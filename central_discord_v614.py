# -*- coding: utf-8 -*-
"""Compatibility launcher for Central V615."""
from __future__ import annotations

from urllib.parse import quote

from aiohttp import web

if not hasattr(web, "URLEncode"):
    web.URLEncode = quote  # type: ignore[attr-defined]

import central_discord_v615


def install(bot_module):
    return central_discord_v615.install(bot_module)
