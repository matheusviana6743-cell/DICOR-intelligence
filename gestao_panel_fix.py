# -*- coding: utf-8 -*-
"""Gestão DICOR — correção de publicação.

Este módulo NÃO publica o painel de gestão automaticamente. O painel deve ser
publicado somente por ação administrativa explícita, nunca durante o boot do bot.
A hierarquia é tratada separadamente no módulo hierarquia_dicor.py.
"""
from __future__ import annotations

from typing import Any

import discord

_INSTALLED = False
_BOT_MODULE: Any = None


async def install(bot_module: Any) -> bool:
    global _INSTALLED, _BOT_MODULE
    _BOT_MODULE = bot_module
    client = getattr(bot_module, "bot", None)
    if client is None:
        return False
    if _INSTALLED:
        return True

    # Mantém os componentes persistentes disponíveis para botões já existentes,
    # mas NÃO chama nenhum _ensure_panel e NÃO envia mensagens no boot.
    try:
        import gestao_v3
        try:
            client.add_view(gestao_v3.GestaoV3Painel())
        except Exception:
            pass
    except Exception as exc:
        print(f"⚠️ [GESTAO] view persistente: {type(exc).__name__}: {exc}", flush=True)

    _INSTALLED = True
    print("✅ [GESTAO] publicação automática do painel DESATIVADA.", flush=True)
    return True


async def _refresh(*_args: Any, **_kwargs: Any) -> None:
    # Compatibilidade com módulos antigos: nunca publica painel aqui.
    return None


async def _ensure_panel(*_args: Any, **_kwargs: Any) -> None:
    # Compatibilidade: chamadas antigas não podem mais enviar o painel.
    return None
