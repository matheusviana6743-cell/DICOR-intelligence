# -*- coding: utf-8 -*-
"""Gestão DICOR V3.

- Não publica painel automaticamente.
- Mantém o painel existente; não cria mensagens novas de gestão.
- Hierarquia lê diretamente os cargos/membros reais do Discord.
- Atualiza a hierarquia após qualquer mudança de cargos.
- Redireciona geradores antigos para o renderer correto.
"""
from __future__ import annotations

import asyncio
import re
import unicodedata
from typing import Any, Optional

import discord

PANEL_NAMES = {"criterios-de-up", "criterios de up", "gestao", "gestao-dicor", "gestao dicor"}
HIERARCHY_NAMES = {"hierarquia", "hierarquia-dicor", "hierarquia dicor"}
PANEL_MARKER = "DICOR_GESTAO_V3"
HIERARCHY_MARKER = "DICOR_HIERARQUIA_V3"

ACTIONS = {
    "promover_estagiario": ("estagiario", "investigador", "⬆️ Estagiário → Investigador"),
    "promover_investigador": ("investigador", "inspetor", "⬆️ Investigador → Inspetor"),
    "rebaixar_inspetor": ("inspetor", "investigador", "⬇️ Inspetor → Investigador"),
    "rebaixar_investigador": ("investigador", "estagiario", "⬇️ Investigador → Estagiário"),
}

_INSTALLED = False
_BOT_MODULE: Any = None
_CHANGE_LOCK = asyncio.Lock()
_REFRESH_TASKS: dict[int, asyncio.Task] = {}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _rank(role: Any) -> str:
    name = _norm(getattr(role, "name", ""))
    if "estagiario" in name:
        return "estagiario"
    if "investigador" in name:
        return "investigador"
    if re.search(r"\binspetor\b", name):
        return "inspetor"
    return ""


def _managed_roles(member: Any) -> list[Any]:
    return [role for role in list(getattr(member, "roles", []) or []) if _rank(role)]


def _highest_managed_role(member: Any) -> Optional[Any]:
    return max(_managed_roles(member), key=lambda role: int(getattr(role, "position", 0) or 0), default=None)


def _find_rank_role(guild: Any, rank: str) -> Optional[Any]:
    roles = [role for role in list(getattr(guild, "roles", []) or []) if _rank(role) == rank]
    return max(roles, key=lambda role: int(getattr(role, "position", 0) or 0), default=None)


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
        if "inspetor" in name or "vice diretor" in name or "diretor" in name:
            return True
    return False


def _role_members(guild: Any, role: Any) -> list[Any]:
    if role is None:
        return []
    role_id = int(getattr(role, "id", 0) or 0)
    found: dict[int, Any] = {}
    for member in list(getattr(role, "members", []) or []):
        if not getattr(member, "bot", False):
            found[int(member.id)] = member
    for member in list(getattr(guild, "members", []) or []):
        if getattr(member, "bot", False):
            continue
        if any(int(getattr(member_role, "id", 0) or 0) == role_id for member_role in list(getattr(member, "roles", []) or [])):
            found[int(member.id)] = member
    return sorted(found.values(), key=lambda member: _norm(getattr(member, "display_name", "")))


def _find_named_role(guild: Any, include: tuple[str, ...], exclude: tuple[str, ...] = ()) -> Optional[Any]:
    wanted = [_norm(x) for x in include if x]
    blocked = [_norm(x) for x in exclude if x]
    matches = []
    for role in list(getattr(guild, "roles", []) or []):
        name = _norm(getattr(role, "name", ""))
        if not name or name == "everyone":
            continue
        if all(part in name for part in wanted) and not any(part in name for part in blocked):
            matches.append(role)
    return max(matches, key=lambda role: int(getattr(role, "position", 0) or 0), default=None)


def _members_block(guild: Any, label: str, include: tuple[str, ...], exclude: tuple[str, ...] = ()) -> str:
    role = _find_named_role(guild, include, exclude)
    members = _role_members(guild, role)
    return f"**{label}**\n" + ("\n".join(f"• {member.mention}" for member in members) if members else "— Nenhum ocupante")


