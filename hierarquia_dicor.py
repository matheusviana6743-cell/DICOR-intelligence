# -*- coding: utf-8 -*-
"""Hierarquia oficial DICOR.

A hierarquia é mantida em um único lugar e o renderer antigo de gestão é
redirecionado para este módulo. IDs de usuários são marcados; o ID do cargo
Vice-Diretor serve apenas para localizar o ocupante.
"""
from __future__ import annotations

import asyncio
import unicodedata
from typing import Any, Optional

import discord
from discord import app_commands

HIERARCHY_NAMES = {"hierarquia", "hierarquia-dicor", "hierarquia dicor"}
HIERARCHY_MARKER = "DICOR_HIERARQUIA_OFICIAL_V6"
VICE_DIRETOR_ROLE_ID = 1490200383614615725

# ESTES SÃO IDs DE USUÁRIOS e devem ser marcados na mensagem.
CURRENT_USER_IDS = {
    "delegado_geral": 1490200384818647051,
    "delegado_adjunto": 527894944904511498,
    "diretor_dicor": 1490200382776021132,
    "inspetor_dicor": 1490200388912156692,
    "investigador": 1490200390426165290,
    "estagiario": 1490200391239864352,
}

_BOT_MODULE: Any = None
_INSTALLED = False
_REFRESH_TASKS: dict[int, asyncio.Task] = {}


def _norm(value: Any) -> str:
    return unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower().replace("-", " ").strip()


def _mention(user_id: int) -> str:
    return f"<@{int(user_id)}>"


def _vice_diretor(guild: Any) -> str:
    # 1490200383614615725 é CARGO, não usuário. Nunca gerar <@1490200383614615725>.
    role = guild.get_role(VICE_DIRETOR_ROLE_ID) if guild is not None else None
    if role is None:
        return "Sem ocupante cadastrado"
    members = [m for m in list(getattr(role, "members", []) or []) if not getattr(m, "bot", False)]
    if not members:
        # Fallback para guild.members, caso role.members ainda não esteja populado.
        for member in list(getattr(guild, "members", []) or []):
            if getattr(member, "bot", False):
                continue
            if any(int(getattr(r, "id", 0) or 0) == VICE_DIRETOR_ROLE_ID for r in list(getattr(member, "roles", []) or [])):
                members.append(member)
    if not members:
        return "Sem ocupante cadastrado"
    return ", ".join(member.mention for member in members)


def build_hierarchy(guild: Any) -> discord.Embed:
    u = CURRENT_USER_IDS
    text = (
        "👑 **ALTO COMANDO**\n\n"
        f"🥇 Delegado Geral — {_mention(u['delegado_geral'])}\n"
        f"🥇 Delegado Adjunto — {_mention(u['delegado_adjunto'])}\n\n"
        "🧠 **COMANDO DICOR**\n\n"
        f"🥇 Diretor DICOR — {_mention(u['diretor_dicor'])}\n"
        f"🥇 Vice-Diretor DICOR — {_vice_diretor(guild)}\n"
        f"🥇 Inspetor DICOR — {_mention(u['inspetor_dicor'])}\n\n"
        "🔎 **SETOR INVESTIGATIVO**\n\n"
        f"🕵️ DICOR - Investigador — {_mention(u['investigador'])}\n\n"
        "📡 **BASE OPERACIONAL**\n\n"
        f"👨‍✈️ DICOR - Estagiário — {_mention(u['estagiario'])}\n\n"
        "----------------------------------------------\n\n"
        "⚖️ **OBSERVAÇÕES GERAIS**\n\n"
        "▪ A hierarquia deve ser respeitada em todas as operações\n"
        "▪ Ordens superiores devem ser seguidas\n"
        "▪ Quebra de hierarquia pode resultar em punição\n"
        "▪ Toda ação deve ser reportada conforme o protocolo DICOR\n\n"
        "📍 **DICOR - Capital Morada Valley**"
    )
    return discord.Embed(title="🏛️ HIERARQUIA OFICIAL - DICOR 🏛️", description=text, color=discord.Color.dark_grey()).set_footer(text=HIERARCHY_MARKER)


