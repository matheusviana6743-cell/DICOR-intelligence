# -*- coding: utf-8 -*-
"""DICOR V204 — proteção definitiva de nomes dos tópicos de BO.

Um tópico de BO recebe o nome uma única vez, na criação. Depois disso,
qualquer tentativa de alteração do campo ``name`` é descartada.
A proteção identifica BOs pelo pai fixo de atendimento e também pelos IDs
registrados no banco, portanto continua funcionando mesmo depois de uma
renomeação indevida anterior.
"""
from __future__ import annotations

import re
import discord

TARGET_ID = 1525762770253910136
_INSTALLED = False
_ORIGINAL_THREAD_EDIT = None
_BO_NAME_RE = re.compile(r"boletim\s+de\s+ocorr[eê]ncia", re.I)
_PROTECTED_IDS = set()


def _load_protected_ids(botmod):
    try:
        rows = list(botmod.carregar_atendimentos_boletins() or [])
    except Exception:
        rows = []
    for row in rows:
        for key in ("thread_id", "area_id"):
            try:
                value = int(row.get(key) or 0)
            except Exception:
                value = 0
            if value:
                _PROTECTED_IDS.add(value)


def _is_bo_thread(channel) -> bool:
    try:
        if not isinstance(channel, discord.Thread):
            return False
        if int(getattr(channel, "id", 0) or 0) in _PROTECTED_IDS:
            return True
        parent_id = int(getattr(channel, "parent_id", 0) or 0)
        if parent_id == TARGET_ID:
            return True
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
        blocked = False
        if _is_bo_thread(self) and "name" in fields:
            fields.pop("name", None)
            blocked = True
        if blocked:
            print(f"🛡️ V204: tentativa de renomear BO bloqueada | thread={getattr(self, 'id', 0)}", flush=True)
        if not fields:
            return self
        return await _ORIGINAL_THREAD_EDIT(self, reason=reason, **fields)

    discord.Thread.edit = guarded_edit


def install(botmod):
    global _INSTALLED
    _load_protected_ids(botmod)
    if _INSTALLED:
        return
    _INSTALLED = True
    try:
        _patch_thread_edit()
        print("✅ V204 BO: proteção definitiva de nomes ativa.", flush=True)
    except Exception as exc:
        print(f"⚠️ V204 BO: falha ao instalar proteção: {type(exc).__name__}: {exc}", flush=True)