def _hierarchy_embed(guild: Any) -> discord.Embed:
    embed = discord.Embed(
        title="🏛️ HIERARQUIA OFICIAL — DICOR",
        description="Efetivo atual lido diretamente dos cargos e membros do Discord.",
        colour=discord.Colour.gold(),
    )
    embed.add_field(name="👑 ALTO COMANDO", value=(
        _members_block(guild, "🥇 Delegado Geral", ("delegado", "geral"), ("adjunto", "vice"))
        + "\n\n" + _members_block(guild, "🥈 Delegado Adjunto", ("delegado", "adjunto"))
    )[:1024], inline=False)
    embed.add_field(name="🧠 COMANDO DICOR", value=(
        _members_block(guild, "🎖️ Diretor DICOR", ("dicor", "diretor"), ("vice",))
        + "\n\n" + _members_block(guild, "🎖️ Vice-Diretor DICOR", ("vice", "diretor"))
        + "\n\n" + _members_block(guild, "🛡️ Inspetor DICOR", ("inspetor",))
    )[:1024], inline=False)
    embed.add_field(name="🔎 SETOR INVESTIGATIVO", value=_members_block(guild, "🕵️ Investigador DICOR", ("investigador",))[:1024], inline=False)
    embed.add_field(name="📡 BASE OPERACIONAL", value=_members_block(guild, "🧑‍🎓 Estagiário DICOR", ("estagiario",))[:1024], inline=False)
    embed.set_footer(text=f"DICOR • {HIERARCHY_MARKER}")
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
        if channel is not None:
            return channel
    names = {_norm(name) for name in HIERARCHY_NAMES}
    for channel in list(getattr(guild, "text_channels", []) or []):
        if _norm(getattr(channel, "name", "")) in names:
            return channel
    return None


async def refresh_hierarchy(guild: Any) -> None:
    client = getattr(_BOT_MODULE, "bot", None)
    if client is None or guild is None:
        return
    channel = await _get_hierarchy_channel(client, guild)
    if channel is None:
        return
    embed = _hierarchy_embed(guild)
    try:
        async for message in channel.history(limit=100):
            if getattr(getattr(message, "author", None), "id", None) != getattr(client.user, "id", None):
                continue
            embeds = list(getattr(message, "embeds", []) or [])
            marked = any(HIERARCHY_MARKER in str(getattr(getattr(e, "footer", None), "text", "")) for e in embeds)
            titled = any("HIERARQUIA OFICIAL" in str(getattr(e, "title", "")) for e in embeds)
            legacy_text = "HIERARQUIA OFICIAL" in str(getattr(message, "content", ""))
            if marked or titled or legacy_text:
                await message.edit(content="", embed=embed, allowed_mentions=discord.AllowedMentions.none())
                return
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except Exception as exc:
        print(f"⚠️ [HIERARQUIA] render: {type(exc).__name__}: {exc}", flush=True)


def _schedule_refresh(guild: Any, delay: float = 0.8) -> None:
    if guild is None:
        return
    gid = int(getattr(guild, "id", 0) or 0)
    task = _REFRESH_TASKS.get(gid)
    if task and not task.done():
        return
    async def runner() -> None:
        await asyncio.sleep(delay)
        await refresh_hierarchy(guild)
    _REFRESH_TASKS[gid] = asyncio.create_task(runner(), name=f"dicor-hierarchy-{gid}")


async def _legacy_hierarchy_bridge(*_args: Any, **_kwargs: Any) -> None:
    client = getattr(_BOT_MODULE, "bot", None)
    for guild in list(getattr(client, "guilds", []) or []):
        await refresh_hierarchy(guild)


def _install_legacy_bridge(bot_module: Any) -> None:
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


def _install_v2_safety() -> None:
    try:
        import gestao_v2
        async def _noop(*_args: Any, **_kwargs: Any) -> None:
            return None
        gestao_v2._upgrade_existing_panel = _noop
        gestao_v2._upgrade_panel = _noop
    except Exception:
        pass


def _panel_exists(client: Any, guild: Any) -> bool:
    names = {_norm(name) for name in PANEL_NAMES}
    for channel in list(getattr(guild, "text_channels", []) or []):
        if _norm(getattr(channel, "name", "")) not in names:
            continue
        # We deliberately do not inspect/send here. Existing panel stays untouched.
        return True
    return False


async def _change(interaction: Any, action: str, member: Any) -> None:
    guild = getattr(interaction, "guild", None)
    if guild is None:
        await interaction.response.send_message("❌ Ação disponível somente dentro do servidor.", ephemeral=True)
        return
    if not _manager(getattr(interaction, "user", None), _BOT_MODULE):
        await interaction.response.send_message("❌ Apenas Inspetor, Vice-Diretor ou Diretor pode usar a Gestão.", ephemeral=True)
        return
    before_name, after_name, label = ACTIONS[action]
    before_role = _find_rank_role(guild, before_name)
    after_role = _find_rank_role(guild, after_name)
    current = _highest_managed_role(member)
    if before_role is None or after_role is None or current is None or _rank(current) != before_name:
        await interaction.response.send_message(f"❌ O membro selecionado precisa estar como **{getattr(before_role, 'name', before_name)}**.", ephemeral=True)
        return
    bot_member = getattr(guild, "me", None)
    bot_top = getattr(bot_member, "top_role", None) if bot_member else None
    if bot_top is not None and int(getattr(after_role, "position", 0) or 0) >= int(getattr(bot_top, "position", 0) or 0):
        await interaction.response.send_message("❌ O bot não pode atribuir esse cargo pela hierarquia do servidor.", ephemeral=True)
        return
    try:
        async with _CHANGE_LOCK:
            old_managed = _managed_roles(member)
            roles = [r for r in list(getattr(member, "roles", []) or []) if r not in old_managed and getattr(r, "name", "") != "@everyone"]
            roles.append(after_role)
            await member.edit(roles=roles, reason=f"DICOR Gestão: {label} por {interaction.user}")
            _schedule_refresh(guild)
        await interaction.response.send_message(f"✅ {member.mention} atualizado: **{before_role.name} → {after_role.name}**.", ephemeral=True)
    except Exception as exc:
        print(f"⚠️ [GESTAO] alteração: {type(exc).__name__}: {exc}", flush=True)
        try:
            await interaction.response.send_message("❌ Não foi possível alterar o cargo.", ephemeral=True)
        except Exception:
            pass


