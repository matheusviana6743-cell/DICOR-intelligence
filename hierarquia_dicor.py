# -*- coding: utf-8 -*-
"""Hierarquia oficial DICOR.

Publica/atualiza UMA mensagem no canal #hierarquia e nunca publica no
#criterios-de-up. IDs de usuários são usados para marcação; o ID do cargo
Vice-Diretor é usado apenas para descobrir o ocupante.
"""
from __future__ import annotations

import asyncio
import re
import unicodedata
from typing import Any, Optional

import discord
from discord import app_commands

HIERARCHY_NAMES = {"hierarquia", "hierarquia-dicor", "hierarquia dicor"}
PANEL_NAMES = {"criterios-de-up", "criterios de up", "gestao", "gestao-dicor", "gestao dicor"}
HIERARCHY_MARKER = "DICOR_HIERARQUIA_OFICIAL_V5"

# ID DO CARGO Vice-Diretor DICOR — nunca marcar este ID como usuário.
VICE_DIRETOR_ROLE_ID = 1490200383614615725

# IDs DOS USUÁRIOS atualmente ocupando os demais cargos.
CURRENT_USER_IDS = {
    "delegado_geral": 1490200384818647051,
    "delegado_adjunto": 527894944904511498,
    "diretor_dicor": 1490200382776021132,
    "inspetor_dicor": 1490200388912156692,
    "investigador": 1490200390426165290,
    "estagiario": 1490200391239864352,
}

_INSTALLED = False
_BOT_MODULE: Any = None
_REFRESH_TASKS: dict[int, asyncio.Task] = {}


def _norm(value: Any) -> str:
    return unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower().replace("-", " ").strip()


def _user_mention(user_id: int) -> str:
    return f"<@{int(user_id)}>"


def _role_members(guild: Any, role_id: int) -> list[Any]:
    role = guild.get_role(role_id) if guild is not None else None
    if role is None:
        return []
    found: dict[int, Any] = {}
    for member in list(getattr(role, "members", []) or []):
        if not getattr(member, "bot", False):
            found[int(member.id)] = member
    for member in list(getattr(guild, "members", []) or []):
        if getattr(member, "bot", False):
            continue
        if any(int(getattr(r, "id", 0) or 0) == role_id for r in list(getattr(member, "roles", []) or [])):
            found[int(member.id)] = member
    return sorted(found.values(), key=lambda m: _norm(getattr(m, "display_name", "")))


def _vice_diretor_mention(guild: Any) -> str:
    members = _role_members(guild, VICE_DIRETOR_ROLE_ID)
    if members:
        return ", ".join(m.mention for m in members)
    return "Sem ocupante cadastrado"


def _entry(label: str, user_id: int) -> str:
    return f"{label} — {_user_mention(user_id)}"


def _build_description(guild: Any) -> str:
    u = CURRENT_USER_IDS
    return (
        "👑 **ALTO COMANDO**\n\n"
        f"🥇 {_entry('Delegado Geral', u['delegado_geral']).split(' — ', 1)[0]} — {_user_mention(u['delegado_geral'])}\n"
        f"🥇 Delegado Adjunto — {_user_mention(u['delegado_adjunto'])}\n\n"
        "🧠 **COMANDO DICOR**\n\n"
        f"🥇 Diretor DICOR — {_user_mention(u['diretor_dicor'])}\n"
        f"🥇 Vice-Diretor DICOR — {_vice_diretor_mention(guild)}\n"
        f"🥇 Inspetor DICOR — {_user_mention(u['inspetor_dicor'])}\n\n"
        "🔎 **SETOR INVESTIGATIVO**\n\n"
        f"🕵️ DICOR - Investigador — {_user_mention(u['investigador'])}\n\n"
        "📡 **BASE OPERACIONAL**\n\n"
        f"👨‍✈️ DICOR - Estagiário — {_user_mention(u['estagiario'])}\n\n"
        "----------------------------------------------\n\n"
        "⚖️ **OBSERVAÇÕES GERAIS**\n\n"
        "▪ A hierarquia deve ser respeitada em todas as operações\n"
        "▪ Ordens superiores devem ser seguidas\n"
        "▪ Quebra de hierarquia pode resultar em punição\n"
        "▪ Toda ação deve ser reportada conforme o protocolo DICOR\n\n"
        "📍 **DICOR - Capital Morada Valley**"
    )


def _embed(guild: Any) -> discord.Embed:
    embed = discord.Embed(
        title="🏛️ HIERARQUIA OFICIAL - DICOR 🏛️",
        description=_build_description(guild),
        color=discord.Color.dark_grey(),
    )
    embed.set_footer(text=HIERARCHY_MARKER)
    return embed


