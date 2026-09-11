# -*- coding: utf-8 -*-
"""Compatibility launcher for Central V613.

Keeps the V613 design and data logic while fixing URL quoting compatibility
with aiohttp versions used by the Railway runtime.
"""
from __future__ import annotations

from urllib.parse import quote

from aiohttp import web

# V613 uses web.URLEncode for the protected-route redirect. Some aiohttp
# versions do not expose that helper, so provide the compatible implementation.
if not hasattr(web, "URLEncode"):
    web.URLEncode = quote  # type: ignore[attr-defined]

import central_discord_v613


def install(bot_module):
    return central_discord_v613.install(bot_module)
