# -*- coding: utf-8 -*-
"""Gestão DICOR: painel único de cargos + hierarquia automática."""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import discord

PANEL_CHANNEL_ID = 1490200489319600300
PROMOCOES_CHANNEL_ID = 1545160616522813520
REBAIXAMENTOS_CHANNEL_ID = 1545160585216532530
HISTORY_FILE = "historico_movimentacoes_cargo.json"
PANEL_MARKER = "<!-- DICOR_GESTAO_PAINEL -->"
HIERARCHY_MARKER = "DICOR_HIERARQUIA_ATUAL"
RANKS = ("estagiario", "investigador", "inspetor")
ACTIONS = {
    "promover_estagiario": ("estagiario", "investigador", "⬆️ Estagiário → Investigador"),
    "promover_investigador": ("investigador", "inspetor", "⬆️ Investigador → Inspetor"),
    "rebaixar_inspetor": ("inspetor", "investigador", "⬇️ Inspetor → Investigador"),
    "rebaixar_investigador": ("investigador", "estagiario", "⬇️ Investigador → Estagiário"),
}
_INSTALLED = False
_BOT_MODULE: Any = None
_LOCK = asyncio.Lock()
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
    if "inspetor" in name:
        return "inspetor"
    return ""


def _find_rank_role(guild: Any, rank: str) -> Optional[Any]:
    candidates = [r for r in getattr(guild, "roles", []) or [] if _rank(r) == rank]
    return max(candidates, key=lambda r: int(getattr(r, "position", 0) or 0), default=None)


def _managed_roles(member: Any) -> list[Any]:
    return [r for r in getattr(member, "roles", []) or [] if _rank(r) in RANKS]


def _highest_managed_role(member: Any) -> Optional[Any]:
    return max(_managed_roles(member), key=lambda r: int(getattr(r, "position", 0) or 0), default=None)


def _manager(member: Any, bot_module: Any) -> bool:
    fn = getattr(bot_module, "usuario_e_administrador", None)
    if callable(fn):
        try:
            return bool(fn(member))
        except Exception:
            pass
    for role in getattr(member, "roles", []) or []:
        name = _norm(getattr(role, "name", ""))
        if "inspetor" in name or "vice diretor" in name or "diretor" in name:
            return True
    return False


def _qra(bot_module: Any, member: Any) -> str:
    for name in ("_qra_por_membro", "_qra_por_usuario", "obter_qra", "get_qra"):
        fn = getattr(bot_module, name, None)
        if not callable(fn):
            continue
        try:
            value = fn(member)
            if inspect.isawaitable(value):
                continue
            if value:
                return str(value)
        except Exception:
            pass
    try:
        state = getattr(bot_module, "_v173_central_data_state", {})
        if isinstance(state, dict):
            for rows in state.values():
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("discord_id", "")) == str(member.id) or str(row.get("user_id", "")) == str(member.id):
                        value = row.get("qra") or row.get("QRA")
                        if value:
                            return str(value)
    except Exception:
        pass
    return "Não identificado"


def _history_path(bot_module: Any) -> Path:
    return Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data"))) / HISTORY_FILE


def _load_history(bot_module: Any) -> dict[str, Any]:
    try:
        path = _history_path(bot_module)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("eventos", [])
                return data
    except Exception:
        pass
    return {"eventos": []}


def _save_history(bot_module: Any, data: dict[str, Any]) -> None:
    try:
        path = _history_path(bot_module)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:
        print(f"⚠️ [GESTAO] histórico: {type(exc).__name__}: {exc}", flush=True)


def _movement_key(member: Any, before_role: Any, after_role: Any) -> str:
    return f"{member.id}:{getattr(before_role, 'id', 0)}:{getattr(after_role, 'id', 0)}"


