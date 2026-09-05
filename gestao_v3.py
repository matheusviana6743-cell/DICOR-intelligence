# -*- coding: utf-8 -*-
"""Gestao DICOR V3.

Painel de gestao reutilizavel, sem publicacao automatica.
Hierarquia atualizada a partir dos cargos reais e dos membros que os possuem.
"""
from __future__ import annotations

import asyncio
import re
import unicodedata
from typing import Any, Optional

import discord

PANEL_NAMES = {"criterios-de-up", "criterios de up", "gestao", "gestao dicor", "gestao-dicor"}
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
_CLEANUP_TASK: Optional[asyncio.Task] = None


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode().lower()
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


def _find_rank_role(guild: Any, rank: str) -> Optional[Any]:
    roles = [r for r in list(getattr(guild, "roles", []) or []) if _rank(r) == rank]
    return max(roles, key=lambda r: int(getattr(r, "position", 0) or 0), default=None)


def _managed_roles(member: Any) -> list[Any]:
    return [r for r in list(getattr(member, "roles", []) or []) if _rank(r)]


def _highest_managed_role(member: Any) -> Optional[Any]:
    return max(_managed_roles(member), key=lambda r: int(getattr(r, "position", 0) or 0), default=None)


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
        for member_role in list(getattr(member, "roles", []) or []):
            if int(getattr(member_role, "id", 0) or 0) == role_id:
                found[int(member.id)] = member
                break
    return sorted(found.values(), key=lambda m: _norm(getattr(m, "display_name", "")))


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
    return max(matches, key=lambda r: int(getattr(r, "position", 0) or 0), default=None)


def _members_block(guild: Any, label: str, include: tuple[str, ...], exclude: tuple[str, ...] = ()) -> str:
    role = _find_named_role(guild, include, exclude)
    members = _role_members(guild, role)
    if not members:
        return f"**{label}**\n— Nenhum ocupante"
    return f"**{label}**\n" + "\n".join(f"• {member.mention}" for member in members)


def _hierarchy_embed(guild: Any) -> discord.Embed:
    embed = discord.Embed(
        title="🏛️ HIERARQUIA OFICIAL — DICOR",
        description="Efetivo atual lido diretamente dos cargos e membros do Discord.",
        colour=discord.Colour.gold(),
    )
    embed.add_field(
        name="👑 ALTO COMANDO",
        value=(
            _members_block(guild, "🥇 Delegado Geral", ("delegado", "geral"), ("adjunto", "vice"))
            + "\n\n"
            + _members_block(guild, "🥈 Delegado Adjunto", ("delegado", "adjunto"))
        )[:1024],
        inline=False,
    )
    embed.add_field(
        name="🧠 COMANDO DICOR",
        value=(
            _members_block(guild, "🎖️ Diretor DICOR", ("dicor", "diretor"), ("vice",))
            + "\n\n"
            + _members_block(guild, "🎖️ Vice-Diretor DICOR", ("vice", "diretor"))
            + "\n\n"
            + _members_block(guild, "🛡️ Inspetor DICOR", ("inspetor",))
        )[:1024],
        inline=False,
    )
    embed.add_field(
        name="🔎 SETOR INVESTIGATIVO",
        value=_members_block(guild, "🕵️ Investigador DICOR", ("investigador",))[:1024],
        inline=False,
    )
    embed.add_field(
        name="📡 BASE OPERACIONAL",
        value=_members_block(guild, "🧑‍🎓 Estagiário DICOR", ("estagiario",))[:1024],
        inline=False,
    )
    embed.set_footer(text=f"DICOR • {HIERARCHY_MARKER}")
    return embed


async def _get_hierarchy_channel(client: Any, guild: Any) -> Optional[Any]:
    configured = int(getattr(_BOT_MODULE, "HIERARQUIA_CHANNEL_ID", 0) or 0)
    candidates = [c for c in (configured,) if c]
    for channel_id in candidates:
        channel = client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(channel_id)
            except Exception:
                channel = None
        if channel is not None:
            return channel
    normalized = {_norm(name) for name in HIERARCHY_NAMES}
    for channel in list(getattr(guild, "text_channels", []) or []):
        if _norm(getattr(channel, "name", "")) in normalized:
            return channel
    return None


async def refresh_hierarchy(guild: Any) -> None:
    client = getattr(_BOT_MODULE, "bot", None)
    if client is None or guild is None:
        return
    channel = await _get_hierarchy_channel(client, guild)
    if channel is None:
        print("⚠️ [HIERARQUIA] canal não encontrado.", flush=True)
        return

    embed = _hierarchy_embed(guild)
    try:
        async for message in channel.history(limit=100):
            if getattr(getattr(message, "author", None), "id", None) != getattr(client.user, "id", None):
                continue
            embeds = list(getattr(message, "embeds", []) or [])
            marked = any(HIERARCHY_MARKER in str(getattr(getattr(e, "footer", None), "text", "")) for e in embeds)
            titled = any("HIERARQUIA OFICIAL" in str(getattr(e, "title", "")) for e in embeds)
            if marked or titled or HIERARCHY_MARKER in str(getattr(message, "content", "")):
                await message.edit(content="", embed=embed, allowed_mentions=discord.AllowedMentions.none())
                return
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except Exception as exc:
        print(f"⚠️ [HIERARQUIA] render: {type(exc).__name__}: {exc}", flush=True)