async def _get_channel(client: Any, guild: Any) -> Optional[Any]:
    configured = int(getattr(_BOT_MODULE, "HIERARQUIA_CHANNEL_ID", 0) or 0)
    if configured:
        channel = client.get_channel(configured)
        if channel is None:
            try:
                channel = await client.fetch_channel(configured)
            except Exception:
                channel = None
        if channel is not None:
            return channel
    for channel in list(getattr(guild, "text_channels", []) or []):
        if _norm(getattr(channel, "name", "")) in {_norm(x) for x in HIERARCHY_NAMES}:
            return channel
    return None


async def refresh_hierarchy(guild: Any) -> None:
    client = getattr(_BOT_MODULE, "bot", None)
    if client is None or guild is None:
        return
    channel = await _get_channel(client, guild)
    if channel is None:
        return
    embed = build_hierarchy(guild)
    try:
        async for message in channel.history(limit=100):
            if getattr(getattr(message, "author", None), "id", None) != getattr(client.user, "id", None):
                continue
            embeds = list(getattr(message, "embeds", []) or [])
            footer = " ".join(str(getattr(getattr(e, "footer", None), "text", "")) for e in embeds)
            title = " ".join(str(getattr(e, "title", "")) for e in embeds)
            if HIERARCHY_MARKER in footer or "HIERARQUIA OFICIAL" in title:
                await message.edit(content="", embed=embed, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
                return
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
    except Exception as exc:
        print(f"⚠️ [HIERARQUIA] {type(exc).__name__}: {exc}", flush=True)


def _schedule(guild: Any, delay: float = 0.5) -> None:
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
    before_ids = {int(getattr(r, "id", 0) or 0) for r in list(getattr(before, "roles", []) or [])}
    after_ids = {int(getattr(r, "id", 0) or 0) for r in list(getattr(after, "roles", []) or [])}
    if before_ids != after_ids:
        _schedule(getattr(after, "guild", None))


def _disable_automatic_panel_publish() -> None:
    # O painel de Gestão DICOR NÃO deve ser criado/enviado durante o boot.
    try:
        import gestao_v2
        async def _noop(*_args: Any, **_kwargs: Any) -> None:
            return None
        for name in ("_ensure_panel", "_upgrade_panel", "_upgrade_existing_panel", "ensure_panel", "refresh_panel"):
            if hasattr(gestao_v2, name):
                setattr(gestao_v2, name, _noop)
    except Exception:
        pass
    try:
        import gestao_v3
        async def _noop(*_args: Any, **_kwargs: Any) -> None:
            return None
        for name in ("_ensure_panel", "_upgrade_panel", "_upgrade_existing_panel", "ensure_panel", "refresh_panel", "_publish_panel", "_post_panel"):
            if hasattr(gestao_v3, name):
                setattr(gestao_v3, name, _noop)
        # Se o renderer V3 tentar gerar a hierarquia, força o renderer oficial.
        if hasattr(gestao_v3, "_hierarchy_embed"):
            gestao_v3._hierarchy_embed = build_hierarchy
        if hasattr(gestao_v3, "refresh_hierarchy"):
            gestao_v3.refresh_hierarchy = refresh_hierarchy
    except Exception:
        pass


async def install(bot_module: Any) -> None:
    global _BOT_MODULE, _INSTALLED
    _BOT_MODULE = bot_module
    client = getattr(bot_module, "bot", None)
    tree = getattr(client, "tree", None) if client else None
    if client is None:
        raise RuntimeError("cliente Discord não encontrado")

    _disable_automatic_panel_publish()

    if not _INSTALLED:
        try:
            client.add_listener(_on_member_update, "on_member_update")
        except Exception:
            pass
        if tree is not None:
            async def callback(interaction: discord.Interaction):
                if interaction.guild is None:
                    await interaction.response.send_message("❌ Use este comando dentro do servidor.", ephemeral=True)
                    return
                await interaction.response.send_message(embed=build_hierarchy(interaction.guild), allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
            existing = tree.get_command("hierarquia")
            if existing is not None:
                existing.callback = callback
            else:
                tree.add_command(app_commands.Command(name="hierarquia", description="Exibe a hierarquia oficial da DICOR.", callback=callback))
        _INSTALLED = True

    for guild in list(getattr(client, "guilds", []) or []):
        _schedule(guild)
    print("✅ [HIERARQUIA] renderer oficial ativo; painel de gestão não é publicado automaticamente.", flush=True)