async def _send_movement(bot_module: Any, member: Any, before_role: Any, after_role: Any, action: str, actor: Any) -> bool:
    client = getattr(bot_module, "bot", None)
    if client is None:
        return False
    history = _load_history(bot_module)
    eventos = history.get("eventos", [])
    if not isinstance(eventos, list):
        eventos = []
    key = _movement_key(member, before_role, after_role)
    if any(isinstance(item, dict) and item.get("key") == key for item in eventos):
        return True

    channel_id = PROMOCOES_CHANNEL_ID if action.startswith("promover") else REBAIXAMENTOS_CHANNEL_ID
    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except Exception as exc:
            print(f"⚠️ [GESTAO] canal {channel_id}: {type(exc).__name__}: {exc}", flush=True)
            return False

    qra = _qra(bot_module, member)
    mention = getattr(member, "mention", str(member))
    actor_text = getattr(actor, "mention", None) or str(actor) if actor is not None else "Sistema DICOR"
    data = datetime.now().astimezone().strftime("%d/%m/%Y às %H:%M")

    if action.startswith("promover"):
        content = (
            "🏅 PROMOÇÃO DE CARGO\n\n"
            f"👤 Oficial: {mention}\n"
            f"📋 QRA: {qra}\n"
            f"⬆️ Cargo anterior: {before_role.name}\n"
            f"🏅 Novo cargo: {after_role.name}\n\n"
            f"Após análise e avaliação interna, fica registrada a promoção do(a) oficial ao cargo de {after_role.name}.\n\n"
            "A promoção reconhece o desempenho, comprometimento e conduta apresentados durante o período de atuação.\n\n"
            f"📅 Data: {data}\n"
            f"👮 Responsável: {actor_text}\n\n"
            "────────────────────────────\n"
            "🔒 DICOR — Gestão da DICOR"
        )
        tipo = "promocao"
    else:
        content = (
            "⚠️ REBAIXAMENTO DE CARGO\n\n"
            f"👤 Oficial: {mention}\n"
            f"📋 QRA: {qra}\n"
            f"⬇️ Cargo anterior: {before_role.name}\n"
            f"📉 Novo cargo: {after_role.name}\n\n"
            f"Fica registrado o rebaixamento do(a) oficial ao cargo de {after_role.name}, conforme decisão administrativa interna.\n\n"
            "A alteração passa a valer imediatamente após a publicação deste comunicado.\n\n"
            f"📅 Data: {data}\n"
            f"👮 Responsável: {actor_text}\n\n"
            "────────────────────────────\n"
            "🔒 DICOR — Gestão da DICOR"
        )
        tipo = "rebaixamento"

    try:
        await channel.send(content, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
    except Exception as exc:
        print(f"⚠️ [GESTAO] comunicado: {type(exc).__name__}: {exc}", flush=True)
        return False

    eventos.append({
        "key": key,
        "tipo": tipo,
        "member_id": int(member.id),
        "cargo_anterior_id": int(getattr(before_role, "id", 0) or 0),
        "cargo_anterior": str(before_role.name),
        "novo_cargo_id": int(getattr(after_role, "id", 0) or 0),
        "novo_cargo": str(after_role.name),
        "qra": qra,
        "responsavel_id": int(getattr(actor, "id", 0) or 0),
        "responsavel": str(actor) if actor is not None else "Sistema DICOR",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    history["eventos"] = eventos[-500:]
    _save_history(bot_module, history)
    return True


def _role_members(guild: Any, role: Any) -> list[Any]:
    if role is None:
        return []
    members = []
    for member in getattr(guild, "members", []) or []:
        if getattr(member, "bot", False):
            continue
        if any(getattr(r, "id", None) == getattr(role, "id", None) for r in getattr(member, "roles", []) or []):
            members.append(member)
    members.sort(key=lambda m: _norm(getattr(m, "display_name", "")))
    return members


def _find_named_role(guild: Any, *parts: str) -> Optional[Any]:
    wanted = [_norm(p) for p in parts if p]
    exact = []
    partial = []
    for role in getattr(guild, "roles", []) or []:
        name = _norm(getattr(role, "name", ""))
        if not name or name == "everyone":
            continue
        if all(p in name for p in wanted):
            exact.append(role)
        elif any(p in name for p in wanted):
            partial.append(role)
    return max(exact or partial, key=lambda r: int(getattr(r, "position", 0) or 0), default=None)


def _members_lines(guild: Any, role: Any) -> str:
    members = _role_members(guild, role)
    if not members:
        return "• Nenhum ocupante"
    return "\n".join(f"• {m.mention}" for m in members)


def _hierarchy_embed(guild: Any) -> discord.Embed:
    embed = discord.Embed(
        title="🏛️ HIERARQUIA OFICIAL — DICOR",
        description="Estrutura atual do efetivo · atualização automática após alterações de cargo.",
        color=0xC9A227,
    )

    alto = [
        ("🥇 Delegado Geral", _find_named_role(guild, "delegado geral")),
        ("🥈 Delegado Adjunto", _find_named_role(guild, "delegado adjunto")),
    ]
    comando = [
        ("🎖️ Diretor DICOR", _find_named_role(guild, "diretor dicor")),
        ("🎖️ Vice-Diretor DICOR", _find_named_role(guild, "vice diretor dicor")),
        ("🛡️ Inspetor DICOR", _find_named_role(guild, "inspetor")),
    ]
    investigativo = [("🔎 Investigador", _find_named_role(guild, "investigador"))]
    operacional = [("🧑‍💼 Estagiário", _find_named_role(guild, "estagiario"))]

    def block(items: list[tuple[str, Any]]) -> str:
        parts = []
        for label, role in items:
            members = _role_members(guild, role)
            if members:
                parts.append(f"**{label}**\n" + "\n".join(f"• {m.mention}" for m in members))
            else:
                parts.append(f"**{label}**\n• Nenhum ocupante")
        text = "\n\n".join(parts)
        return text[:1024]

    embed.add_field(name="👑 ALTO COMANDO", value=block(alto), inline=False)
    embed.add_field(name="🧠 COMANDO DICOR", value=block(comando), inline=False)
    embed.add_field(name="🔎 SETOR INVESTIGATIVO", value=block(investigativo), inline=False)
    embed.add_field(name="📡 BASE OPERACIONAL", value=block(operacional), inline=False)
    embed.add_field(
        name="⚖️ OBSERVAÇÕES",
        value="A ordem apresentada acompanha a hierarquia registrada no servidor. Alterações de cargo refletem automaticamente neste painel.",
        inline=False,
    )
    embed.set_footer(text=f"DICOR • {HIERARCHY_MARKER}")
    return embed


async def _refresh_hierarchy(bot_module: Any, guild: Any) -> None:
    if guild is None:
        return
    client = getattr(bot_module, "bot", None)
    if client is None:
        return
    channel = client.get_channel(PANEL_CHANNEL_ID)
    if channel is None:
        try:
            channel = await client.fetch_channel(PANEL_CHANNEL_ID)
        except Exception as exc:
            print(f"⚠️ [HIERARQUIA] canal: {type(exc).__name__}: {exc}", flush=True)
            return

    embed = _hierarchy_embed(guild)
    try:
        async for message in channel.history(limit=80):
            if getattr(getattr(message, "author", None), "id", None) != getattr(client.user, "id", None):
                continue
            old_title = any(str(getattr(e, "title", "")) == "🏛️ HIERARQUIA OFICIAL — DICOR" for e in getattr(message, "embeds", []) or [])
            old_content = "HIERARQUIA OFICIAL" in str(getattr(message, "content", ""))
            footer_mark = any(HIERARCHY_MARKER in str(getattr(getattr(e, "footer", None), "text", "")) for e in getattr(message, "embeds", []) or [])
            if old_title or old_content or footer_mark:
                await message.edit(content="", embed=embed, allowed_mentions=discord.AllowedMentions.none())
                return
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except Exception as exc:
        print(f"⚠️ [HIERARQUIA] render: {type(exc).__name__}: {exc}", flush=True)


def _schedule_hierarchy_refresh(bot_module: Any, guild: Any) -> None:
    if guild is None:
        return
    key = int(getattr(guild, "id", 0) or 0)
    task = _REFRESH_TASKS.get(key)
    if task and not task.done():
        return

    async def runner() -> None:
        await asyncio.sleep(0.8)
        try:
            await _refresh_hierarchy(bot_module, guild)
        except Exception as exc:
            print(f"⚠️ [HIERARQUIA] tarefa: {type(exc).__name__}: {exc}", flush=True)

    _REFRESH_TASKS[key] = asyncio.create_task(runner(), name=f"dicor-hierarchy-{key}")


class MemberSelect(discord.ui.UserSelect):
    def __init__(self, action: str):
        super().__init__(placeholder="Selecione o membro…", min_values=1, max_values=1, custom_id=f"dicor:gestao:v3:select:{action}")
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            member = self.values[0]
            if not isinstance(member, discord.Member) and getattr(interaction, "guild", None) is not None:
                member = interaction.guild.get_member(int(getattr(member, "id", 0) or 0))
            if member is None:
                await interaction.response.send_message("❌ Membro não encontrado.", ephemeral=True)
                return
            await _do_change(interaction, self.action, member, _BOT_MODULE)
        except Exception as exc:
            print(f"⚠️ [GESTAO] select: {type(exc).__name__}: {exc}", flush=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Não foi possível processar a seleção.", ephemeral=True)
            except Exception:
                pass


class SelectView(discord.ui.View):
    def __init__(self, action: str):
        super().__init__(timeout=180)
        self.add_item(MemberSelect(action))


class GestaoV3Panel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if _manager(interaction.user, _BOT_MODULE):
            return True
        try:
            await interaction.response.send_message("❌ Apenas Inspetor, Vice-Diretor ou Diretor pode usar a Gestão.", ephemeral=True)
        except Exception:
            pass
        return False

    @discord.ui.button(label="Estagiário → Investigador", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="dicor:gestao:v3:up:estagiario", row=0)
    async def up_estagiario(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message("Selecione o Estagiário que será promovido:", view=SelectView("promover_estagiario"), ephemeral=True)

    @discord.ui.button(label="Investigador → Inspetor", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="dicor:gestao:v3:up:investigador", row=0)
    async def up_investigador(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message("Selecione o Investigador que será promovido:", view=SelectView("promover_investigador"), ephemeral=True)

    @discord.ui.button(label="Inspetor → Investigador", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="dicor:gestao:v3:down:inspetor", row=1)
    async def down_inspetor(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message("Selecione o Inspetor que será rebaixado:", view=SelectView("rebaixar_inspetor"), ephemeral=True)

    @discord.ui.button(label="Investigador → Estagiário", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="dicor:gestao:v3:down:investigador", row=1)
    async def down_investigador(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message("Selecione o Investigador que será rebaixado:", view=SelectView("rebaixar_investigador"), ephemeral=True)

    @discord.ui.button(label="Retirar da DICOR", emoji="🚫", style=discord.ButtonStyle.danger, custom_id="dicor:gestao:v3:retirar", row=2)
    async def retirar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        old_view = getattr(_BOT_MODULE, "V141SelecionarMembroView", None)
        if callable(old_view):
            await interaction.response.send_message("Selecione o membro que será retirado:", view=old_view("retirar"), ephemeral=True)
        else:
            await interaction.response.send_message("❌ Rotina de retirada indisponível.", ephemeral=True)


async def _do_change(interaction: discord.Interaction, action: str, target: discord.Member, bot_module: Any) -> None:
    guild = getattr(interaction, "guild", None)
    if guild is None:
        await interaction.response.send_message("❌ Ação disponível somente no servidor.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    if not _manager(interaction.user, bot_module):
        await interaction.followup.send("❌ Apenas Inspetor, Vice-Diretor ou Diretor pode usar a Gestão.", ephemeral=True)
        return

    before_name, after_name, label = ACTIONS[action]
    before_role = _find_rank_role(guild, before_name)
    after_role = _find_rank_role(guild, after_name)
    if before_role is None or after_role is None:
        await interaction.followup.send("❌ Cargos da hierarquia não encontrados.", ephemeral=True)
        return

    current_role = _highest_managed_role(target)
    if _rank(current_role) != before_name:
        await interaction.followup.send(f"❌ O membro precisa estar como **{before_role.name}**.", ephemeral=True)
        return

    bot_member = getattr(guild, "me", None)
    bot_top = getattr(bot_member, "top_role", None) if bot_member else None
    if bot_top is not None and int(after_role.position) >= int(bot_top.position):
        await interaction.followup.send("❌ O bot não pode aplicar um cargo acima ou igual ao seu próprio cargo.", ephemeral=True)
        return

    try:
        async with _LOCK:
            old_roles = _managed_roles(target)
            kept_roles = [r for r in getattr(target, "roles", []) or [] if r not in old_roles and getattr(r, "name", "") != "@everyone"]
            kept_roles.append(after_role)
            await target.edit(roles=kept_roles, reason=f"DICOR Gestão: {label} por {interaction.user}")
            announced = await _send_movement(bot_module, target, before_role, after_role, action, interaction.user)
            _schedule_hierarchy_refresh(bot_module, guild)

        if announced:
            await interaction.followup.send(f"✅ {target.mention} alterado: **{before_role.name} → {after_role.name}**.", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ {target.mention} alterado: **{before_role.name} → {after_role.name}**. O cargo foi aplicado, mas o comunicado não foi publicado.", ephemeral=True)
    except Exception as exc:
        print(f"⚠️ [GESTAO] alteração: {type(exc).__name__}: {exc}", flush=True)
        try:
            await interaction.followup.send("❌ Não foi possível concluir a alteração.", ephemeral=True)
        except Exception:
            pass


async def _on_member_update(before: discord.Member, after: discord.Member) -> None:
    try:
        if getattr(after, "bot", False):
            return
        before_ids = {getattr(r, "id", 0) for r in getattr(before, "roles", []) or []}
        after_ids = {getattr(r, "id", 0) for r in getattr(after, "roles", []) or []}
        if before_ids != after_ids:
            _schedule_hierarchy_refresh(_BOT_MODULE, getattr(after, "guild", None))
    except Exception as exc:
        print(f"⚠️ [HIERARQUIA] listener: {type(exc).__name__}: {exc}", flush=True)


async def _install_panel(bot_module: Any) -> None:
    client = getattr(bot_module, "bot", None)
    if client is None:
        return
    channel = client.get_channel(PANEL_CHANNEL_ID)
    if channel is None:
        try:
            channel = await client.fetch_channel(PANEL_CHANNEL_ID)
        except Exception as exc:
            print(f"⚠️ [GESTAO] canal do painel: {type(exc).__name__}: {exc}", flush=True)
            return

    embed = discord.Embed(
        title="🔐 GESTÃO DICOR",
        description=(
            "**Painel oficial de movimentação do efetivo**\n\n"
            "🥉 **Estagiário**  →  🔹 **Investigador**  →  🛡️ **Inspetor**\n\n"
            "Use os botões abaixo para realizar promoções ou rebaixamentos."
        ),
        color=0xC9A227,
    )
    embed.add_field(name="⬆️ PROMOÇÕES", value="🥉 Estagiário → 🔹 Investigador\n🔹 Investigador → 🛡️ Inspetor", inline=True)
    embed.add_field(name="⬇️ REBAIXAMENTOS", value="🛡️ Inspetor → 🔹 Investigador\n🔹 Investigador → 🥉 Estagiário", inline=True)
    embed.add_field(name="🔒 AUTORIZAÇÃO", value="🛡️ Inspetor • 🎖️ Vice-Diretor • 👑 Diretor", inline=False)
    embed.set_footer(text="DICOR • Gestão de efetivo")

    try:
        async for message in channel.history(limit=80):
            if getattr(getattr(message, "author", None), "id", None) != getattr(client.user, "id", None):
                continue
            title_match = any(str(getattr(e, "title", "")) == "🔐 GESTÃO DICOR" for e in getattr(message, "embeds", []) or [])
            marker_match = "GESTÃO DICOR" in str(getattr(message, "content", ""))
            if title_match or marker_match:
                await message.edit(content="", embed=embed, view=GestaoV3Panel(), allowed_mentions=discord.AllowedMentions.none())
                return
        await channel.send(embed=embed, view=GestaoV3Panel(), allowed_mentions=discord.AllowedMentions.none())
    except Exception as exc:
        print(f"⚠️ [GESTAO] painel: {type(exc).__name__}: {exc}", flush=True)


async def install(bot_module: Any) -> bool:
    global _INSTALLED, _BOT_MODULE
    if _INSTALLED:
        return True
    _BOT_MODULE = bot_module
    client = getattr(bot_module, "bot", None)
    if client is None:
        return False
    try:
        client.add_view(GestaoV3Panel())
    except Exception as exc:
        print(f"⚠️ [GESTAO] View persistente: {type(exc).__name__}: {exc}", flush=True)
    try:
        client.add_listener(_on_member_update, "on_member_update")
    except Exception:
        pass
    _INSTALLED = True
    await _install_panel(bot_module)
    guilds = list(getattr(client, "guilds", []) or [])
    for guild in guilds:
        await _refresh_hierarchy(bot_module, guild)
    print(f"✅ [GESTAO] painel único ativo no canal {PANEL_CHANNEL_ID}; promoções/rebaixamentos + hierarquia sincronizados.", flush=True)
    return True
