# -*- coding: utf-8 -*-
"""V202 - correção das interações dos mini-painéis de BO.

O painel V200 continua sendo o painel visual. Este módulo apenas fortalece a
resolução do atendimento pelo tópico Discord, para que os callbacks e modais
legados encontrem o registro correto mesmo quando o tópico foi criado pelo
novo motor automático.
"""
import traceback
import discord

_installed = False
_botmod = None
_original = None


def _records():
    try:
        return list(_botmod.carregar_atendimentos_boletins() or [])
    except Exception:
        return []


def _find_by_thread(interaction):
    channel = getattr(interaction, "channel", None)
    cid = int(getattr(channel, "id", 0) or 0)
    if not cid:
        return None

    # Primeiro pelo tópico atual; depois pelo canal de atendimento.
    for item in reversed(_records()):
        if not isinstance(item, dict):
            continue
        if int(item.get("thread_id") or 0) == cid or int(item.get("area_id") or 0) == cid:
            return item

    # Último fallback: mensagem do painel, quando o Discord ainda não
    # disponibilizou o objeto do tópico no cache.
    message = getattr(interaction, "message", None)
    mid = int(getattr(message, "id", 0) or 0)
    if mid:
        for item in reversed(_records()):
            if int(item.get("painel_msg_id") or 0) == mid:
                return item
    return None


async def _robust_garantir(interaction):
    # Preserva o comportamento original quando ele consegue localizar o BO.
    if _original is not None:
        try:
            atendimento = await _original(interaction)
            if atendimento:
                return atendimento
        except Exception:
            pass
    return _find_by_thread(interaction)


def install(botmod):
    global _installed, _botmod, _original
    _botmod = botmod
    if _installed:
        return
    _installed = True

    original = getattr(botmod, "garantir_atendimento_interaction", None)
    if callable(original):
        _original = original
        botmod.garantir_atendimento_interaction = _robust_garantir

    print("✅ V202 Painel BO: resolução por tópico Discord ativada.", flush=True)
