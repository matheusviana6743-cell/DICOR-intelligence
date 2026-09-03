# -*- coding: utf-8 -*-
"""Painel de Gestão DICOR V2 + sincronização imediata da hierarquia."""
from __future__ import annotations

import asyncio
import inspect
import re
import unicodedata
from typing import Any, Optional

PANEL_MARKER = "<!-- DICOR_GESTAO_V2 -->"
PANEL_NAMES = {"criterios-de-up", "criterios de up", "gestao", "gestao-dicor", "gestão-dicor"}
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
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _rank(role: Any) -> str:
    name = _norm(getattr(role, "name", ""))
    if "estagiario" in name:
        return "estagiario"
    if "investigador" in name:
        return "investigador"
    if re.search(r"\binspetor\b", name):
        return "inspetor"
    return ""


def _find_rank_role(guild: Any, rank: str) -> Optional[Any]:
    candidates = []
    for role in list(getattr(guild, "roles", []) or []):
        if _rank(role) == rank:
            candidates.append(role)
    return max(candidates, key=lambda r: int(getattr(r, "position", 0) or 0), default=None)


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
        if any(x in name for x in ("inspetor", "vice diretor", "diretor")):
            return True
    return False


def _managed_roles(member: Any) -> list[Any]:
    return [r for r in list(getattr(member, "roles", []) or []) if _rank(r) in MANAGED_RANKS]


async def _refresh_hierarchy(bot_module: Any, guild: Any) -> None:
    try:
        for name in ("enviar_hierarquia_substituindo_anterior", "atualizar_hierarquia", "publicar_hierarquia", "rebuild_hierarquia", "atualizar_painel_hierarquia"):
            fn = getattr(bot_module, name, None)
            if not callable(fn):
                continue
            result = fn()
            if inspect.isawaitable(result):
                await result
            return
    except Exception as exc:
        print(f"⚠️ [HIERARQUIA] atualização falhou: {type(exc).__name__}: {exc}", flush=True)


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
    current_rank = _rank(max(current, key=lambda r: int(getattr(r, "position", 0) or 0), default=None))
    if current_rank != before_name:
        await interaction.response.send_message(f"❌ O membro selecionado precisa estar como **{before_role.name}**.", ephemeral=True)
        return
    bot_member = getattr(guild, "me", None)
    if bot_member is not None and int(getattr(after_role, "position", 0) or 0) >= int(getattr(getattr(bot_member, "top_role", None), "position", 0) or 0):
        await interaction.response.send_message("❌ O cargo de destino está acima do cargo máximo do bot.", ephemeral=True)
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


class _MemberSelect(__import__("discord").ui.UserSelect):
    def __init__(self, action: str):
        super().__init__(placeholder="Selecione o membro…", min_values=1, max_values=1, custom_id=f"dicor:gestao:v2:select:{action}")
        self.action = action

    async def callback(self, interaction: Any) -> None:
        try:
            value = self.values[0]
            member = value if hasattr(value, "guild") else interaction.guild.get_member(int(getattr(value, "id", 0) or 0))
            if member is None:
                await interaction.response.send_message("❌ Membro não encontrado.", ephemeral=True)
                return
            await _do_change(interaction, self.action, member, _BOT_MODULE)
        except Exception as exc:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Ocorreu um erro ao processar a alteração.", ephemeral=True)
            except Exception:
                pass
            print(f"⚠️ [GESTAO V2] select: {type(exc).__name__}: {exc}", flush=True)


class _SelectView(__import__("discord").ui.View):
    def __init__(self, action: str):
        super().__init__(timeout=180)
        self.add_item(_MemberSelect(action))


