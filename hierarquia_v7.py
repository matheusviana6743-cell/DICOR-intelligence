# -*- coding: utf-8 -*-
"""Hierarquia DICOR dinâmica.

Os ocupantes são sempre lidos dos cargos reais do Discord; nenhum usuário é fixado no código.
"""
from __future__ import annotations

import asyncio
import re
import unicodedata
from typing import Any, Optional

import discord

CHANNEL_NAME = "hierarquia"
MARKER = "DICOR_HIERARQUIA_V7"
VICE_DIRETOR_ROLE_ID = 1490200383614615725
_BOT_MODULE: Any = None
_INSTALLED = False
_TASKS: dict[int, asyncio.Task] = {}

RANKS = [
    ("👑", "Delegado Geral", ("delegado", "geral"), ("adjunto", "vice")),
    ("👑", "Delegado Adjunto", ("delegado", "adjunto"), ()),
    ("🎖️", "Diretor DICOR", ("diretor", "dicor"), ("vice",)),
    ("🎖️", "Vice-Diretor DICOR", ("diretor", "vice"), ()),
    ("🛡️", "Inspetor DICOR", ("inspetor",), ()),
    ("🔎", "Investigador DICOR", ("investigador",), ()),
    ("📡", "Estagiário DICOR", ("estagiario",), ()),
]


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _find_role(guild: Any, include: tuple[str, ...], exclude: tuple[str, ...] = ()) -> Optional[Any]:
    wanted = [_norm(x) for x in include]
    blocked = [_norm(x) for x in exclude]
    candidates = []
    for role in getattr(guild, "roles", []) or []:
        name = _norm(getattr(role, "name", ""))
        if name and all(x in name for x in wanted) and not any(x in name for x in blocked):
            candidates.append(role)
    return max(candidates, key=lambda r: int(getattr(r, "position", 0) or 0), default=None)


def _members(guild: Any, role: Any) -> list[Any]:
    if role is None:
        return []
    rid = int(getattr(role, "id", 0) or 0)
    found = {}
    for member in getattr(guild, "members", []) or []:
        if getattr(member, "bot", False):
            continue
        if any(int(getattr(r, "id", 0) or 0) == rid for r in getattr(member, "roles", []) or []):
            found[int(member.id)] = member
    return sorted(found.values(), key=lambda m: _norm(getattr(m, "display_name", "")))


def _block(guild: Any, icon: str, title: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> str:
    if title.startswith("Vice-Diretor"):
        role = guild.get_role(VICE_DIRETOR_ROLE_ID)
    else:
        role = _find_role(guild, include, exclude)
    members = _members(guild, role)
    text = ", ".join(m.mention for m in members) if members else "— Nenhum ocupante"
    return f"{icon} **{title}**\n{text}"


def build_embed(guild: Any) -> discord.Embed:
    embed = discord.Embed(
        title="🏛️ HIERARQUIA OFICIAL — DICOR",
        description="Efetivo atual sincronizado diretamente com os cargos do Discord.",
        color=discord.Color.gold(),
    )
    embed.add_field(name="👑 ALTO COMANDO", value=(
        _block(guild, "🥇", "Delegado Geral", ("delegado", "geral"), ("adjunto", "vice"))
        + "\n\n" + _block(guild, "🥈", "Delegado Adjunto", ("delegado", "adjunto"), ())
    )[:1024], inline=False)
    embed.add_field(name="🧠 COMANDO DICOR", value=(
        _block(guild, "🎖️", "Diretor DICOR", ("diretor", "dicor"), ("vice",))
        + "\n\n" + _block(guild, "🎖️", "Vice-Diretor DICOR", ("diretor", "vice"), ())
        + "\n\n" + _block(guild, "🛡️", "Inspetor DICOR", ("inspetor",), ())
    )[:1024], inline=False)
    embed.add_field(name="🔎 SETOR INVESTIGATIVO", value=_block(guild, "🕵️", "Investigador DICOR", ("investigador",), ())[:1024], inline=False)
    embed.add_field(name="📡 BASE OPERACIONAL", value=_block(guild, "🧑‍🎓", "Estagiário DICOR", ("estagiario",), ())[:1024], inline=False)
    embed.set_footer(text=f"DICOR • {MARKER}")
    return embed


async def _channel(client: Any, guild: Any) -> Optional[Any]:
    configured = int(getattr(_BOT_MODULE, "HIERARQUIA_CHANNEL_ID", 0) or 0)
    if configured:
        ch = client.get_channel(configured)
        if ch is not None and "hierarquia" in _norm(getattr(ch, "name", "")):
            return ch
    for ch in getattr(guild, "text_channels", []) or []:
        if _norm(getattr(ch, "name", "")) == CHANNEL_NAME:
            return ch
    for ch in getattr(guild, "text_channels", []) or []:
        name = _norm(getattr(ch, "name", ""))
        if "hierarquia" in name and "criterios" not in name and "gestao" not in name:
            return ch
    return None


async def refresh_hierarchy(guild: Any) -> None:
    client = getattr(_BOT_MODULE, "bot", None)
    if client is None or guild is None:
        return
    channel = await _channel(client, guild)
    if channel is None:
        print("⚠️ [HIERARQUIA V7] canal #hierarquia não encontrado.", flush=True)
        return
    embed = build_embed(guild)
    try:
        async for message in channel.history(limit=100):
            if getattr(getattr(message, "author", None), "id", None) != getattr(client.user, "id", None):
                continue
            if any(MARKER in str(getattr(getattr(e, "footer", None), "text", "")) for e in getattr(message, "embeds", []) or []):
                await message.edit(content="", embed=embed, allowed_mentions=discord.AllowedMentions.none())
                return
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except Exception as exc:
        print(f"⚠️ [HIERARQUIA V7] atualização: {type(exc).__name__}: {exc}", flush=True)


def schedule(guild: Any, delay: float = 0.5) -> None:
    if guild is None:
        return
    gid = int(getattr(guild, "id", 0) or 0)
    task = _TASKS.get(gid)
    if task and not task.done():
        return
    async def runner() -> None:
        await asyncio.sleep(delay)
        await refresh_hierarchy(guild)
    _TASKS[gid] = asyncio.create_task(runner(), name=f"dicor-hierarchy-v7-{gid}")


async def _on_member_update(before: Any, after: Any) -> None:
    if getattr(after, "bot", False):
        return
    before_ids = {int(getattr(r, "id", 0) or 0) for r in getattr(before, "roles", []) or []}
    after_ids = {int(getattr(r, "id", 0) or 0) for r in getattr(after, "roles", []) or []}
    if before_ids != after_ids:
        schedule(getattr(after, "guild", None))


async def install(bot_module: Any) -> bool:
    global _BOT_MODULE, _INSTALLED
    _BOT_MODULE = bot_module
    client = getattr(bot_module, "bot", None)
    if client is None:
        return False
    if not _INSTALLED:
        try:
            client.add_listener(_on_member_update, "on_member_update")
        except Exception:
            pass
        _INSTALLED = True
        print("✅ [HIERARQUIA V7] leitura dinâmica de cargos ativa.", flush=True)
    if bool(getattr(client, "is_ready", lambda: False)()):
        for guild in list(getattr(client, "guilds", []) or []):
            schedule(guild, 0.3)
    return True
