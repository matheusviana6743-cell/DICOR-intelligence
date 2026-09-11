# -*- coding: utf-8 -*-
"""Proteção de rate limit da Central V615."""
from __future__ import annotations

import asyncio
from typing import Any

import central_discord_v615

REFRESH_SECONDS = 300.0


def install(central: Any) -> Any:
    if getattr(central, "_central_rate_guard_v615", False):
        return central

    async def safe_refresh_loop(client: Any) -> None:
        # Nunca consultar a API enquanto o gateway ainda não estiver READY.
        while not getattr(client, "is_ready", lambda: False)():
            await asyncio.sleep(5)

        while True:
            try:
                # Nesta etapa a Central consulta somente Procurados.
                await central_discord_v615.refresh(client)
            except Exception as exc:
                print(f"⚠️ Central refresh: {type(exc).__name__}: {exc}", flush=True)
            await asyncio.sleep(REFRESH_SECONDS)

    central_discord_v615.refresh_loop = safe_refresh_loop
    central._central_rate_guard_v615 = True
    print("🛡️ Central Rate Guard V615 ativo | refresh=300s | somente Procurados | após READY", flush=True)
    return central
