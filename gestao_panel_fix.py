# -*- coding: utf-8 -*-
"""Ajuste final da Gestão DICOR: painel visual + canal correto da hierarquia."""
from __future__ import annotations

import asyncio
import unicodedata
from typing import Any, Optional

import discord

MANAGEMENT_NAMES = (
    "criterios-de-up",
    "criterios de up",
    "gestao-dicor",
    "gestao dicor",
    "gestao",
    "painel-gestao",
)
HIERARCHY_NAMES = (
    "hierarquia",
    "hierarquia-dicor",
    "hierarquia dicor",
)

_INSTALLED = False


def _norm(value: Any) -> str:
    return unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower().replace("-", " ").strip()


async def _get_named_channel(client: Any, guild: Any, names: tuple[str, ...]) -> Optional[Any]:
    wanted = {_norm(name) for name in names}
    for channel in list(getattr(guild, "text_channels", []) or []):
        if _norm(getattr(channel, "name", "")) in wanted:
            return channel
    return None


async def _get_hierarchy_channel(client: Any, guild: Any) -> Optional[Any]:
    channel = await _get_named_channel(client, guild, HIERARCHY_NAMES)
    if channel is not None:
        return channel
    configured = int(getattr(_BOT_MODULE, "HIERARQUIA_CHANNEL_ID", 0) or 0)
    if configured:
        channel = client.get_channel(configured)
        if channel is not None and _norm(getattr(channel, "name", "")) in {_norm(x) for x in HIERARCHY_NAMES}:
            return channel
        if channel is None:
            try:
                channel = await client.fetch_channel(configured)
            except Exception:
                channel = None
            if channel is not None and _norm(getattr(channel, "name", "")) in {_norm(x) for x in HIERARCHY_NAMES}:
                return channel
    return None


async def _get_management_channel(client: Any, guild: Any) -> Optional[Any]:
    return await _get_named_channel(client, guild, MANAGEMENT_NAMES)


def _panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🔐 GESTÃO DICOR",
        description="Painel oficial de movimentação do efetivo.\n\nSelecione uma ação para continuar.",
        colour=discord.Colour.gold(),
    )
    embed.add_field(
        name="⬆️ PROMOÇÕES",
        value="🥉 Estagiário → Investigador\n🔹 Investigador → Inspetor",
        inline=True,
    )
    embed.add_field(
        name="⬇️ REBAIXAMENTOS",
        value="🛡️ Inspetor → Investigador\n🔹 Investigador → 🥉 Estagiário",
        inline=True,
    )
    embed.add_field(
        name="🔒 QUEM PODE ALTERAR",
        value="🛡️ Inspetor • 🎖️ Vice-Diretor • 👑 Diretor",
        inline=False,
    )
    embed.set_footer(text="DICOR • Gestão de efetivo")
    return embed


async def _ensure_panel(bot_module: Any, guild: Any) -> None:
    client = getattr(bot_module, "bot", None)
    if client is None:
        return
    channel = await _get_management_channel(client, guild)
    if channel is None:
        print(f"⚠️ [GESTAO] canal do painel não encontrado em {getattr(guild, 'id', '?')}", flush=True)
        return

    embed = _panel_embed()
    button_ids = {
        "dicor:gestao:v2:promover:estagiario",
        "dicor:gestao:v2:promover:investigador",
        "dicor:gestao:v2:rebaixar:inspetor",
        "dicor:gestao:v2:rebaixar:investigador",
        "dicor:gestao:v3:promover:estagiario",
        "dicor:gestao:v3:promover:investigador",
        "dicor:gestao:v3:rebaixar:inspetor",
        "dicor:gestao:v3:rebaixar:investigador",
    }
    try:
        async for message in channel.history(limit=100):
            if getattr(getattr(message, "author", None), "id", None) != getattr(client.user, "id", None):
                continue
            content = str(getattr(message, "content", ""))
            embeds = list(getattr(message, "embeds", []) or [])
            footer = " ".join(str(getattr(getattr(e, "footer", None), "text", "")) for e in embeds)
            found_ids = {
                str(getattr(child, "custom_id", ""))
                for row in list(getattr(message, "components", []) or [])
                for child in list(getattr(row, "children", []) or [])
                if getattr(child, "custom_id", None)
            }
            legacy = any(marker in content or marker in footer for marker in ("DICOR_GESTAO_V2", "DICOR_GESTAO_PAINEL", "DICOR_GESTAO_V3"))
            titled = any("GESTÃO DICOR" in str(getattr(e, "title", "")) for e in embeds)
            if legacy or titled or found_ids.intersection(button_ids):
                await message.edit(
                    content="",
                    embed=embed,
                    view=_GESTAO_VIEW(),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                print(f"✅ [GESTAO] painel atualizado no canal #{getattr(channel, 'name', '?')}.", flush=True)
                return
    except Exception as exc:
        print(f"⚠️ [GESTAO] leitura do painel: {type(exc).__name__}: {exc}", flush=True)
        return

    try:
        await channel.send(
            embed=embed,
            view=_GESTAO_VIEW(),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        print(f"✅ [GESTAO] painel criado no canal #{getattr(channel, 'name', '?')}.", flush=True)
    except Exception as exc:
        print(f"⚠️ [GESTAO] criação do painel: {type(exc).__name__}: {exc}", flush=True)


async def install(bot_module: Any) -> bool:
    global _INSTALLED, _BOT_MODULE, _GESTAO_VIEW
    _BOT_MODULE = bot_module
    if _INSTALLED:
        return True
    client = getattr(bot_module, "bot", None)
    if client is None:
        return False

    try:
        import gestao_v3
        _GESTAO_VIEW = gestao_v3.GestaoV3Painel
        gestao_v3._get_hierarchy_channel = _get_hierarchy_channel
    except Exception as exc:
        print(f"⚠️ [GESTAO] patch V3: {type(exc).__name__}: {exc}", flush=True)
        return False

    _INSTALLED = True
    for guild in list(getattr(client, "guilds", []) or []):
        asyncio.create_task(_ensure_panel(bot_module, guild), name=f"dicor-gestao-panel-final-{getattr(guild, 'id', 0)}")
        asyncio.create_task(_refresh(guild), name=f"dicor-hierarchy-final-{getattr(guild, 'id', 0)}")
    print("✅ [GESTAO] painel final aplicado; critérios preservados e hierarquia direcionada para #hierarquia.", flush=True)
    return True


async def _refresh(guild: Any) -> None:
    try:
        import gestao_v3
        await gestao_v3.refresh_hierarchy(guild)
    except Exception as exc:
        print(f"⚠️ [HIERARQUIA] refresh final: {type(exc).__name__}: {exc}", flush=True)


_BOT_MODULE: Any = None
_GESTAO_VIEW: Any = None
