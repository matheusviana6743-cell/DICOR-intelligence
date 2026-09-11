# -*- coding: utf-8 -*-
"""Launcher oficial do DICOR Core V604.

BO e Perícia usam um único núcleo automático. O scanner também recupera
mensagens que chegaram durante deploy/restart. O Dossiê é gerado pelo
renderer local do V604, sem depender de template/base64 externo.
"""
import asyncio
import os
import traceback

import bot
import dicor_legacy_guard_v604
import dicor_core_v604


async def main():
    client = getattr(bot, "bot", None)
    token = str(os.getenv("DISCORD_TOKEN") or getattr(bot, "DISCORD_TOKEN", "")).strip()
    if client is None:
        raise RuntimeError("cliente Discord ausente")
    if not token:
        raise RuntimeError("DISCORD_TOKEN ausente")

    dicor_legacy_guard_v604.install(bot)
    dicor_core_v604.install(bot)
    print("✅ DICOR Core V604 ativo | BO + Perícia + Dossiê | gatilho por canal + scanner contínuo", flush=True)
    await client.start(token, reconnect=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        raise
