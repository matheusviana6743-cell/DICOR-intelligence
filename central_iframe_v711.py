# -*- coding: utf-8 -*-
"""Compatibilidade dedicada da Central DICOR com iframe/NUI do FiveM.

A camada de iframe é aplicada antes da criação da Application do aiohttp.
Não usa X-Frame-Options e não injeta uma CSP frame-ancestors restritiva.
A autenticação, CSRF e autorização continuam sendo as mesmas do núcleo.
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

    # Compatibilidade com o navegador embutido do FiveM/NUI.
    response.headers.pop("X-Frame-Options", None)
    response.headers.pop("Content-Security-Policy", None)

    # Evita cache de sessão/páginas da Central dentro do CEF.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(),microphone=(),geolocation=()"
    return response


_original_login_route = v700.login_route


async def iframe_login_route(request):
    response = await _original_login_route(request)

    # A sessão em iframe precisa aceitar contexto incorporado.
    cookies = list(response.headers.getall("Set-Cookie", []))
    if cookies:
        response.headers.popall("Set-Cookie")
        for cookie in cookies:
            cookie = cookie.replace(
                "; Path=/; SameSite=Lax",
                "; Path=/; SameSite=None; Secure",
            )
            if "SameSite=" not in cookie:
                cookie += "; SameSite=None; Secure"
            response.headers.add("Set-Cookie", cookie)
    return response


def install(bot_module):
    # IMPORTANTE: os patches precisam ocorrer antes de v708 criar a aiohttp.Application.
    v700.security = iframe_security
    v700.login_route = iframe_login_route
    return v708.install(bot_module)
