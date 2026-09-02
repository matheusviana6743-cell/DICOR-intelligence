# -*- coding: utf-8 -*-
"""V170 - inicializador seguro da Central HTTP.

Não altera rotas nem autenticação. Apenas garante que a aplicação aiohttp
registrada pelas versões da Central seja publicada em 0.0.0.0:$PORT.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Optional


_APP_NAMES = (
    "web_app",
    "central_app",
    "app",
    "application",
    "aiohttp_app",
    "central_web_app",
)


def _find_app(bot_module) -> Optional[Any]:
    for name in _APP_NAMES:
        candidate = getattr(bot_module, name, None)
        if candidate is not None and hasattr(candidate, "router"):
            return candidate
    # Algumas versões guardam a aplicação em um atributo privado.
    for name in dir(bot_module):
        if name.startswith("_"):
            continue
        try:
            candidate = getattr(bot_module, name)
        except Exception:
            continue
        if candidate is not None and hasattr(candidate, "router") and hasattr(candidate, "_middlewares"):
            return candidate
    return None


async def start(bot_module) -> bool:
    if getattr(bot_module, "_v170_http_started", False):
        return True

    web = getattr(bot_module, "web", None)
    if web is None or not hasattr(web, "AppRunner"):
        print("⚠️ V170: aiohttp.web não está disponível; Central HTTP não iniciada.", flush=True)
        return False

    app = _find_app(bot_module)
    if app is None:
        print("⚠️ V170: aplicação aiohttp da Central não encontrada; nenhuma porta foi tomada.", flush=True)
        return False

    try:
        port = int(os.getenv("PORT", "8000"))
    except Exception:
        port = 8000

    try:
        runner = web.AppRunner(app, access_log=None, handle_signals=False)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
    except OSError as exc:
        # Não derruba o Discord se outra camada já estiver usando a PORT.
        print(f"⚠️ V170: PORT {port} já está ocupada ou indisponível: {type(exc).__name__}: {exc}", flush=True)
        try:
            await runner.cleanup()
        except Exception:
            pass
        return False
    except Exception as exc:
        print(f"⚠️ V170: falha ao iniciar HTTP da Central: {type(exc).__name__}: {exc}", flush=True)
        try:
            await runner.cleanup()
        except Exception:
            pass
        return False

    bot_module._v170_http_runner = runner
    bot_module._v170_http_site = site
    bot_module._v170_http_started = True
    print(f"✅ V170 Central HTTP ONLINE em 0.0.0.0:{port}", flush=True)
    return True


async def stop(bot_module) -> None:
    runner = getattr(bot_module, "_v170_http_runner", None)
    if runner is None:
        return
    try:
        await runner.cleanup()
    except Exception:
        pass
    bot_module._v170_http_runner = None
    bot_module._v170_http_site = None
    bot_module._v170_http_started = False
