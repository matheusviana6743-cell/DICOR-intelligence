# -*- coding: utf-8 -*-
import asyncio
import bot
import dossie_v161

if __name__ == '__main__':
    try:
        if hasattr(bot, '_v70_iniciar_health_bootstrap'):
            bot._v70_iniciar_health_bootstrap()
    except Exception:
        pass
    dossie_v161.install(bot)
    asyncio.run(bot._runtime_lifecycle_entrypoint())