def _schedule_refresh(guild: Any, delay: float = 0.7) -> None:
    if guild is None:
        return
    gid = int(getattr(guild, "id", 0) or 0)
    task = _REFRESH_TASKS.get(gid)
    if task and not task.done():
        return

    async def runner() -> None:
        await asyncio.sleep(delay)
        await refresh_hierarchy(guild)

    _REFRESH_TASKS[gid] = asyncio.create_task(runner(), name=f"dicor-hierarchy-refresh-{gid}")


async def _cleanup_unwanted_panels(bot_module: Any) -> None:
    client = getattr(bot_module, "bot", None)
    if client is None:
        return
    unwanted_markers = (PANEL_MARKER, "DICOR_GESTAO_PAINEL", "DICOR_GESTAO_V2")
    normalized_names = {_norm(name) for name in PANEL_NAMES}
    for guild in list(getattr(client, "guilds", []) or []):
        for channel in list(getattr(guild, "text_channels", []) or []):
            if _norm(getattr(channel, "name", "")) not in normalized_names:
                continue
            try:
                async for message in channel.history(limit=80):
                    if getattr(getattr(message, "author", None), "id", None) != getattr(client.user, "id", None):
                        continue
                    content = str(getattr(message, "content", ""))
                    components = list(getattr(message, "components", []) or [])
                    ids = {
                        str(getattr(child, "custom_id", ""))
                        for row in components
                        for child in list(getattr(row, "children", []) or [])
                        if getattr(child, "custom_id", None)
                    }
                    embeds = list(getattr(message, "embeds", []) or [])
                    embed_marked = any("GESTÃO DICOR" in str(getattr(e, "title", "")) for e in embeds)
                    if any(marker in content for marker in unwanted_markers) or any(x.startswith("dicor:gestao:v3:") for x in ids) or embed_marked:
                        try:
                            await message.delete()
                        except Exception:
                            pass
            except Exception as exc:
                print(f"⚠️ [GESTAO] limpeza do painel: {type(exc).__name__}: {exc}", flush=True)


async def _change(interaction: Any, action: str, member: Any) -> None:
    bot_module = _BOT_MODULE
    if not _manager(getattr(interaction, "user", None), bot_module):
        await interaction.response.send_message(
            "❌ Apenas **Inspetor, Vice-Diretor ou Diretor** pode usar a Gestão.",
            ephemeral=True,
        )
        return
    guild = getattr(interaction, "guild", None)
    if guild is None:
        await interaction.response.send_message("❌ Ação disponível somente dentro do servidor.", ephemeral=True)
        return

    before_name, after_name, label = ACTIONS[action]
    before_role = _find_rank_role(guild, before_name)
    after_role = _find_rank_role(guild, after_name)
    if before_role is None or after_role is None:
        await interaction.response.send_message(f"❌ Não encontrei os cargos necessários para **{label}**.", ephemeral=True)
        return

    current = _highest_managed_role(member)
    if current is None or _rank(current) != before_name:
        await interaction.response.send_message(
            f"❌ O membro selecionado precisa estar como **{before_role.name}**.",
            ephemeral=True,
        )
        return

    bot_member = getattr(guild, "me", None)
    bot_top = getattr(bot_member, "top_role", None) if bot_member else None
    if bot_top is not None and int(getattr(after_role, "position", 0) or 0) >= int(getattr(bot_top, "position", 0) or 0):
        await interaction.response.send_message("❌ O bot não pode atribuir esse cargo pela hierarquia do servidor.", ephemeral=True)
        return

    try:
        async with _CHANGE_LOCK:
            old_managed = _managed_roles(member)
            new_roles = [
                role for role in list(getattr(member, "roles", []) or [])
                if role not in old_managed and getattr(role, "name", "") != "@everyone"
            ]
            new_roles.append(after_role)
            await member.edit(roles=new_roles, reason=f"DICOR Gestão: {label} por {interaction.user}")
            _schedule_refresh(guild)
        await interaction.response.send_message(
            f"✅ {member.mention} atualizado: **{before_role.name} → {after_role.name}**.",
            ephemeral=True,
        )
    except Exception as exc:
        print(f"⚠️ [GESTAO] alteração de cargo: {type(exc).__name__}: {exc}", flush=True)
        try:
            await interaction.response.send_message("❌ Não foi possível alterar o cargo.", ephemeral=True)
        except Exception:
            pass


