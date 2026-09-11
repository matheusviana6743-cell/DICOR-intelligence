# -*- coding: utf-8 -*-
"""DICOR Central V709 - modo iframe seguro e compatível com embeds.

Mantém a Central V707 e altera somente o necessário para permitir a
renderização dentro de iframe, com origem configurável e cookie compatível
com iframe cross-site.

Env:
    CENTRAL_IFRAME_ORIGINS=https://painel.exemplo.com,https://outro.exemplo.com

Use CENTRAL_IFRAME_ORIGINS=* somente quando o container do iframe for
controlado e a proteção de clickjacking vier do próprio container.
"""
from __future__ import annotations

import os

import central_home_v700 as v700
import central_home_v707 as v707


def _origins() -> list[str]:
    raw = str(os.getenv("CENTRAL_IFRAME_ORIGINS", "")).strip()
    if not raw:
        return []
    out: list[str] = []
    for item in raw.split(","):
        value = item.strip()
        if value and value not in out:
            out.append(value)
    return out


async def iframe_security(req, handler):
    response = await handler(req)
    # Remove apenas o bloqueio de frame do renderer legado.
    response.headers.pop("X-Frame-Options", None)

    origins = _origins()
    if "*" in origins:
        ancestors = "*"
    else:
        ancestors = "'self'" + (" " + " ".join(origins) if origins else "")

    csp = str(response.headers.get("Content-Security-Policy", ""))
    if csp:
        parts = []
        replaced = False
        for part in csp.split(";"):
            item = part.strip()
            if not item:
                continue
            if item.lower().startswith("frame-ancestors "):
                parts.append("frame-ancestors " + ancestors)
                replaced = True
            else:
                parts.append(item)
        if not replaced:
            parts.append("frame-ancestors " + ancestors)
        response.headers["Content-Security-Policy"] = "; ".join(parts)
    else:
        response.headers["Content-Security-Policy"] = "frame-ancestors " + ancestors

    return response


_orig_login_route = v700.login_route


async def iframe_login_route(req):
    response = await _orig_login_route(req)
    # Cookies SameSite=Lax não são enviados em vários cenários de iframe
    # cross-site. Em modo iframe, força SameSite=None + Secure.
    cookie = response.cookies.get(v700.COOKIE)
    if cookie is not None and _origins():
        cookie["samesite"] = "None"
        cookie["secure"] = True
        cookie["httponly"] = True
        cookie["path"] = "/"
    return response


def install(bot_module):
    # Patch mínimo antes de o app aiohttp ser construído pelo V700/V707.
    v700.security = iframe_security
    v700.login_route = iframe_login_route
    return v707.install(bot_module)
