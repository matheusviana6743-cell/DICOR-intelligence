# -*- coding: utf-8 -*-
"""DICOR Central V628.

Camada mínima sobre V627 para desativar autenticação temporariamente de
verdade, sem tocar no restante da Central.
"""
from __future__ import annotations
from typing import Any
import central_v627_final as v627

base = v627.base
_ORIGINAL_READ_SESSION = base.read_session
_ORIGINAL_START = v627.start_server_v627

# A Central web fica aberta temporariamente.
# Quando não existe cookie, usamos uma sessão virtual somente para o painel.
def read_session_open(request: Any):
    try:
        session = _ORIGINAL_READ_SESSION(request)
        if session:
            return session
    except Exception:
        pass
    return ("CENTRAL", "LIVRE")

base.read_session = read_session_open
v627.base.read_session = read_session_open

async def start_server_v628(client: Any):
    v627.base.read_session = read_session_open
    base.read_session = read_session_open
    return await _ORIGINAL_START(client)

base.start_server = start_server_v628

def install(bot_module: Any):
    return base.install(bot_module)
