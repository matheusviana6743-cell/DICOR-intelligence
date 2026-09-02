# -*- coding: utf-8 -*-
"""V168 - restaura as Views persistentes da Central de Dados no Discord.

O painel antigo pode continuar visível no Discord depois de um restart, mas a
View que recebia os cliques deixa de existir em memória. Este módulo procura
em runtime a classe de View original do bot pelos labels/custom_ids e a
registra novamente com timeout=None, sem reescrever o bot.py gigante.
"""
from __future__ import annotations

import asyncio
import inspect
from typing import Any, Optional, Tuple

TARGET_LABELS = {
    "criar ficha",
    "pesquisar fichas",
    "buscar por imagem",
    "painel",
    "atualizar índice visual",
    "atualizar indice visual",
}
TARGET_WORDS = ("ficha", "imagem", "índice", "indice", "painel")


def _children(view: Any):
    try:
        return list(getattr(view, "children", []) or [])
    except Exception:
        return []


def _score_view(view: Any) -> int:
    score = 0
    labels = []
    ids = []
    for item in _children(view):
        label = str(getattr(item, "label", "") or "").strip().casefold()
        custom_id = str(getattr(item, "custom_id", "") or "").strip().casefold()
        if label:
            labels.append(label)
        if custom_id:
            ids.append(custom_id)
        if label in TARGET_LABELS:
            score += 10
        elif any(word in label for word in TARGET_WORDS):
            score += 2
        if any(word in custom_id for word in TARGET_WORDS):
            score += 2
    # O painel da Central normalmente possui 5 ações. Exigir ao menos 2 sinais
    # evita registrar Views aleatórias do bot.
    if len(labels) >= 4:
        score += 2
    return score


def _instantiate(cls: type) -> Optional[Any]:
    try:
        signature = inspect.signature(cls)
        required = [
            p for p in signature.parameters.values()
            if p.name != "self"
            and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and p.default is inspect.Parameter.empty
        ]
        if required:
            return None
    except Exception:
        pass
    try:
        return cls()
    except Exception:
        return None


def _find_best_view(bot_module: Any) -> Tuple[Optional[Any], int, str]:
    discord = getattr(bot_module, "discord", None)
    view_base = getattr(getattr(discord, "ui", None), "View", None)
    if view_base is None:
        return None, 0, "discord.ui.View indisponível"

    best = None
    best_score = 0
    best_name = ""
    for name, cls in list(vars(bot_module).items()):
        try:
            if not inspect.isclass(cls) or cls is view_base or not issubclass(cls, view_base):
                continue
        except Exception:
            continue
        view = _instantiate(cls)
        if view is None:
            continue
        score = _score_view(view)
        if score > best_score:
            best = view
            best_score = score
            best_name = name
    return best, best_score, best_name


async def _restore_after_ready(bot_module: Any) -> None:
    client = getattr(bot_module, "bot", None)
    if client is None:
        return

    # Aguarda o bot estar realmente pronto e os módulos principais já terem
    # sido importados. Não faz leitura de histórico nem bloqueia o gateway.
    await asyncio.sleep(1.5)

    try:
        view, score, name = _find_best_view(bot_module)
        if view is None or score < 10:
            print(
                f"⚠️ V168: nenhuma View da Central encontrada para restauração "
                f"(score={score}, classe={name or 'nenhuma'}).",
                flush=True,
            )
            return

        # Views persistentes precisam de timeout=None.
        try:
            view.timeout = None
        except Exception:
            pass

        # O add_view é idempotente na prática para o mesmo custom_id; não há
        # alteração de mensagens antigas nem criação de canais.
        client.add_view(view)

        labels = [
            str(getattr(item, "label", "") or "").strip()
            for item in _children(view)
            if getattr(item, "label", None)
        ]
        print(
            f"✅ V168: View da Central restaurada: {name} | "
            f"score={score} | botões={labels}",
            flush=True,
        )
        bot_module._DICOR_V168_VIEW_RESTORED = True
    except Exception as exc:
        print(
            f"❌ V168: falha ao restaurar View da Central: {type(exc).__name__}: {exc}",
            flush=True,
        )


def install(bot_module: Any) -> None:
    client = getattr(bot_module, "bot", None)
    if client is None or not hasattr(client, "add_listener"):
        print("⚠️ V168: cliente Discord indisponível; módulo ignorado.", flush=True)
        return

    async def _on_ready_v168() -> None:
        if getattr(bot_module, "_DICOR_V168_RESTORE_STARTED", False):
            return
        bot_module._DICOR_V168_RESTORE_STARTED = True
        asyncio.create_task(_restore_after_ready(bot_module))

    client.add_listener(_on_ready_v168, "on_ready")
    print("V168: restaurador de Views persistentes da Central armado.", flush=True)