class _MemberSelect(discord.ui.UserSelect):
    def __init__(self, action: str):
        super().__init__(
            placeholder="Selecione o membro…",
            min_values=1,
            max_values=1,
            custom_id=f"dicor:gestao:v3:select:{action}",
        )
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
    """Painel reutilizável. A instalação NÃO publica mensagem automaticamente."""

    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: Any) -> bool:
        if _manager(getattr(interaction, "user", None), _BOT_MODULE):
            return True
        try:
            await interaction.response.send_message(
                "❌ Apenas Inspetor, Vice-Diretor ou Diretor pode usar este painel.",
                ephemeral=True,
            )
        except Exception:
            pass
        return False

    @discord.ui.button(label="Estagiário → Investigador", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="dicor:gestao:v3:promover:estagiario", row=0)
    async def promover_estagiario(self, interaction: Any, _: Any) -> None:
        await interaction.response.send_message("Selecione o **Estagiário** que será promovido:", view=_SelectView("promover_estagiario"), ephemeral=True)

    @discord.ui.button(label="Investigador → Inspetor", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="dicor:gestao:v3:promover:investigador", row=0)
    async def promover_investigador(self, interaction: Any, _: Any) -> None:
        await interaction.response.send_message("Selecione o **Investigador** que será promovido:", view=_SelectView("promover_investigador"), ephemeral=True)

    @discord.ui.button(label="Inspetor → Investigador", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="dicor:gestao:v3:rebaixar:inspetor", row=1)
    async def rebaixar_inspetor(self, interaction: Any, _: Any) -> None:
        await interaction.response.send_message("Selecione o **Inspetor** que será rebaixado:", view=_SelectView("rebaixar_inspetor"), ephemeral=True)

    @discord.ui.button(label="Investigador → Estagiário", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="dicor:gestao:v3:rebaixar:investigador", row=1)
    async def rebaixar_investigador(self, interaction: Any, _: Any) -> None:
        await interaction.response.send_message("Selecione o **Investigador** que será rebaixado:", view=_SelectView("rebaixar_investigador"), ephemeral=True)


async def _on_member_update(before: Any, after: Any) -> None:
    try:
        if getattr(after, "bot", False):
            return
        before_ids = {int(getattr(role, "id", 0) or 0) for role in list(getattr(before, "roles", []) or [])}
        after_ids = {int(getattr(role, "id", 0) or 0) for role in list(getattr(after, "roles", []) or [])}
        if before_ids != after_ids:
            _schedule_refresh(getattr(after, "guild", None))
    except Exception as exc:
        print(f"⚠️ [HIERARQUIA] listener: {type(exc).__name__}: {exc}", flush=True)


async def _on_ready_once() -> None:
    client = getattr(_BOT_MODULE, "bot", None)
    if client is None:
        return
    for guild in list(getattr(client, "guilds", []) or []):
        _schedule_refresh(guild, delay=1.2)
    await _cleanup_unwanted_panels(_BOT_MODULE)


async def _cleanup_delayed() -> None:
    await asyncio.sleep(3)
    await _cleanup_unwanted_panels(_BOT_MODULE)


async def _install_v2_safety(bot_module: Any) -> None:
    """Impede que a implementação V2 volte a publicar o painel automaticamente."""
    try:
        import gestao_v2
        async def _noop_upgrade(*_args: Any, **_kwargs: Any) -> None:
            return None
        gestao_v2._upgrade_existing_panel = _noop_upgrade
        gestao_v2._upgrade_panel = _noop_upgrade
    except Exception:
        pass


async def install(bot_module: Any) -> bool:
    global _INSTALLED, _BOT_MODULE, _CLEANUP_TASK
    _BOT_MODULE = bot_module
    client = getattr(bot_module, "bot", None)
    if client is None:
        return False
    if _INSTALLED:
        return True

    await _install_v2_safety(bot_module)

    try:
        client.add_view(GestaoV3Painel())
    except Exception as exc:
        print(f"⚠️ [GESTAO V3] View persistente: {type(exc).__name__}: {exc}", flush=True)

    try:
        client.add_listener(_on_member_update, "on_member_update")
        client.add_listener(_on_ready_once, "on_ready")
    except Exception as exc:
        print(f"⚠️ [GESTAO V3] listener: {type(exc).__name__}: {exc}", flush=True)

    _INSTALLED = True
    if _CLEANUP_TASK is None or _CLEANUP_TASK.done():
        _CLEANUP_TASK = asyncio.create_task(_cleanup_delayed(), name="dicor-gestao-cleanup")

    print("✅ [GESTAO V3] gestão ativa sem publicação automática de painel; hierarquia dinâmica por membros e cargos reais.", flush=True)
    return True


# Compatibilidade com chamadas antigas que esperavam estes nomes.
V72GestaoModal = None
V72SelecionarMembro = _MemberSelect
V72SelecionarMembroView = _SelectView
V72PainelGestaoView = GestaoV3Painel
