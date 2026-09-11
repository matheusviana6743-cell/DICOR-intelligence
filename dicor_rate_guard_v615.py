# -*- coding: utf-8 -*-
"""DICOR Rate Guard V615.

Reduz chamadas à API do Discord causadas pelo scanner V605 sem alterar o
fluxo normal de BO/perícia, seleção de agente ou nomes dos tópicos.
"""
from __future__ import annotations

import asyncio
import re
import types
from typing import Any

import discord

TARGET_CACHE_SECONDS = 30.0
RECOVERY_INTERVAL_SECONDS = 600.0
ARCHIVED_THREADS_LIMIT = 30
THREAD_HISTORY_LIMIT = 3


def install(core: Any) -> Any:
    if getattr(core, "_dicor_rate_guard_v615", False):
        return core

    original_recover = core.recover_channel

    async def safe_target_threads(self: Any, kind: str, refresh: bool = False):
        now = asyncio.get_running_loop().time()
        cached = self._target_cache.get(kind)
        if cached and now - cached[0] < TARGET_CACHE_SECONDS:
            return cached[1], cached[2]

        from dicor_core_v605 import BO_TARGET_ID, PERICIA_TARGET_ID, extract_number, month_of_thread

        target_id = BO_TARGET_ID if kind == "bo" else PERICIA_TARGET_ID
        parent = await self.channel(target_id)
        if not isinstance(parent, discord.TextChannel):
            return set(), set()

        threads = list(getattr(parent, "threads", []) or [])
        known_ids = {t.id for t in threads}
        try:
            async for thread in parent.archived_threads(limit=ARCHIVED_THREADS_LIMIT):
                if thread.id not in known_ids:
                    threads.append(thread)
                    known_ids.add(thread.id)
        except Exception:
            pass

        keys: set[tuple[str, str, str]] = set()
        source_ids: set[int] = set()
        marker_re = re.compile(
            r"DICOR-AUTO\|kind=(bo|pericia)\|source=(\d+)\|month=([^|]+)\|number=(\d{4,8})"
        )

        for thread in threads:
            name = str(getattr(thread, "name", "") or "")
            month = month_of_thread(thread)
            number = extract_number(name, kind)
            if number:
                keys.add((kind, month, number))
            try:
                async for msg in thread.history(limit=THREAD_HISTORY_LIMIT, oldest_first=True):
                    for embed in msg.embeds or []:
                        footer = str(getattr(embed.footer, "text", "") or "")
                        match = marker_re.search(footer)
                        if match:
                            source_ids.add(int(match.group(2)))
                            keys.add((match.group(1), match.group(3), f"{int(match.group(4)):04d}"))
            except Exception:
                pass

        self._target_cache[kind] = (now, keys, source_ids)
        return keys, source_ids

    async def safe_scanner(self: Any) -> None:
        await asyncio.sleep(5)
        while True:
            try:
                await original_recover("bo", 1490200514837745754)
            except Exception:
                pass
            try:
                await original_recover("pericia", 1490200524367200297)
            except Exception:
                pass
            await asyncio.sleep(RECOVERY_INTERVAL_SECONDS)

    core.target_threads = types.MethodType(safe_target_threads, core)
    core.scanner = types.MethodType(safe_scanner, core)
    core._dicor_rate_guard_v615 = True
    print("🛡️ DICOR Rate Guard V615 ativo | índice limitado + recuperação a cada 10min", flush=True)
    return core
