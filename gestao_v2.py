# -*- coding: utf-8 -*-
"""Gestão DICOR V2.

Mantém um único painel permanente no canal #critérios-de-up e atualiza
imediatamente a hierarquia após movimentações de cargo.
"""
from __future__ import annotations

import asyncio
import inspect
import re
import unicodedata
from typing import Any, Optional

import discord

PANEL_MARKER = "<!-- DICOR_GESTAO_V2 -->"
PANEL_CHANNEL_NAME = "criterios-de-up"
MANAGED_RANKS = ("estagiario", "investigador", "inspetor")
_ACTIONS = {
    "promover_estagiario": ("estagiario", "investigador", "⬆️ Estagiário → Investigador"),
    "promover_investigador": ("investigador", "inspetor", "⬆️ Investigador → Inspetor"),
    "rebaixar_inspetor": ("inspetor", "investigador", "⬇️ Inspetor → Investigador"),
    "rebaixar_investigador": ("investigador", "estagiario", "⬇️ Investigador → Estagiário"),
}
_INSTALLED = False
_REFRESH_TASK: Optional[asyncio.Task] = None
_CHANGE_LOCK = asyncio.Lock()


def _norm(text: Any) -> str:
    value = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def _rank(role: Any) -> str:
    name = _norm(getattr(role, "name", ""))
    if "estagiario" in name:
        return "estagiario"
    if "investigador" in name:
        return "investigador"
    if re.search(r"(?:^|-)inspetor(?:-|$)", name):
        return "inspetor"
    return ""


def _find_rank_role(guild: Any, rank: str) -> Optional[Any]:
    roles = [r for r in list(getattr(guild, "roles", []) or []) if _rank(r) == rank]
    return max(roles, key=lambda r: int(getattr(r, "position", 0) or 0), default=None)


def _manager(member: Any, bot_module: Any) -> bool:
    fn = getattr(bot_module, "usuario_e_administrador", None)
    if callable(fn):
        try:
            if bool(fn(member)):
                return True
        except Exception:
            pass
    for role in list(getattr(member, "roles", []) or []):
        name = _norm(getattr(role, "name", ""))
        if any(x in name for x in ("inspetor", "vice-diretor", "diretor")):
            return True
    return False


def _managed_roles(member: Any) -> list[Any]:
    return [r for r in list(getattr(member, "roles", []) or []) if _rank(r) in MANAGED_RANKS]


async def _refresh_hierarchy(bot_module: Any, guild: Any) -> None:
    for name in (
        "enviar_hierarquia_substituindo_anterior",
        "atualizar_hierarquia",
        "publicar_hierarquia",
        "rebuild_hierarquia",
        "atualizar_painel_hierarquia",
    ):
        fn = getattr(bot_module, name, None)
        if not callable(fn):
            continue
        try:
            result = fn()
            if inspect.isawaitable(result):
                await result
            print("✅ [HIERARQUIA] painel atualizado após alteração de cargo.", flush=True)
            return
        except Exception as exc:
            print(f"⚠️ [HIERARQUIA] {name} falhou: {type(exc).__name__}: {exc}", flush=True)


def _schedule_hierarchy_refresh(bot_module: Any, guild: Any) -> None:
    global _REFRESH_TASK
    if _REFRESH_TASK and not _REFRESH_TASK.done():
        return
    async def runner() -> None:
        await asyncio.sleep(0.4)
        await _refresh_hierarchy(bot_module, guild)
    _REFRESH_TASK = asyncio.create_task(runner(), name="dicor-hierarchy-refresh")


