# -*- coding: utf-8 -*-
"""Hotfix seguro da Gestão DICOR.

Corrige dois problemas sem duplicar a lógica de gestão:
1) hierarquia estava sendo publicada no canal errado quando o ID configurado apontava
   para #criterios-de-up;
2) remove mensagens de hierarquia criadas pelo próprio bot no canal do painel.

A implementação usa o canal #hierarquia pelo nome quando o ID configurado estiver
errado/inconsistente e mantém o painel de gestão separado.
"""
from __future__ import annotations

import asyncio
import os
import re
import unicodedata
from typing import Any, Optional

import discord

_INSTALLED = False
_BOT_MODULE: Any = None


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _is_hierarchy_channel(channel: Any) -> bool:
    name = _norm(getattr(channel, "name", ""))
    if not name:
        return False
    return "hierarquia" in name and "criterios" not in name and "gestao" not in name


def _resolve_hierarchy_channel(bot_module: Any, guild: Any) -> Optional[Any]:
    client = getattr(bot_module, "bot", None)
    if client is None or guild is None:
        return None

    # 1. Variável explícita, mas só aceita se o canal realmente for a hierarquia.
    for raw in (os.getenv("DICOR_HIERARQUIA_CHANNEL_ID", ""), getattr(bot_module, "HIERARQUIA_CHANNEL_ID", 0)):
        try:
            channel_id = int(raw or 0)
        except (TypeError, ValueError):
            channel_id = 0
        if not channel_id:
            continue
        channel = client.get_channel(channel_id)
        if channel is not None and _is_hierarchy_channel(channel):
            return channel

    # 2. Descoberta por nome, evitando explicitamente #criterios-de-up.
    channels = list(getattr(guild, "channels", []) or [])
    exact = [c for c in channels if _norm(getattr(c, "name", "")) == "hierarquia"]
    if exact:
        return exact[0]
    candidates = [c for c in channels if _is_hierarchy_channel(c)]
    if candidates:
        return candidates[0]
    return None


def _role_members(guild: Any, role: Any) -> list[Any]:
    if role is None:
        return []
    result = []
    role_id = getattr(role, "id", None)
    for member in list(getattr(guild, "members", []) or []):
        if getattr(member, "bot", False):
            continue
        if any(getattr(r, "id", None) == role_id for r in getattr(member, "roles", []) or []):
            result.append(member)
    result.sort(key=lambda m: _norm(getattr(m, "display_name", "")))
    return result


def _find_role(guild: Any, *parts: str) -> Optional[Any]:
    wanted = [_norm(p) for p in parts if p]
    exact = []
    partial = []
    for role in list(getattr(guild, "roles", []) or []):
        name = _norm(getattr(role, "name", ""))
        if not name or name == "everyone":
            continue
        if all(p in name for p in wanted):
            exact.append(role)
        elif any(p in name for p in wanted):
            partial.append(role)
    return max(exact or partial, key=lambda r: int(getattr(r, "position", 0) or 0), default=None)


def _build_embed(guild: Any) -> discord.Embed:
    embed = discord.Embed(
        title="🏛️ HIERARQUIA OFICIAL — DICOR",
        description="Estrutura atual do efetivo • atualização automática após cada alteração de cargo.",
        color=0xC9A227,
    )

    sections = [
        (
            "👑 ALTO COMANDO",
            [
                ("🥇 Delegado Geral", _find_role(guild, "delegado geral")),
                ("🥈 Delegado Adjunto", _find_role(guild, "delegado adjunto")),
            ],
        ),
        (
            "🧠 COMANDO DICOR",
            [
                ("🎖️ Diretor DICOR", _find_role(guild, "diretor dicor")),
                ("🎖️ Vice-Diretor DICOR", _find_role(guild, "vice diretor dicor")),
                ("🛡️ Inspetor DICOR", _find_role(guild, "inspetor")),
            ],
        ),
        (
            "🔎 SETOR INVESTIGATIVO",
            [("🕵️ Investigador", _find_role(guild, "investigador"))],
        ),
        (
            "📡 BASE OPERACIONAL",
            [("🧑‍🎓 Estagiário", _find_role(guild, "estagiario"))],
        ),
    ]

    for section_name, entries in sections:
        blocks = []
        for label, role in entries:
            members = _role_members(guild, role)
            if members:
                blocks.append(f"**{label}**\n" + "\n".join(f"• {m.mention}" for m in members))
            else:
                blocks.append(f"**{label}**\n• Nenhum ocupante")
        embed.add_field(name=section_name, value="\n\n".join(blocks)[:1024], inline=False)

    embed.add_field(
        name="⚖️ OBSERVAÇÕES",
        value=(
            "A ordem acompanha os cargos reais do servidor. "
            "Promoções e rebaixamentos atualizam este painel automaticamente."
        ),
        inline=False,
    )
    embed.set_footer(text="DICOR • HIERARQUIA OFICIAL")
    return embed


