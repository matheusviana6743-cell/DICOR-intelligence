# -*- coding: utf-8 -*-
"""DICOR Rate Guard V615.

Protege o Core V605 contra rajadas de chamadas à API do Discord.
A lógica de BO/perícia, seleção de agentes e nomes dos tópicos permanece igual.
"""
from __future__ import annotations

import asyncio
import types
from typing import Any

import discord

# Recuperação somente para cobrir mensagens recentes perdidas durante restart.
RECOVERY_INTERVAL_SECONDS = 900.0
RECOVERY_LIMIT = 100


def install(core: Any) -> Any:
    if getattr(core, "_dicor_rate_guard_v615", False):
        return core

    original_recover = core.recover_channel

    async def safe_target_threads(self: Any, kind: str, refresh: bool = False):
        # O Core já mantém estado e o nome do tópico. Para evitar dezenas de
        # requests de histórico, usamos somente os tópicos atualmente em cache
        # do Discord; não varremos mensagens de tópicos arquivados.
        from dicor_core_v605 import BO_TARGET_ID, PERICIA_TARGET_ID, extract_number, month_of_thread

        now = asyncio.get_running_loop().time()
        cached = self._target_cache.get(kind)
        if cached and now - cached[0] < 120.0 and not refresh:
            return cached[1], cached[2]

        target_id = BO_TARGET_ID if kind == "bo" else PERICIA_TARGET_ID
        parent = await self.channel(target_id)
        if not isinstance(parent, discord.TextChannel):
            return set(), set()

        threads = list(getattr(parent, "threads", []) or [])
        keys: set[tuple[str, str, str]] = set()
        source_ids: set[int] = set()

        for thread in threads:
            name = str(getattr(thread, "name", "") or "")
            month = month_of_thread(thread)
            number = extract_number(name, kind)
            if number:
                keys.add((kind, month, number))

        self._target_cache[kind] = (now, keys, source_ids)
        return keys, source_ids

    async def safe_scanner(self: Any) -> None:
        # Pequena espera para o READY estabilizar antes da primeira recuperação.
        await asyncio.sleep(30)
        while True:
            try:
                await original_recover("bo", 1490200514837745754)
            except Exception as exc:
                print(f"⚠️ Rate Guard BO recovery: {type(exc).__name__}: {exc}", flush=True)
            try:
                await original_recover("pericia", 1490200524367200297)
            except Exception as exc:
                print(f"⚠️ Rate Guard Perícia recovery: {type(exc).__name__}: {exc}", flush=True)
            await asyncio.sleep(RECOVERY_INTERVAL_SECONDS)

    core.target_threads = types.MethodType(safe_target_threads, core)
    core.scanner = types.MethodType(safe_scanner, core)
    core._dicor_rate_guard_v615 = True
    print("🛡️ DICOR Rate Guard V615 ativo | recovery=100 mensagens/15min | sem histórico de tópicos", flush=True)
    return core