class _MemberSelect(discord.ui.UserSelect):
    def __init__(self, action: str):
        super().__init__(placeholder="Selecione o membro…", min_values=1, max_values=1, custom_id=f"dicor:gestao:v3:select:{action}")
        self.action = action

    async def callback(self, interaction: Any) -> None:
        try:
            selected = self.values[0]
            member = selected if hasattr(selected, "roles") else interaction.guild.get_member(int(getattr(selected, "id", 0) or 0))
            if member is None:
                await interaction.response.send_message("❌ Membro não encontrado.", ephemeral=True)
                return
            await _change(interaction, self.action, member)
        except Exception as exc:
            print(f"⚠️ [GESTAO] seleção: {type(exc).__name__}: {exc}", flush=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Ocorreu um erro ao processar a alteração.", ephemeral=True)
            except Exception:
                pass


class _SelectView(discord.ui.View):
    def __init__(self, action: str):
        super().__init__(timeout=180)
        self.add_item(_MemberSelect(action))


class GestaoV3Painel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: Any) -> bool:
        if not _manager(getattr(interaction, "user", None), _BOT_MODULE):
            try:
                await interaction.response.send_message("❌ Apenas Inspetor, Vice-Diretor ou Diretor pode usar este painel.", ephemeral=True)
            except Exception:
                pass
            return False
        return True

    @discord.ui.button(label="Estagiário → Investigador", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="dicor:gestao:v3:promover:estagiario", row=0)
    async def promover_estagiario(self, interaction: Any, _: discord.ui.Button) -> None:
        await interaction.response.send_message("Selecione o **Estagiário** que será promovido:", view=_SelectView("promover_estagiario"), ephemeral=True)

    @discord.ui.button(label="Investigador → Inspetor", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="dicor:gestao:v3:promover:investigador", row=0)
    async def promover_investigador(self, interaction: Any, _: discord.ui.Button) -> None:
        await interaction.response.send_message("Selecione o **Investigador** que será promovido:", view=_SelectView("promover_investigador"), ephemeral=True)

    @discord.ui.button(label="Inspetor → Investigador", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="dicor:gestao:v3:rebaixar:inspetor", row=1)
    async def rebaixar_inspetor(self, interaction: Any, _: discord.ui.Button) -> None:
        await interaction.response.send_message("Selecione o **Inspetor** que será rebaixado:", view=_SelectView("rebaixar_inspetor"), ephemeral=True)

    @discord.ui.button(label="Investigador → Estagiário", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="dicor:gestao:v3:rebaixar:investigador", row=1)
    async def rebaixar_investigador(self, interaction: Any, _: discord.ui.Button) -> None:
        await interaction.response.send_message("Selecione o **Investigador** que será rebaixado:", view=_SelectView("rebaixar_investigador"), ephemeral=True)


async def install(bot_module: Any) -> bool:
    global _INSTALLED, _BOT_MODULE
    _BOT_MODULE = bot_module
    client = getattr(bot_module, "bot", None)
    if client is None:
        return False
    _install_legacy_bridge(bot_module)
    _install_v2_safety()
    if _INSTALLED:
        return True
    try:
        client.add_view(GestaoV3Painel())
    except Exception as exc:
        print(f"⚠️ [GESTAO V3] View persistente: {type(exc).__name__}: {exc}", flush=True)
    try:
        client.add_listener(_on_member_update, "on_member_update")
    except Exception:
        pass
    _INSTALLED = True
    for guild in list(getattr(client, "guilds", []) or []):
        _schedule_refresh(guild, delay=1.0)
    print("✅ [GESTAO V3] hierarquia por membros reais; nenhum painel de gestão será publicado automaticamente.", flush=True)
    return True


V72PainelGestaoView = GestaoV3Painel
V72SelecionarMembro = _MemberSelect
V72SelecionarMembroView = _SelectView
