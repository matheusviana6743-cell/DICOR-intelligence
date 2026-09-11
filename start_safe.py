# -*- coding: utf-8 -*-
"""Launcher oficial do DICOR Core V606 + Central V610."""
import asyncio
import os
import traceback

import bot
import dicor_legacy_guard_v605
import dicor_core_v605
import dicor_recovery_guard_v606
import central_discord_v610


async def main():
    client = getattr(bot, "bot", None)
    token = str(os.getenv("DISCORD_TOKEN") or getattr(bot, "DISCORD_TOKEN", "")).strip()
    if client is None:
        raise RuntimeError("cliente Discord ausente")
    if not token:
        raise RuntimeError("DISCORD_TOKEN ausente")

    dicor_legacy_guard_v605.install(bot)
    core = dicor_core_v605.install(bot)
    dicor_recovery_guard_v606.install(core)

    central = central_discord_v610.install(bot)
    await central.start()

    print("✅ DICOR Core V606 ativo | BO + Perícia | recuperação limitada | Central V610 rápida", flush=True)
    await client.start(token, reconnect=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        raise
