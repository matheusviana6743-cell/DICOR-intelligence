# -*- coding: utf-8 -*-
"""Promoções, rebaixamentos e sincronização da hierarquia.

Opera como listener adicional e não altera a lógica de Gestão já existente.
Falhas deste módulo são sempre isoladas e não devem derrubar o bot.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROMOCOES_CHANNEL_ID = 1545160616522813520
REBAIXAMENTOS_CHANNEL_ID = 1545160585216532530
HISTORICO_FILE = "historico_movimentacoes_cargo.json"
_MARKER = "<!-- DICOR_HIERARQUIA_MIRROR -->"
_LOCK = asyncio.Lock()
_INSTALLED = False

_NAME_HINTS = (
    "delegado", "diretor", "inspetor", "investigador", "agente", "escriv",
    "estagi", "coordenador", "superintendente", "perito"
)


def _data_path(bot_module: Any) -> Path:
    return Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data"))) / HISTORICO_FILE


def _load_history(bot_module: Any) -> dict[str, Any]:
    path = _data_path(bot_module)
    try:
        if not path.exists():
            return {"eventos": []}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"eventos": []}
    except Exception:
        return {"eventos": []}


def _save_history(bot_module: Any, data: dict[str, Any]) -> None:
    path = _data_path(bot_module)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:
        print(f"⚠️ [GESTAO] histórico não salvo: {type(exc).__name__}: {exc}", flush=True)


def _hierarchy_ids(bot_module: Any) -> set[int]:
    raw = str(os.getenv("DICOR_HIERARQUIA_CARGO_IDS", "") or "")
    ids = {int(x.strip()) for x in raw.replace(";", ",").split(",") if x.strip().isdigit()}
    return ids


def _candidate_roles(member: Any, bot_module: Any) -> list[Any]:
    ids = _hierarchy_ids(bot_module)
    roles = []
    for role in list(getattr(member, "roles", []) or []):
        rid = int(getattr(role, "id", 0) or 0)
        name = str(getattr(role, "name", "") or "").strip().lower()
        if rid and rid in ids:
            roles.append(role)
        elif rid and any(hint in name for hint in _NAME_HINTS) and "bot" not in name:
            roles.append(role)
    return [r for r in roles if getattr(r, "name", "") != "@everyone"]


def _highest_role(member: Any, bot_module: Any) -> Optional[Any]:
    roles = _candidate_roles(member, bot_module)
    if not roles:
        return None
    return max(roles, key=lambda r: int(getattr(r, "position", 0) or 0))


def _qra(bot_module: Any, member: Any) -> str:
    for name in ("_qra_por_membro", "_qra_por_usuario", "obter_qra", "get_qra"):
        fn = getattr(bot_module, name, None)
        if callable(fn):
            try:
                value = fn(member)
                if value:
                    return str(value)
            except Exception:
                pass
    try:
        state = getattr(bot_module, "_v173_central_data_state", {})
        for kind in ("procurados", "boletins", "pericias"):
            for row in state.get(kind, []) if isinstance(state, dict) else []:
                if str(row.get("discord_id")) == str(member.id) or str(row.get("user_id")) == str(member.id):
                    for key in ("qra", "QRA"):
                        if row.get(key):
                            return str(row[key])
    except Exception:
        pass
    return "Não identificado"


async def _audit_actor(guild: Any, member_id: int) -> Optional[Any]:
    try:
        import discord
        now = datetime.now(timezone.utc)
        async for entry in guild.audit_logs(limit=8, action=discord.AuditLogAction.member_role_update):
            if int(getattr(getattr(entry, "target", None), "id", 0) or 0) != member_id:
                continue
            created = getattr(entry, "created_at", None)
            if created is not None and abs((now - created).total_seconds()) <= 30:
                return getattr(entry, "user", None)
    except Exception:
        pass
    return None


def _event_key(member_id: int, before_role: Optional[Any], after_role: Optional[Any], audit_id: Any = None) -> str:
    if audit_id:
        return f"audit:{audit_id}"
    return f"roles:{member_id}:{getattr(before_role, 'id', 0)}:{getattr(after_role, 'id', 0)}"


def _format_message(kind: str, member: Any, before_role: Any, after_role: Any, qra: str, actor: Any) -> str:
    data = datetime.now().astimezone().strftime("%d/%m/%Y às %H:%M")
    responsavel = str(actor) if actor is not None else "Sistema DICOR"
    if kind == "promocao":
        return (
            "🏅 PROMOÇÃO DE CARGO\n\n\n"
            f"👤 Oficial: {member.mention}\n"
            f"📋 QRA: {qra}\n"
            f"⬆️ Cargo anterior: {before_role.name}\n"
            f"🏅 Novo cargo: {after_role.name}\n\n"
            f"Após análise e avaliação interna, fica registrada a promoção do(a) oficial ao cargo de {after_role.name}.\n\n"
            "A promoção reconhece o desempenho, comprometimento e conduta apresentados durante o período de atuação.\n\n"
            f"📅 Data: {data}\n"
            f"👮 Responsável: {responsavel}\n\n"
            "────────────────────────────\n"
            "🔒 DICOR — Gestão da DICOR"
        )
    return (
        "⚠️ REBAIXAMENTO DE CARGO\n\n\n"
        f"👤 Oficial: {member.mention}\n"
        f"📋 QRA: {qra}\n"
        f"⬇️ Cargo anterior: {before_role.name}\n"
        f"📉 Novo cargo: {after_role.name}\n\n"
        f"Fica registrado o rebaixamento do(a) oficial ao cargo de {after_role.name}, conforme decisão administrativa interna.\n\n"
        "A alteração passa a valer imediatamente após a publicação deste comunicado.\n\n"
        f"📅 Data: {data}\n"
        f"👮 Responsável: {responsavel}\n\n"
        "────────────────────────────\n"
        "🔒 DICOR — Gestão da DICOR"
    )


async def _refresh_existing_hierarchy(bot_module: Any, guild: Any) -> bool:
    """Tenta reaproveitar o mecanismo de hierarquia já existente."""
    candidates = (
        "_v72_atualizar_hierarquia", "_v72_publicar_hierarquia", "atualizar_hierarquia",
        "publicar_hierarquia", "_atualizar_hierarquia", "rebuild_hierarquia",
        "atualizar_painel_hierarquia",
    )
    for name in candidates:
        fn = getattr(bot_module, name, None)
        if not callable(fn):
            continue
        try:
            sig = inspect.signature(fn)
            argc = len([p for p in sig.parameters.values() if p.default is inspect._empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])
            if argc == 0:
                result = fn()
            else:
                result = fn(guild)
            if inspect.isawaitable(result):
                await result
            return True
        except Exception:
            continue
    return False


async def _mirror_hierarchy(bot_module: Any, guild: Any) -> None:
    client = getattr(bot_module, "bot", None)
    channel_id = int(getattr(bot_module, "HIERARQUIA_CHANNEL_ID", 0) or 0)
    if client is None or not channel_id:
        return
    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except Exception:
            return
    members: list[tuple[Any, Any]] = []
    for member in list(getattr(guild, "members", []) or []):
        if getattr(member, "bot", False):
            continue
        role = _highest_role(member, bot_module)
        if role is not None:
            members.append((member, role))
    members.sort(key=lambda pair: (-int(getattr(pair[1], "position", 0) or 0), str(getattr(pair[0], "display_name", ""))))
    lines = [_MARKER, "🏛️ **HIERARQUIA DICOR**", "", "Atualização automática após movimentação de cargo.", ""]
    last_role = None
    for member, role in members:
        if last_role != role.id:
            lines += [f"**{role.name}**"]
            last_role = role.id
        lines.append(f"• {member.mention}")
    content = "\n".join(lines)[:3900]
    try:
        async for message in channel.history(limit=50):
            if getattr(message.author, "id", None) == getattr(client.user, "id", None) and _MARKER in str(getattr(message, "content", "")):
                await message.edit(content=content, allowed_mentions=None)
                return
    except Exception:
        return
    try:
        await channel.send(content=content, allowed_mentions=None)
    except Exception:
        pass


async def _publish(bot_module: Any, member: Any, before_role: Any, after_role: Any, kind: str, actor: Any, key: str) -> None:
    history = _load_history(bot_module)
    eventos = history.setdefault("eventos", [])
    if any(str(e.get("key")) == key for e in eventos if isinstance(e, dict)):
        return
    qra = _qra(bot_module, member)
    channel_id = PROMOCOES_CHANNEL_ID if kind == "promocao" else REBAIXAMENTOS_CHANNEL_ID
    client = getattr(bot_module, "bot", None)
    if client is None:
        return
    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except Exception as exc:
            print(f"⚠️ [GESTAO] canal {channel_id} indisponível: {type(exc).__name__}", flush=True)
            return
    content = _format_message(kind, member, before_role, after_role, qra, actor)
    try:
        await channel.send(content, allowed_mentions=None)
    except Exception as exc:
        print(f"⚠️ [GESTAO] comunicado não enviado: {type(exc).__name__}: {exc}", flush=True)
        return
    eventos.append({
        "key": key,
        "tipo": kind,
        "member_id": int(member.id),
        "cargo_anterior_id": int(before_role.id),
        "cargo_anterior": str(before_role.name),
        "novo_cargo_id": int(after_role.id),
        "novo_cargo": str(after_role.name),
        "qra": qra,
        "responsavel_id": int(getattr(actor, "id", 0) or 0),
        "responsavel": str(actor) if actor is not None else "Sistema DICOR",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    history["eventos"] = eventos[-500:]
    _save_history(bot_module, history)


async def _on_member_update(before: Any, after: Any) -> None:
    bot_module = _BOT_MODULE
    try:
        if getattr(after, "bot", False):
            return
        before_role = _highest_role(before, bot_module)
        after_role = _highest_role(after, bot_module)
        if before_role is None and after_role is None:
            return
        if before_role is not None and after_role is not None and int(before_role.id) == int(after_role.id):
            return
        if before_role is None or after_role is None:
            return
        if int(before_role.position) == int(after_role.position):
            return
        kind = "promocao" if int(after_role.position) > int(before_role.position) else "rebaixamento"
        actor = await _audit_actor(getattr(after, "guild", None), int(after.id))
        audit_id = None
        try:
            import discord
            guild = getattr(after, "guild", None)
            if guild is not None:
                async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.member_role_update):
                    if int(getattr(getattr(entry, "target", None), "id", 0) or 0) == int(after.id):
                        audit_id = getattr(entry, "id", None)
                        break
        except Exception:
            pass
        key = _event_key(int(after.id), before_role, after_role, audit_id)
        async with _LOCK:
            await _publish(bot_module, after, before_role, after_role, kind, actor, key)
            refreshed = await _refresh_existing_hierarchy(bot_module, getattr(after, "guild", None))
            if not refreshed:
                await _mirror_hierarchy(bot_module, getattr(after, "guild", None))
        print(f"✅ [GESTAO] {kind}: {after} | {before_role.name} -> {after_role.name}", flush=True)
    except Exception as exc:
        print(f"⚠️ [GESTAO] evento isolado: {type(exc).__name__}: {exc}", flush=True)


async def install(bot_module: Any) -> bool:
    global _INSTALLED, _BOT_MODULE
    if _INSTALLED:
        return True
    client = getattr(bot_module, "bot", None)
    if client is None:
        return False
    _BOT_MODULE = bot_module
    client.add_listener(_on_member_update, "on_member_update")
    _INSTALLED = True
    print("✅ [GESTAO] promoções, rebaixamentos e atualização automática da hierarquia ativos.", flush=True)
    return True


_BOT_MODULE: Any = None
