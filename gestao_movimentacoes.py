# -*- coding: utf-8 -*-
"""Compatibilidade do módulo antigo de movimentações.

A gestão ativa foi consolidada em gestao_v2.py para evitar listeners duplicados.
Este módulo permanece importável porque o entrypoint ainda pode carregá-lo.
"""
from __future__ import annotations
from typing import Any


async def install(bot_module: Any) -> bool:
    print("ℹ️ [GESTAO LEGADO] listener antigo desativado; gestão consolidada em Gestao V3.", flush=True)
    return True