class GestaoV2Painel(__import__("discord").ui.View):
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

    @__import__("discord").ui.button(label="Estagiário → Investigador", emoji="⬆️", style=__import__("discord").ButtonStyle.success, custom_id="dicor:gestao:v2:promover:estagiario", row=0)
    async def promover_estagiario(self, interaction: Any, _: Any) -> None:
        await interaction.response.send_message("Selecione o **Estagiário** que será promovido:", view=_SelectView("promover_estagiario"), ephemeral=True)

    @__import__("discord").ui.button(label="Investigador → Inspetor", emoji="⬆️", style=__import__("discord").ButtonStyle.success, custom_id="dicor:gestao:v2:promover:investigador", row=0)
    async def promover_investigador(self, interaction: Any, _: Any) -> None:
        await interaction.response.send_message("Selecione o **Investigador** que será promovido:", view=_SelectView("promover_investigador"), ephemeral=True)

    @__import__("discord").ui.button(label="Inspetor → Investigador", emoji="⬇️", style=__import__("discord").ButtonStyle.secondary, custom_id="dicor:gestao:v2:rebaixar:inspetor", row=1)
    async def rebaixar_inspetor(self, interaction: Any, _: Any) -> None:
        await interaction.response.send_message("Selecione o **Inspetor** que será rebaixado:", view=_SelectView("rebaixar_inspetor"), ephemeral=True)

    @__import__("discord").ui.button(label="Investigador → Estagiário", emoji="⬇️", style=__import__("discord").ButtonStyle.secondary, custom_id="dicor:gestao:v2:rebaixar:investigador", row=1)
    async def rebaixar_investigador(self, interaction: Any, _: Any) -> None:
        await interaction.response.send_message("Selecione o **Investigador** que será rebaixado:", view=_SelectView("rebaixar_investigador"), ephemeral=True)


async def _upgrade_existing_panel(bot_module: Any) -> None:
    client = getattr(bot_module, "bot", None)
    if client is None:
        return
    old_ids = {"dicor:gestao:subir:v72", "dicor:gestao:descer:v72", "dicor:gestao:retirar:v72"}
    content = (
        f"{PANEL_MARKER}\n"
        "🔐 **GESTÃO DICOR — MOVIMENTAÇÃO DE CARGOS**\n\n"
        "**Hierarquia operacional**\n"
        "🥉 Estagiário  →  🔹 Investigador  →  🛡️ Inspetor\n\n"
        "**Ações disponíveis**\n"
        "⬆️ Progressão de cargo\n"
        "⬇️ Rebaixamento de cargo\n\n"
        "👮 **Gestão autorizada:** Inspetor • Vice-Diretor • Diretor\n\n"
        "Selecione uma ação abaixo para continuar."
    )
    channels = []
    for guild in list(getattr(client, "guilds", []) or []):
        channels.extend([c for c in list(getattr(guild, "text_channels", []) or []) if _norm(getattr(c, "name", "")) in {_norm(x) for x in PANEL_NAMES}])
    for channel in channels[:3]:
        try:
            async for message in channel.history(limit=40):
                if getattr(getattr(message, "author", None), "id", None) != getattr(getattr(client, "user", None), "id", None):
                    continue
                component_ids = set()
                for row in list(getattr(message, "components", []) or []):
                    for child in list(getattr(row, "children", []) or []):
                        cid = getattr(child, "custom_id", None)
                        if cid:
                            component_ids.add(str(cid))
                if PANEL_MARKER in str(getattr(message, "content", "")) or component_ids.intersection(old_ids):
                    await message.edit(content=content, view=GestaoV2Painel(), allowed_mentions=None)
                    return
            await channel.send(content=content, view=GestaoV2Painel(), allowed_mentions=None)
            return
        except Exception as exc:
            print(f"⚠️ [GESTAO V2] painel em {getattr(channel, 'id', '?')}: {type(exc).__name__}: {exc}", flush=True)


async def _on_member_update(before: Any, after: Any) -> None:
    try:
        if getattr(after, "bot", False):
            return
        before_roles = {getattr(r, "id", 0) for r in getattr(before, "roles", []) or []}
        after_roles = {getattr(r, "id", 0) for r in getattr(after, "roles", []) or []}
        if before_roles != after_roles:
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
    except Exception:
        pass
    try:
        client.add_view(GestaoV2Painel())
    except Exception as exc:
        print(f"⚠️ [GESTAO V2] View persistente: {type(exc).__name__}: {exc}", flush=True)
    _INSTALLED = True
    asyncio.create_task(_upgrade_existing_panel(bot_module), name="dicor-gestao-panel-upgrade")
    print("✅ [GESTAO V2] painel ampliado: Estagiário, Investigador e Inspetor; gestão por Inspetor/Vice-Diretor/Diretor.", flush=True)
    return True


_BOT_MODULE: Any = None
