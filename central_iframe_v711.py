# -*- coding: utf-8 -*-
"""DICOR Central - iframe/NUI FiveM.

Mantém a Central V708 e corrige a sessão dentro do iframe. O CEF do FiveM
pode tratar a sessão como contexto incorporado; por isso o cookie é alterado
no objeto Set-Cookie do aiohttp, e não por substituição textual do header.
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
    response.headers.pop("Content-Security-Policy", None)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


async def iframe_login_route(request):
    response = await v700._central_original_login_route(request)
    try:
        cookie = response.cookies.get(v700.COOKIE)
        if cookie is not None:
            cookie["samesite"] = "None"
            cookie["secure"] = True
            cookie["httponly"] = True
            cookie["path"] = "/"
    except Exception:
        # Fallback para versões do aiohttp que não expõem o cookie por nome.
        headers = list(response.headers.getall("Set-Cookie", []))
        if headers:
            response.headers.popall("Set-Cookie")
            for header in headers:
                if "SameSite=Lax" in header:
                    header = header.replace("SameSite=Lax", "SameSite=None")
                elif "SameSite=" not in header:
                    header += "; SameSite=None"
                if "Secure" not in header:
                    header += "; Secure"
                response.headers.add("Set-Cookie", header)
    return response


def install(bot_module):
    central = v708.install(bot_module)
    if not hasattr(v700, "_central_original_login_route"):
        v700._central_original_login_route = v700.login_route
    v700.security = iframe_security
    v700.login_route = iframe_login_route
    return central
