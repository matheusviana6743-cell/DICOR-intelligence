# -*- coding: utf-8 -*-
"""Hierarquia oficial DICOR.

Os IDs abaixo são IDs de CARGOS do Discord. A mensagem nunca marca o cargo;
ela consulta os membros que possuem cada cargo e marca os USUÁRIOS encontrados.
"""
from __future__ import annotations

import discord
from discord import app_commands

# IDs DE CARGOS — não são IDs de usuários.
ROLE_IDS = {
    "delegado_geral": 1490200384818647051,
    "delegado_adjunto": 527894944904511498,
    "diretor_dicor": 1490200382776021132,
    "vice_diretor_dicor": 1490200383614615725,
    "inspetor_dicor": 1490200388912156692,
    "investigador": 1490200390426165290,
    "estagiario": 1490200391239864352,
}

# IDs atuais conhecidos dos ocupantes. Servem somente como fallback caso o
# cache de membros ainda não esteja populado no momento da renderização.
CURRENT_USER_IDS = {
    "delegado_geral": 1490200384818647051,
    "delegado_adjunto": 527894944904511498,
    "diretor_dicor": 1490200382776021132,
    "inspetor_dicor": 1490200388912156692,
    "investigador": 1490200390426165290,
    "estagiario": 1490200391239864352,
}


def _mentions_for_role(guild: discord.Guild, role_id: int, fallback_user_id: int | None = None) -> str:
    role = guild.get_role(role_id)
    if role is not None:
        members = list(getattr(role, "members", []) or [])
        if members:
            return ", ".join(f"<@{member.id}>" for member in members)
    if fallback_user_id:
        member = guild.get_member(fallback_user_id)
        if member is not None:
            return f"<@{member.id}>"
    return "Sem ocupante cadastrado"


def _build_description(guild: discord.Guild) -> str:
    r = ROLE_IDS
    u = CURRENT_USER_IDS
    return (
        "👑 **ALTO COMANDO**\n\n"
        f"🥇 Delegado Geral — {_mentions_for_role(guild, r['delegado_geral'], u.get('delegado_geral'))}\n"
        f"🥇 Delegado Adjunto — {_mentions_for_role(guild, r['delegado_adjunto'], u.get('delegado_adjunto'))}\n\n"
        "🧠 **COMANDO DICOR**\n\n"
        f"🥇 Diretor DICOR — {_mentions_for_role(guild, r['diretor_dicor'], u.get('diretor_dicor'))}\n"
        f"🥇 Vice-Diretor DICOR — {_mentions_for_role(guild, r['vice_diretor_dicor'], u.get('vice_diretor_dicor'))}\n"
        f"🥇 Inspetor DICOR — {_mentions_for_role(guild, r['inspetor_dicor'], u.get('inspetor_dicor'))}\n\n"
        "🔎 **SETOR INVESTIGATIVO**\n\n"
        f"🕵️ DICOR - Investigador — {_mentions_for_role(guild, r['investigador'], u.get('investigador'))}\n\n"
        "📡 **BASE OPERACIONAL**\n\n"
        f"👨‍✈️ DICOR - Estagiário — {_mentions_for_role(guild, r['estagiario'], u.get('estagiario'))}\n\n"
        "----------------------------------------------\n\n"
        "⚖️ **OBSERVAÇÕES GERAIS**\n\n"
        "▪ A hierarquia deve ser respeitada em todas as operações\n"
        "▪ Ordens superiores devem ser seguidas\n"
        "▪ Quebra de hierarquia pode resultar em punição\n"
        "▪ Toda ação deve ser reportada conforme o protocolo DICOR\n\n"
        "📍 **DICOR - Capital Morada Valley**"
    )


def _embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🏛️ HIERARQUIA OFICIAL - DICOR 🏛️",
        description=_build_description(guild),
        color=discord.Color.dark_grey(),
    )
    return embed


async def install(bot_module) -> None:
    client = getattr(bot_module, "bot", None)
    tree = getattr(client, "tree", None) if client else None
    if client is None or tree is None:
        raise RuntimeError("cliente Discord/CommandTree não encontrado")

    async def hierarchy_callback(interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("❌ Este comando só pode ser usado dentro do servidor.", ephemeral=True)
            return
        await interaction.response.send_message(embed=_embed(guild))

    # Reaproveita o comando existente, se ele já estiver registrado.
    existing = tree.get_command("hierarquia")
    if existing is not None:
        existing.callback = hierarchy_callback
        print("✅ Hierarquia DICOR atualizada no comando existente.", flush=True)
        return

    # Caso não exista, cria o comando sem duplicar nada.
    command = app_commands.Command(
        name="hierarquia",
        description="Exibe a hierarquia oficial da DICOR.",
        callback=hierarchy_callback,
    )
    tree.add_command(command)
    try:
        await tree.sync()
    except Exception as exc:
        print(f"⚠️ Hierarquia: falha ao sincronizar comando: {type(exc).__name__}: {exc}", flush=True)
    else:
        print("✅ Comando /hierarquia registrado.", flush=True)