async def _do_change(interaction: Any, action: str, target_member: Any, bot_module: Any) -> None:
    before_name, after_name, label = _ACTIONS[action]
    guild = getattr(interaction, "guild", None)
    if guild is None:
        await interaction.response.send_message("❌ Esta ação precisa ser usada dentro do servidor.", ephemeral=True)
        return
    if not _manager(getattr(interaction, "user", None), bot_module):
        await interaction.response.send_message("❌ Apenas Inspetor, Vice-Diretor ou Diretor pode usar a Gestão.", ephemeral=True)
        return
    before_role = _find_rank_role(guild, before_name)
    after_role = _find_rank_role(guild, after_name)
    if before_role is None or after_role is None:
        await interaction.response.send_message(f"❌ Não encontrei os cargos necessários para {label}.", ephemeral=True)
        return
    current = _managed_roles(target_member)
    current_role = max(current, key=lambda r: int(getattr(r, "position", 0) or 0), default=None)
    if _rank(current_role) != before_name:
        await interaction.response.send_message(f"❌ O membro selecionado precisa estar como **{before_role.name}**.", ephemeral=True)
        return
    bot_member = getattr(guild, "me", None)
    bot_top = getattr(bot_member, "top_role", None) if bot_member else None
    if bot_top is not None and int(after_role.position) >= int(bot_top.position):
        await interaction.response.send_message("❌ O bot não possui hierarquia suficiente para aplicar esse cargo.", ephemeral=True)
        return
    try:
        async with _CHANGE_LOCK:
            old_managed = _managed_roles(target_member)
            new_roles = [r for r in list(getattr(target_member, "roles", []) or []) if r not in old_managed and getattr(r, "name", "") != "@everyone"]
            new_roles.append(after_role)
            await target_member.edit(roles=new_roles, reason=f"DICOR Gestão: {label} por {interaction.user}")
            _schedule_hierarchy_refresh(bot_module, guild)
        await interaction.response.send_message(f"✅ {target_member.mention} atualizado: **{before_role.name} → {after_role.name}**.", ephemeral=True)
    except Exception as exc:
        try:
            await interaction.response.send_message(f"❌ Não foi possível alterar o cargo: {type(exc).__name__}.", ephemeral=True)
        except Exception:
            pass
        print(f"⚠️ [GESTAO V2] alteração falhou: {type(exc).__name__}: {exc}", flush=True)


class MemberSelect(discord.ui.UserSelect):
    def __init__(self, action: str):
        super().__init__(placeholder="Selecione o membro…", min_values=1, max_values=1, custom_id=f"dicor:gestao:v2:select:{action}")
        self.action = action

    async def callback(self, interaction: Any) -> None:
        try:
            member = self.values[0]
            await _do_change(interaction, self.action, member, _BOT_MODULE)
        except Exception as exc:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Ocorreu um erro ao processar a alteração.", ephemeral=True)
            except Exception:
                pass
            print(f"⚠️ [GESTAO V2] select: {type(exc).__name__}: {exc}", flush=True)


class SelectView(discord.ui.View):
    def __init__(self, action: str):
        super().__init__(timeout=180)
        self.add_item(MemberSelect(action))


class GestaoV2Painel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: Any) -> bool:
        if _manager(getattr(interaction, "user", None), _BOT_MODULE):
            return True
        try:
            await interaction.response.send_message("❌ Apenas Inspetor, Vice-Diretor ou Diretor pode usar este painel.", ephemeral=True)
        except Exception:
            pass
        return False

    @discord.ui.button(label="Estagiário → Investigador", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="dicor:gestao:v2:promover:estagiario", row=0)
    async def promover_estagiario(self, interaction: Any, _: Any) -> None:
        await interaction.response.send_message("Selecione o **Estagiário** que será promovido:", view=SelectView("promover_estagiario"), ephemeral=True)

    @discord.ui.button(label="Investigador → Inspetor", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="dicor:gestao:v2:promover:investigador", row=0)
    async def promover_investigador(self, interaction: Any, _: Any) -> None:
        await interaction.response.send_message("Selecione o **Investigador** que será promovido:", view=SelectView("promover_investigador"), ephemeral=True)

    @discord.ui.button(label="Inspetor → Investigador", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="dicor:gestao:v2:rebaixar:inspetor", row=1)
    async def rebaixar_inspetor(self, interaction: Any, _: Any) -> None:
        await interaction.response.send_message("Selecione o **Inspetor** que será rebaixado:", view=SelectView("rebaixar_inspetor"), ephemeral=True)

    @discord.ui.button(label="Investigador → Estagiário", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="dicor:gestao:v2:rebaixar:investigador", row=1)
    async def rebaixar_investigador(self, interaction: Any, _: Any) -> None:
        await interaction.response.send_message("Selecione o **Investigador** que será rebaixado:", view=SelectView("rebaixar_investigador"), ephemeral=True)

    @discord.ui.button(label="Retirar da DICOR", emoji="🚫", style=discord.ButtonStyle.danger, custom_id="dicor:gestao:v2:retirar", row=2)
    async def retirar(self, interaction: Any, _: Any) -> None:
        old_view = getattr(_BOT_MODULE, "V141SelecionarMembroView", None)
        if callable(old_view):
            await interaction.response.send_message("Selecione o membro que será retirado da DICOR:", view=old_view("retirar"), ephemeral=True)
        else:
            await interaction.response.send_message("❌ Rotina de retirada indisponível.", ephemeral=True)


