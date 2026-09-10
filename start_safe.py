# -*- coding: utf-8 -*-
"""Launcher oficial do DICOR Core V603.

O fluxo novo de BO, Perícia Externa e Dossiê é instalado como um único núcleo.
Nenhum patch legado de BO/Perícia/Dossiê é carregado por este launcher.
"""
import asyncio
import os
import traceback

import bot
import dicor_core_v603


async def main():
    client = getattr(bot, "bot", None)
    token = str(os.getenv("DISCORD_TOKEN") or getattr(bot, "DISCORD_TOKEN", "")).strip()
    if client is None:
        raise RuntimeError("cliente Discord ausente")
    if not token:
        raise RuntimeError("DISCORD_TOKEN ausente")

    dicor_core_v603.install(bot)
    print("✅ DICOR Core V603 ativo | BO + Perícia + Dossiê | scanner automático contínuo", flush=True)
    await client.start(token, reconnect=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        raise
