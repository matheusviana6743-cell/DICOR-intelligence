# -*- coding: utf-8 -*-
"""DICOR Central V710 - modo iframe compatível com FiveM NUI.

Mantém a Central V708 e altera apenas a camada de incorporação:
- permite execução dentro de iframe sem exigir domínio pai específico;
- remove X-Frame-Options que bloquearia a NUI;
- usa frame-ancestors * na CSP HTML;
- ajusta o cookie de sessão para SameSite=None + Secure, necessário para
  sessões em contexto incorporado;
- preserva autenticação, CSRF, autorização e todas as funcionalidades da V708.
"""
from __future__ import annotations

from aiohttp import web

import central_home_v700 as v700
import central_home_v708 as v708


async def iframe_security(req, handler):
    try:
        response = await handler(req)
    except web.HTTPException as exc:
        response = exc
    response.headers.pop("X-Frame-Options", None)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "frame-ancestors *; "
        "base-uri 'self'; form-action 'self'; object-src 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(),microphone=(),geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    return response


async def iframe_login_route(req):
    response = await v700.login_route(req)
    if getattr(response, "headers", None) is not None:
        cookies = list(response.headers.getall("Set-Cookie", []))
        if cookies:
            response.headers.popall("Set-Cookie")
            for cookie in cookies:
                cookie = cookie.replace(
                    "; Path=/; SameSite=Lax",
                    "; Path=/; SameSite=None; Secure",
                )
                response.headers.add("Set-Cookie", cookie)
    return response


def install(bot_module):
    central = v708.install(bot_module)
    v700.security = iframe_security
    v700.login_route = iframe_login_route
    return central
