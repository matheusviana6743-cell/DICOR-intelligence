# -*- coding: utf-8 -*-
"""DICOR Central V710 - compatibilidade com iframe/NUI do FiveM.

Corrige o middleware do aiohttp: o app principal registra `security` como
middleware e, por isso, ele precisa usar a assinatura (request, handler).
Mantém a Central V708 intacta e altera apenas os headers/cookie de iframe.
"""
from __future__ import annotations

from aiohttp import web

import central_home_v700 as v700
import central_home_v708 as v708


@web.middleware
async def iframe_security(request, handler):
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        response = exc

    response.headers.pop("X-Frame-Options", None)

    csp = str(response.headers.get("Content-Security-Policy", "")).strip()
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
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(),microphone=(),geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    return response


_original_login_route = v700.login_route


async def iframe_login_route(request):
    response = await _original_login_route(request)
    cookies = list(response.headers.getall("Set-Cookie", [])) if getattr(response, "headers", None) else []
    if cookies:
        response.headers.popall("Set-Cookie")
        for cookie in cookies:
            cookie = cookie.replace("; Path=/; SameSite=Lax", "; Path=/; SameSite=None; Secure")
            response.headers.add("Set-Cookie", cookie)
    return response


def install(bot_module):
    central = v708.install(bot_module)
    v700.security = iframe_security
    v700.login_route = iframe_login_route
    return central
