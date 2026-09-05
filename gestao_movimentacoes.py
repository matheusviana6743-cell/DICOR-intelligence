# -*- coding: utf-8 -*-
"""Compatibilidade do módulo antigo de movimentações.

A gestão ativa permanece em gestao_v2.py. Este módulo só instala o hotfix que
separa o painel de gestão do canal de hierarquia e remove mensagens indevidas.
"""
from __future__ import annotations
from typing import Any


async def install(bot_module: Any) -> bool:
    try:
        import gestao_hotfix_v4
        await gestao_hotfix_v4.install(bot_module)
    except Exception as exc:
        print(f"⚠️ [GESTAO V4] hotfix isolado: {type(exc).__name__}: {exc}", flush=True)
    return True
