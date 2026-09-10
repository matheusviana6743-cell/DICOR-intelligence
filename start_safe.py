# -*- coding: utf-8 -*-
"""Launcher oficial do DICOR Core V602.

Somente o núcleo V602 é instalado para BO, Perícia Externa e Dossiê.
Os patches legados não são carregados neste processo.
"""
import asyncio
import os
import traceback

import bot
import dicor_core_v602


async def main():
    client = getattr(bot, 'bot', None)
    token = str(os.getenv('DISCORD_TOKEN') or getattr(bot, 'DISCORD_TOKEN', '')).strip()
    if client is None:
        raise RuntimeError('cliente Discord ausente')
    if not token:
        raise RuntimeError('DISCORD_TOKEN ausente')

    dicor_core_v602.install(bot)
    print('✅ DICOR Core V602 ativo: BO + Perícia + Dossiê. Scanner automático contínuo ativo.', flush=True)
    await client.start(token, reconnect=True)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        raise