async def _refresh_hierarchy(bot_module: Any, guild: Any) -> None:
    if guild is None:
        return
    client = getattr(bot_module, "bot", None)
    channel = _resolve_hierarchy_channel(bot_module, guild)
    if client is None or channel is None:
        print("⚠️ [HIERARQUIA V4] canal #hierarquia não localizado; atualização ignorada.", flush=True)
        return

    embed = _build_embed(guild)
    try:
        async for message in channel.history(limit=80):
            if getattr(getattr(message, "author", None), "id", None) != getattr(client.user, "id", None):
                continue
            if any("HIERARQUIA OFICIAL" in str(getattr(e, "title", "")) for e in getattr(message, "embeds", []) or []):
                await message.edit(content="", embed=embed, allowed_mentions=discord.AllowedMentions.none())
                return
            if "DICOR_HIERARQUIA_ATUAL" in str(getattr(message, "content", "")):
                await message.edit(content="", embed=embed, allowed_mentions=discord.AllowedMentions.none())
                return
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except Exception as exc:
        print(f"⚠️ [HIERARQUIA V4] render: {type(exc).__name__}: {exc}", flush=True)


async def _cleanup_wrong_hierarchy_messages(bot_module: Any) -> None:
    client = getattr(bot_module, "bot", None)
    if client is None:
        return
    try:
        for guild in list(getattr(client, "guilds", []) or []):
            for channel in list(getattr(guild, "channels", []) or []):
                # O canal do painel não deve receber o painel de hierarquia.
                name = _norm(getattr(channel, "name", ""))
                if "criterios de up" not in name and "criterios-de-up" not in name:
                    continue
                try:
                    async for message in channel.history(limit=80):
                        if getattr(getattr(message, "author", None), "id", None) != getattr(client.user, "id", None):
                            continue
                        content = str(getattr(message, "content", ""))
                        embed_titles = [str(getattr(e, "title", "")) for e in getattr(message, "embeds", []) or []]
                        if "DICOR_HIERARQUIA_ATUAL" in content or any("HIERARQUIA OFICIAL" in title for title in embed_titles):
                            try:
                                await message.delete()
                                print(f"✅ [HIERARQUIA V4] mensagem indevida removida de #{getattr(channel, 'name', '?')}", flush=True)
                            except Exception:
                                pass
                except Exception:
                    continue
    except Exception as exc:
        print(f"⚠️ [HIERARQUIA V4] limpeza: {type(exc).__name__}: {exc}", flush=True)


def _patch_gestao_v2(bot_module: Any) -> None:
    try:
        import gestao_v2
        gestao_v2._refresh_hierarchy = _refresh_hierarchy
    except Exception as exc:
        print(f"⚠️ [GESTAO V4] patch gestao_v2: {type(exc).__name__}: {exc}", flush=True)


async def install(bot_module: Any) -> bool:
    global _INSTALLED, _BOT_MODULE
    if _INSTALLED:
        return True
    _BOT_MODULE = bot_module
    _patch_gestao_v2(bot_module)
    await _cleanup_wrong_hierarchy_messages(bot_module)
    _INSTALLED = True
    print("✅ [GESTAO V4] hierarquia separada do painel; #criterios-de-up mantido somente para gestão.", flush=True)
    return True
