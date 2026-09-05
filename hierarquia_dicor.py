# -*- coding: utf-8 -*-
"""Hierarquia oficial DICOR.

Os IDs dos cargos e dos usuários são tratados separadamente:
- os IDs fornecidos para os cargos ocupados são IDs dos USUÁRIOS a marcar;
- o ID 1490200383614615725 é o ID do CARGO Vice-Diretor DICOR e nunca é marcado.
"""
from __future__ import annotations

import discord
from discord import app_commands

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


def _user_mention(guild: discord.Guild, user_id: int) -> str:
    # O ID é de usuário: a marcação correta é <@ID>.
    member = guild.get_member(user_id)
    return f"<@{member.id if member is not None else user_id}>"


def _vice_diretor_mention(guild: discord.Guild) -> str:
    # Aqui usamos o ID do CARGO somente para descobrir quem o possui.
    # Nunca retornamos <@cargo_id>.
    role = guild.get_role(VICE_DIRETOR_ROLE_ID)
    if role is not None:
        members = list(getattr(role, "members", []) or [])
        if members:
            return ", ".join(f"<@{member.id}>" for member in members)
    return "Sem ocupante cadastrado"


def _build_description(guild: discord.Guild) -> str:
    u = CURRENT_USER_IDS
    return (
        "👑 **ALTO COMANDO**\n\n"
        f"🥇 Delegado Geral — {_user_mention(guild, u['delegado_geral'])}\n"
        f"🥇 Delegado Adjunto — {_user_mention(guild, u['delegado_adjunto'])}\n\n"
        "🧠 **COMANDO DICOR**\n\n"
        f"🥇 Diretor DICOR — {_user_mention(guild, u['diretor_dicor'])}\n"
        f"🥇 Vice-Diretor DICOR — {_vice_diretor_mention(guild)}\n"
        f"🥇 Inspetor DICOR — {_user_mention(guild, u['inspetor_dicor'])}\n\n"
        "🔎 **SETOR INVESTIGATIVO**\n\n"
        f"🕵️ DICOR - Investigador — {_user_mention(guild, u['investigador'])}\n\n"
        "📡 **BASE OPERACIONAL**\n\n"
        f"👨‍✈️ DICOR - Estagiário — {_user_mention(guild, u['estagiario'])}\n\n"
        "----------------------------------------------\n\n"
        "⚖️ **OBSERVAÇÕES GERAIS**\n\n"
        "▪ A hierarquia deve ser respeitada em todas as operações\n"
        "▪ Ordens superiores devem ser seguidas\n"
        "▪ Quebra de hierarquia pode resultar em punição\n"
        "▪ Toda ação deve ser reportada conforme o protocolo DICOR\n\n"
        "📍 **DICOR - Capital Morada Valley**"
    )


def _embed(guild: discord.Guild) -> discord.Embed:
    return discord.Embed(
        title="🏛️ HIERARQUIA OFICIAL - DICOR 🏛️",
        description=_build_description(guild),
        color=discord.Color.dark_grey(),
    )


async def install(bot_module) -> None:
    client = getattr(bot_module, "bot", None)
    tree = getattr(client, "tree", None) if client else None
    if client is None or tree is None:
        raise RuntimeError("cliente Discord/CommandTree não encontrado")

    async def hierarchy_callback(interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "❌ Este comando só pode ser usado dentro do servidor.", ephemeral=True
            )
            return
        await interaction.response.send_message(embed=_embed(guild))

    existing = tree.get_command("hierarquia")
    if existing is not None:
        existing.callback = hierarchy_callback
        print("✅ Hierarquia DICOR atualizada no comando existente.", flush=True)
        return

    command = app_commands.Command(
        name="hierarquia",
        description="Exibe a hierarquia oficial da DICOR.",
        callback=hierarchy_callback,
    )
    tree.add_command(command)
    try:
        await tree.sync()
    except Exception as exc:
        print(
            f"⚠️ Hierarquia: falha ao sincronizar comando: {type(exc).__name__}: {exc}",
            flush=True,
        )
    else:
        print("✅ Comando /hierarquia registrado.", flush=True)
