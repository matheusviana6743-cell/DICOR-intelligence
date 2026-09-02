# -*- coding: utf-8 -*-
"""V170 - servidor HTTP seguro da Central DICOR."""
from __future__ import annotations

import os
from typing import Any, Optional

_APP_NAMES = ("web_app", "central_app", "app", "application", "aiohttp_app", "central_web_app")


def _find_app(bot_module) -> Optional[Any]:
    for name in _APP_NAMES:
        candidate = getattr(bot_module, name, None)
        if candidate is not None and hasattr(candidate, "router"):
            return candidate
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
        print("⚠️ V170: aiohttp.web indisponível; Central HTTP não iniciada.", flush=True)
        return False
    app = _find_app(bot_module)
    if app is None:
        print("⚠️ V170: aplicação aiohttp não encontrada; Central HTTP não iniciada.", flush=True)
        return False
    try:
        port = int(os.getenv("PORT", "8000"))
    except Exception:
        port = 8000

    runner = None
    site = None
    try:
        runner = web.AppRunner(app, access_log=None, handle_signals=False)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
    except BaseException as exc:
        # Isola também CancelledError/erros de lifecycle: HTTP nunca derruba o Gateway.
        print(f"⚠️ V170: HTTP da Central não iniciou ({type(exc).__name__}: {exc})", flush=True)
        if runner is not None:
            try:
                await runner.cleanup()
            except BaseException:
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
    except BaseException:
        pass
    bot_module._v170_http_runner = None
    bot_module._v170_http_site = None
    bot_module._v170_http_started = False
