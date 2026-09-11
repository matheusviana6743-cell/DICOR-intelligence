# -*- coding: utf-8 -*-
"""DICOR Rate Guard V615.

Evita rajadas de chamadas à API do Discord causadas pelo scanner V605.

Regras:
- não varre todos os tópicos arquivados a cada BO/perícia;
- mantém um índice curto em cache por 30s;
- a recuperação de restart roda uma vez e depois fica em baixa frequência;
- o gatilho on_message continua imediato;
- não altera nomes, seleção de agentes ou deduplicação do atendimento.
"""
from __future__ import annotations

import asyncio
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

    original_target_threads = core.target_threads
    original_recover = core.recover_channel

    async def safe_target_threads(self: Any, kind: str, refresh: bool = False):
        now = asyncio.get_running_loop().time()
        cached = self._target_cache.get(kind)
        if cached and now - cached[0] < TARGET_CACHE_SECONDS:
            return cached[1], cached[2]

        target_id = self.__class__.__dict__.get("_unused", None)
        target_id = 0
        # IDs são obtidos das constantes do módulo original através do método
        # original; para evitar a varredura ilimitada, reconstruímos apenas o
        # índice dos tópicos ativos e dos últimos arquivados.
        from dicor_core_v605 import BO_TARGET_ID, PERICIA_TARGET_ID, month_of_thread, extract_number
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
                        import re
                        m = re.search(r"DICOR-AUTO\\|kind=(bo|pericia)\\|source=(\\d+)\\|month=([^|]+)\\|number=(\\d{4,8})", footer)
                        if m:
                            source_ids.add(int(m.group(2)))
                            keys.add((m.group(1), m.group(3), f"{int(m.group(4)):04d}"))
            except Exception:
                pass

        self._target_cache[kind] = (now, keys, source_ids)
        return keys, source_ids

    async def safe_scanner(self: Any) -> None:
        # Uma recuperação curta após o READY é suficiente para mensagens que
        # chegaram durante deploy/restart. Depois, on_message trata o fluxo
        # normal e uma recuperação espaçada cobre eventual falha de evento.
        await asyncio.sleep(5)
        first = True
        while True:
            try:
                await original_recover("bo", self.__class__.__dict__.get("_unused_channel", 0) or 1490200514837745754)
            except Exception:
                pass
            try:
                await original_recover("pericia", 1490200524367200297)
            except Exception:
                pass
            first = False
            await asyncio.sleep(RECOVERY_INTERVAL_SECONDS)

    # A recuperação original já foi limitada pelo V606. O wrapper do índice
    # reduz drasticamente as chamadas dentro dela.
    core.target_threads = types.MethodType(safe_target_threads, core)
    core.scanner = types.MethodType(safe_scanner, core)
    core._dicor_rate_guard_v615 = True
    print("🛡️ DICOR Rate Guard V615 ativo | cache Discord=30s | recuperação=10min", flush=True)
    return core
