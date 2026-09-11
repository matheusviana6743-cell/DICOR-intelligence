# -*- coding: utf-8 -*-
"""DICOR Central - compatibilidade com iframe/NUI do FiveM."""
from __future__ import annotations

from aiohttp import web

import central_home_v700 as v700
import central_home_v707 as v707


@web.middleware
async def iframe_security(request, handler):
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        response = exc

    response.headers.pop("X-Frame-Options", None)

    csp = str(response.headers.get("Content-Security-Policy", ""))
    parts = []
    found = False
    for part in csp.split(";"):
        item = part.strip()
        if not item:
            continue
        if item.lower().startswith("frame-ancestors "):
            parts.append("frame-ancestors *")
            found = True
        else:
            parts.append(item)
    if not found:
        parts.append("frame-ancestors *")
    response.headers["Content-Security-Policy"] = "; ".join(parts)
    response.headers["Cache-Control"] = "no-store"
    return response


_original_login_route = v700.login_route


async def iframe_login_route(request):
    response = await _original_login_route(request)
    cookie = response.cookies.get(v700.COOKIE)
    if cookie is not None:
        cookie["samesite"] = "None"
        cookie["secure"] = True
        cookie["httponly"] = True
        cookie["path"] = "/"
    return response


def install(bot_module):
    v700.security = iframe_security
    v700.login_route = iframe_login_route
    return v707.install(bot_module)
