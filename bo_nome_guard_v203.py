# -*- coding: utf-8 -*-
"""DICOR V203 — bloqueia renomeações repetidas dos tópicos de BO.

O tópico recebe seu nome no momento da criação pelo V200. Depois disso,
nenhum módulo pode alterá-lo novamente. O bloqueio é restrito a tópicos cujo
nome atual já identifica um BO, para não afetar outros recursos do Discord.
"""
from __future__ import annotations

import re
import discord

_INSTALLED = False
_ORIGINAL_THREAD_EDIT = None

_BO_NAME_RE = re.compile(r"boletim\s+de\s+ocorr[eê]ncia", re.I)


def _is_bo_thread(channel) -> bool:
    try:
        if not isinstance(channel, discord.Thread):
            return False
        return bool(_BO_NAME_RE.search(str(getattr(channel, "name", "") or "")))
    except Exception:
        return False


def _patch_thread_edit():
    global _ORIGINAL_THREAD_EDIT
    original = getattr(discord.Thread, "edit", None)
    if not callable(original) or _ORIGINAL_THREAD_EDIT is not None:
        return
    _ORIGINAL_THREAD_EDIT = original

    async def guarded_edit(self, *, reason=None, **fields):
        if _is_bo_thread(self) and "name" in fields:
            # O nome inicial do tópico é definitivo. Os demais campos continuam
            # podendo ser editados normalmente, quando algum outro recurso pedir.
            fields.pop("name", None)
        if not fields:
            return self
        return await _ORIGINAL_THREAD_EDIT(self, reason=reason, **fields)

    discord.Thread.edit = guarded_edit


def install(botmod):
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    try:
        _patch_thread_edit()
        print("✅ V203 BO: nome dos tópicos protegido contra renomeações repetidas.", flush=True)
    except Exception as exc:
        print(f"⚠️ V203 BO: não foi possível instalar proteção de nome: {type(exc).__name__}: {exc}", flush=True)