async def _get_hierarchy_channel(client: Any, guild: Any) -> Optional[Any]:
    configured = int(getattr(_BOT_MODULE, "HIERARQUIA_CHANNEL_ID", 0) or 0)
    if configured:
        channel = client.get_channel(configured)
        if channel is None:
            try:
                channel = await client.fetch_channel(configured)
            except Exception:
                channel = None
        if channel is not None and _norm(getattr(channel, "name", "")) in {_norm(x) for x in HIERARCHY_NAMES}:
            return channel

    for channel in list(getattr(guild, "text_channels", []) or []):
        name = _norm(getattr(channel, "name", ""))
        if name in {_norm(x) for x in HIERARCHY_NAMES}:
            return channel
    return None


async def refresh_hierarchy(guild: Any) -> None:
    client = getattr(_BOT_MODULE, "bot", None)
    if client is None or guild is None:
        return
    channel = await _get_hierarchy_channel(client, guild)
    if channel is None:
        print(f"⚠️ [HIERARQUIA] canal próprio não encontrado em {getattr(guild, 'id', '?')}", flush=True)
        return

    embed = _embed(guild)
    try:
        async for message in channel.history(limit=100):
            if getattr(getattr(message, "author", None), "id", None) != getattr(client.user, "id", None):
                continue
            embeds = list(getattr(message, "embeds", []) or [])
            footer = " ".join(str(getattr(getattr(e, "footer", None), "text", "")) for e in embeds)
            title = " ".join(str(getattr(e, "title", "")) for e in embeds)
            if HIERARCHY_MARKER in footer or "HIERARQUIA OFICIAL" in title:
                await message.edit(content="", embed=embed, allowed_mentions=discord.AllowedMentions.none())
                return

        # Cria somente no canal de hierarquia. Nunca usa #criterios-de-up.
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except Exception as exc:
        print(f"⚠️ [HIERARQUIA] render: {type(exc).__name__}: {exc}", flush=True)


def _schedule_refresh(guild: Any, delay: float = 1.0) -> None:
    if guild is None:
        return
    gid = int(getattr(guild, "id", 0) or 0)
    old = _REFRESH_TASKS.get(gid)
    if old and not old.done():
        return

    async def runner() -> None:
        await asyncio.sleep(delay)
        await refresh_hierarchy(guild)

    _REFRESH_TASKS[gid] = asyncio.create_task(runner(), name=f"dicor-hierarchy-{gid}")


async def _on_member_update(before: Any, after: Any) -> None:
    if _norm(getattr(before, "roles", "")) == _norm(getattr(after, "roles", "")):
        return
    _schedule_refresh(getattr(after, "guild", None))


async def _legacy_hierarchy_bridge(*_args: Any, **_kwargs: Any) -> None:
    client = getattr(_BOT_MODULE, "bot", None)
    for guild in list(getattr(client, "guilds", []) or []):
        _schedule_refresh(guild, delay=0)


async def install(bot_module: Any) -> None:
    global _INSTALLED, _BOT_MODULE
    _BOT_MODULE = bot_module
    client = getattr(bot_module, "bot", None)
    tree = getattr(client, "tree", None) if client else None
    if client is None:
        raise RuntimeError("cliente Discord não encontrado")

    # Substitui pontes antigas para que nenhuma rotina volte a publicar hierarquia
    # em #criterios-de-up.
    for name in (
        "enviar_hierarquia_substituindo_anterior",
        "atualizar_hierarquia",
        "publicar_hierarquia",
        "rebuild_hierarquia",
        "atualizar_painel_hierarquia",
    ):
        try:
            setattr(bot_module, name, _legacy_hierarchy_bridge)
        except Exception:
            pass

    if not _INSTALLED:
        try:
            client.add_listener(_on_member_update, "on_member_update")
        except Exception:
            pass
        _INSTALLED = True

        if tree is not None:
            async def hierarchy_callback(interaction: discord.Interaction):
                guild = interaction.guild
                if guild is None:
                    await interaction.response.send_message("❌ Use este comando dentro do servidor.", ephemeral=True)
                    return
                await interaction.response.send_message(embed=_embed(guild), allowed_mentions=discord.AllowedMentions.none())

            existing = tree.get_command("hierarquia")
            if existing is not None:
                existing.callback = hierarchy_callback
            else:
                tree.add_command(app_commands.Command(
                    name="hierarquia",
                    description="Exibe a hierarquia oficial da DICOR.",
                    callback=hierarchy_callback,
                ))
                try:
                    await tree.sync()
                except Exception as exc:
                    print(f"⚠️ [HIERARQUIA] sync: {type(exc).__name__}: {exc}", flush=True)

    for guild in list(getattr(client, "guilds", []) or []):
        _schedule_refresh(guild, delay=0.5)
    print("✅ [HIERARQUIA] canal próprio ativo; #criterios-de-up não recebe hierarquia/painel automaticamente.", flush=True)
