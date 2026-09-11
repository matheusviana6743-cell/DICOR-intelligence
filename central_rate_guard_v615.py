# -*- coding: utf-8 -*-
"""Proteção de rate limit da Central V615.

A Central é somente leitura, então não precisa consultar o Discord a cada
20 segundos. O refresh fica em 120s para evitar rajadas e ainda manter os
dados suficientemente atuais.
"""
from __future__ import annotations

import asyncio
from typing import Any

import central_discord_v613

REFRESH_SECONDS = 120.0


def install(central: Any) -> Any:
    if getattr(central, "_central_rate_guard_v615", False):
        return central

    async def safe_refresh_loop(client: Any) -> None:
        while True:
            try:
                await central_discord_v613.refresh(client)
            except Exception:
                pass
            await asyncio.sleep(REFRESH_SECONDS)

    central_discord_v613.refresh_loop = safe_refresh_loop
    central._central_rate_guard_v615 = True
    print("🛡️ Central Rate Guard V615 ativo | atualização Discord=120s", flush=True)
    return central