async def _manage_panel_location(bot_module: Any) -> None:
    """Corrige painéis V2 fora do canal certo e mantém um único painel no #critérios-de-up."""
    client = getattr(bot_module, "bot", None)
    if client is None:
        return
    target_channels = []
    for guild in list(getattr(client, "guilds", []) or []):
        target_channels.extend([c for c in list(getattr(guild, "text_channels", []) or []) if _norm(getattr(c, "name", "")) == PANEL_CHANNEL_NAME])
        # Apaga somente mensagens marcadas pelo V2 em qualquer canal que não seja o alvo.
        for channel in list(getattr(guild, "text_channels", []) or []):
            if _norm(getattr(channel, "name", "")) == PANEL_CHANNEL_NAME:
                continue
            try:
                async for message in channel.history(limit=30):
                    if getattr(getattr(message, "author", None), "id", None) == getattr(getattr(client, "user", None), "id", None) and PANEL_MARKER in str(getattr(message, "content", "")):
                        await message.delete()
            except Exception:
                pass
    if not target_channels:
        print("⚠️ [GESTAO V2] canal #critérios-de-up não encontrado; nenhum painel criado fora dele.", flush=True)
        return
    content = f"{PANEL_MARKER}\n🔐 **GESTÃO DICOR**\n\n🛡️ **Fluxo operacional de cargos**\n\n🥉 **Estagiário** → 🔹 **Investigador** → 🛡️ **Inspetor**\n\n⬆️ Promoções\n⬇️ Rebaixamentos\n🚫 Retirada da DICOR\n\n👮 **Podem operar:** Inspetor • Vice-Diretor • Diretor\n\nSelecione uma ação abaixo."
    embed = discord.Embed(title="GESTÃO DICOR", description="Painel operacional para movimentação de cargos.", color=0x273142)
    embed.add_field(name="HIERARQUIA", value="🥉 Estagiário\n🔹 Investigador\n🛡️ Inspetor\n👔 Vice-Diretor", inline=False)
    embed.add_field(name="AÇÕES", value="⬆️ Promoções\n⬇️ Rebaixamentos\n🚫 Retirada da DICOR", inline=False)
    embed.set_footer(text="DICOR • Gestão de efetivo")
    for channel in target_channels[:1]:
        try:
            found = None
            async for message in channel.history(limit=50):
                if getattr(getattr(message, "author", None), "id", None) == getattr(getattr(client, "user", None), "id", None) and PANEL_MARKER in str(getattr(message, "content", "")):
                    found = message
                    break
            if found:
                await found.edit(content=content, embed=embed, view=GestaoV2Painel(), allowed_mentions=None)
            else:
                await channel.send(content=content, embed=embed, view=GestaoV2Painel(), allowed_mentions=None)
            return
        except Exception as exc:
            print(f"⚠️ [GESTAO V2] painel: {type(exc).__name__}: {exc}", flush=True)


async def _on_member_update(before: Any, after: Any) -> None:
    try:
        if getattr(after, "bot", False):
            return
        if {getattr(r, "id", 0) for r in getattr(before, "roles", []) or []} != {getattr(r, "id", 0) for r in getattr(after, "roles", []) or []}:
            _schedule_hierarchy_refresh(_BOT_MODULE, getattr(after, "guild", None))
    except Exception as exc:
        print(f"⚠️ [HIERARQUIA] listener isolado: {type(exc).__name__}: {exc}", flush=True)


async def install(bot_module: Any) -> bool:
    global _INSTALLED, _BOT_MODULE
    if _INSTALLED:
        return True
    _BOT_MODULE = bot_module
    client = getattr(bot_module, "bot", None)
    if client is None:
        return False
    try:
        client.add_listener(_on_member_update, "on_member_update")
        client.add_view(GestaoV2Painel())
    except Exception as exc:
        print(f"⚠️ [GESTAO V2] instalação: {type(exc).__name__}: {exc}", flush=True)
    _INSTALLED = True
    await _manage_panel_location(bot_module)
    await _refresh_hierarchy(bot_module, getattr(client, "guilds", [None])[0] if getattr(client, "guilds", None) else None)
    print("✅ [GESTAO V2] painel único em #critérios-de-up; hierarquia sincronizada.", flush=True)
    return True


_BOT_MODULE: Any = None
