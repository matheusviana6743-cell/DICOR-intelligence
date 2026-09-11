# -*- coding: utf-8 -*-
"""Launcher oficial do DICOR Core V605.

BO e Perícia usam um único núcleo automático. O scanner recupera mensagens
que chegaram durante deploy/restart e a deduplicação usa os próprios tópicos
existentes no Discord como fonte de verdade.
"""
import asyncio
import os
import traceback

import bot
import dicor_legacy_guard_v605
import dicor_core_v605


async def main():
    client = getattr(bot, "bot", None)
    token = str(os.getenv("DISCORD_TOKEN") or getattr(bot, "DISCORD_TOKEN", "")).strip()
    if client is None:
        raise RuntimeError("cliente Discord ausente")
    if not token:
        raise RuntimeError("DISCORD_TOKEN ausente")

    # Primeiro elimina somente os listeners automáticos antigos.
    dicor_legacy_guard_v605.install(bot)
    # Depois instala UM único núcleo para BO + Perícia.
    dicor_core_v605.install(bot)
    print("✅ DICOR Core V605 ativo | BO + Perícia | gatilho imediato + recuperação de deploy + dedupe real", flush=True)
    await client.start(token, reconnect=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        raise
