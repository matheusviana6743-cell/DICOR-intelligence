# -*- coding: utf-8 -*-
"""DICOR clean launcher.

The BO, Perícia Externa and Dossiê flows are provided by one V600 core.
Legacy V147/V181/V186/V200 document/interaction patches are intentionally
not installed here, avoiding multiple listeners and conflicting Views.
"""
import asyncio
import os
import traceback
import bot
import dicor_core_v600
try:
    import runtime_safety_v180
except Exception:
    runtime_safety_v180=None


def install_safety():
    try:
        if runtime_safety_v180 is not None:
            runtime_safety_v180.install(bot)
    except Exception:
        traceback.print_exc()


async def main():
    client=getattr(bot,'bot',None)
    token=str(os.getenv('DISCORD_TOKEN') or getattr(bot,'DISCORD_TOKEN','')).strip()
    if client is None or not token:
        raise RuntimeError('cliente Discord ou DISCORD_TOKEN ausente')
    install_safety()
    dicor_core_v600.install(bot)
    print('✅ DICOR V600 ativo: BO + Perícia + Dossiê | listeners legados de BO/Dossiê não instalados.',flush=True)
    await client.start(token,reconnect=True)

if __name__=='__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        traceback.print_exc()
        raise
