# -*- coding: utf-8 -*-
"""Gestão DICOR V5.
Painel único e persistente para promoção/rebaixamento de cargos.
"""
from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import discord

PANEL_MARKER = "DICOR_GESTAO_V5"
PANEL_NAMES = {"criterios-de-up", "criterios de up"}
PROMOCOES_CHANNEL_ID = 1545160616522813520
REBAIXAMENTOS_CHANNEL_ID = 1545160585216532530
HISTORY_FILE = "historico_movimentacoes_cargo.json"

ACTIONS = {
    "promover_estagiario": ("estagiario", "investigador", "⬆️ Estagiário → Investigador"),
    "promover_investigador": ("investigador", "inspetor", "⬆️ Investigador → Inspetor"),
    "promover_inspetor": ("inspetor", "vice_diretor", "⬆️ Inspetor → Vice-Diretor"),
    "rebaixar_vice_diretor": ("vice_diretor", "inspetor", "⬇️ Vice-Diretor → Inspetor"),
    "rebaixar_inspetor": ("inspetor", "investigador", "⬇️ Inspetor → Investigador"),
    "rebaixar_investigador": ("investigador", "estagiario", "⬇️ Investigador → Estagiário"),
}

_RANK_ALIASES = {
    "estagiario": ("estagiario", "estagiário"),
    "investigador": ("investigador",),
    "inspetor": ("inspetor",),
    "vice_diretor": ("vice diretor", "vice-diretor", "vice diretor dicor", "vice-diretor dicor"),
}

_bot_module: Any = None
_installed = False
_lock = asyncio.Lock()
_refresh_tasks: dict[int, asyncio.Task] = {}


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()).strip()


def _rank(role: Any) -> str:
    name = _norm(getattr(role, "name", ""))
    if "vice diretor" in name:
        return "vice_diretor"
    if "estagiario" in name:
        return "estagiario"
    if "investigador" in name:
        return "investigador"
    if "inspetor" in name:
        return "inspetor"
    return ""


def _role(guild: Any, rank: str) -> Optional[Any]:
    roles = [r for r in getattr(guild, "roles", []) or [] if _rank(r) == rank]
    dicor = [r for r in roles if "dicor" in _norm(getattr(r, "name", ""))]
    return max(dicor or roles, key=lambda r: int(getattr(r, "position", 0) or 0), default=None)


def _highest(member: Any) -> Optional[Any]:
    return max([r for r in getattr(member, "roles", []) or [] if _rank(r)], key=lambda r: int(getattr(r, "position", 0) or 0), default=None)


def _managed_roles(member: Any) -> list[Any]:
    return [r for r in getattr(member, "roles", []) or [] if _rank(r)]


def _manager(member: Any) -> bool:
    fn = getattr(_bot_module, "usuario_e_administrador", None)
    if callable(fn):
        try:
            if fn(member):
                return True
        except Exception:
            pass
    return any(_rank(r) in {"inspetor", "vice_diretor"} or ("diretor" in _norm(getattr(r, "name", "")) and "dicor" in _norm(getattr(r, "name", ""))) for r in getattr(member, "roles", []) or [])


def _qra(member: Any) -> str:
    for value in (getattr(member, "nick", ""), getattr(member, "display_name", ""), getattr(member, "name", "")):
        text = str(value or "")
        match = re.search(r"(?:\||-|#)\s*(\d{4,})\b", text) or re.search(r"\b(\d{4,})\s*$", text)
        if match:
            return match.group(1)
    return "Não identificado"


def _history_path() -> Path:
    base = getattr(_bot_module, "DATA_DIR", Path(__file__).parent / "data")
    return Path(str(base)) / HISTORY_FILE


def _save_history(event: dict[str, Any]) -> None:
    try:
        path = _history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"eventos": []}
        if not isinstance(data, dict):
            data = {"eventos": []}
        eventos = data.setdefault("eventos", [])
        if not isinstance(eventos, list):
            eventos = []
            data["eventos"] = eventos
        if not any(isinstance(x, dict) and x.get("key") == event.get("key") for x in eventos):
            eventos.append(event)
        data["eventos"] = eventos[-500:]
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        print(f"⚠️ [GESTAO V5] histórico: {type(exc).__name__}: {exc}", flush=True)


def _panel_embed() -> discord.Embed:
    e = discord.Embed(
        title="🔐 GESTÃO DICOR",
        description="Painel único para movimentação de cargos.\n\nSelecione a ação e depois o membro. A alteração é aplicada imediatamente e registrada nos canais administrativos.",
        color=discord.Color.gold(),
    )
    e.add_field(name="🏅 PROMOÇÃO", value="Estagiário → Investigador\nInvestigador → Inspetor\nInspetor → Vice-Diretor", inline=True)
    e.add_field(name="⚠️ REBAIXAMENTO", value="Vice-Diretor → Inspetor\nInspetor → Investigador\nInvestigador → Estagiário", inline=True)
    e.add_field(name="🔐 AUTORIZAÇÃO", value="Inspetor • Vice-Diretor • Diretor", inline=False)
    e.set_footer(text=PANEL_MARKER)
    return e


class MemberSelect(discord.ui.UserSelect):
    def __init__(self, action: str):
        self.action = action
        super().__init__(placeholder="Selecione o membro…", min_values=1, max_values=1, custom_id=f"dicor:gestao:v5:select:{action}")

    async def callback(self, interaction: discord.Interaction) -> None:
        member = self.values[0]
        if not isinstance(member, discord.Member):
            member = interaction.guild.get_member(int(getattr(member, "id", 0))) if interaction.guild else None
        if member is None:
            await interaction.response.send_message("❌ Membro não encontrado.", ephemeral=True)
            return
        await _change(interaction, self.action, member)


class SelectView(discord.ui.View):
    def __init__(self, action: str):
        super().__init__(timeout=180)
        self.add_item(MemberSelect(action))


class GestaoV5Painel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if _manager(interaction.user):
            return True
        await interaction.response.send_message("❌ Apenas Inspetor, Vice-Diretor ou Diretor pode usar este painel.", ephemeral=True)
        return False

    async def _select(self, interaction: discord.Interaction, action: str, label: str) -> None:
        await interaction.response.send_message(f"Selecione o **{label}** que será movimentado:", view=SelectView(action), ephemeral=True)

    @discord.ui.button(label="Estagiário → Investigador", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="dicor:gestao:v5:promover_estagiario", row=0)
    async def p1(self, interaction: discord.Interaction, _: discord.ui.Button): await self._select(interaction, "promover_estagiario", "Estagiário")

    @discord.ui.button(label="Investigador → Inspetor", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="dicor:gestao:v5:promover_investigador", row=0)
    async def p2(self, interaction: discord.Interaction, _: discord.ui.Button): await self._select(interaction, "promover_investigador", "Investigador")

    @discord.ui.button(label="Inspetor → Vice-Diretor", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="dicor:gestao:v5:promover_inspetor", row=0)
    async def p3(self, interaction: discord.Interaction, _: discord.ui.Button): await self._select(interaction, "promover_inspetor", "Inspetor")

    @discord.ui.button(label="Vice-Diretor → Inspetor", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="dicor:gestao:v5:rebaixar_vice_diretor", row=1)
    async def r1(self, interaction: discord.Interaction, _: discord.ui.Button): await self._select(interaction, "rebaixar_vice_diretor", "Vice-Diretor")

    @discord.ui.button(label="Inspetor → Investigador", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="dicor:gestao:v5:rebaixar_inspetor", row=1)
    async def r2(self, interaction: discord.Interaction, _: discord.ui.Button): await self._select(interaction, "rebaixar_inspetor", "Inspetor")

    @discord.ui.button(label="Investigador → Estagiário", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="dicor:gestao:v5:rebaixar_investigador", row=1)
    async def r3(self, interaction: discord.Interaction, _: discord.ui.Button): await self._select(interaction, "rebaixar_investigador", "Investigador")


def _movement_text(kind: str, member: Any, before: Any, after: Any, actor: Any) -> str:
    now = datetime.now().astimezone().strftime("%d/%m/%Y às %H:%M")
    if kind == "promocao":
        title, icon = "PROMOÇÃO DE CARGO", "🏅"
        desc = f"Fica registrada a promoção de {member.mention} ao cargo de **{after.name}**."
    else:
        title, icon = "REBAIXAMENTO DE CARGO", "⚠️"
        desc = f"Fica registrado o rebaixamento de {member.mention} ao cargo de **{after.name}**."
    return (f"{icon} **{title}**\n\n👤 Oficial: {member.mention}\n📋 QRA: **{_qra(member)}**\n"
            f"📌 Cargo anterior: **{before.name}**\n🏷️ Novo cargo: **{after.name}**\n\n{desc}\n\n"
            f"📅 {now}\n👮 Responsável: {actor}\n\n🔒 DICOR — Gestão da DICOR")


async def _publish(member: Any, before: Any, after: Any, actor: Any, kind: str) -> None:
    client = getattr(_bot_module, "bot", None)
    if client is None: return
    channel_id = PROMOCOES_CHANNEL_ID if kind == "promocao" else REBAIXAMENTOS_CHANNEL_ID
    channel = client.get_channel(channel_id)
    if channel is None:
        try: channel = await client.fetch_channel(channel_id)
        except Exception: return
    try:
        await channel.send(_movement_text(kind, member, before, after, actor), allowed_mentions=discord.AllowedMentions.none())
    except Exception as exc:
        print(f"⚠️ [GESTAO V5] registro: {type(exc).__name__}: {exc}", flush=True)
        return
    _save_history({"key": f"{member.id}:{before.id}:{after.id}:{datetime.now(timezone.utc).isoformat()}", "tipo": kind, "member_id": member.id, "cargo_anterior_id": before.id, "novo_cargo_id": after.id, "qra": _qra(member), "responsavel_id": getattr(actor, "id", 0), "timestamp": datetime.now(timezone.utc).isoformat()})


async def _refresh_hierarchy(guild: Any) -> None:
    for name in ("hierarquia_v7", "hierarquia_dicor"):
        try:
            module = __import__(name)
            fn = getattr(module, "refresh_hierarchy", None)
            if callable(fn):
                await fn(guild)
                return
        except Exception:
            continue


def _schedule_refresh(guild: Any) -> None:
    gid = int(getattr(guild, "id", 0) or 0)
    old = _refresh_tasks.get(gid)
    if old and not old.done(): return
    async def run():
        await asyncio.sleep(0.5)
        await _refresh_hierarchy(guild)
    _refresh_tasks[gid] = asyncio.create_task(run(), name=f"dicor-hierarchy-refresh-{gid}")


async def _change(interaction: discord.Interaction, action: str, member: Any) -> None:
    guild = interaction.guild
    before_name, after_name, label = ACTIONS[action]
    before, after, current = _role(guild, before_name), _role(guild, after_name), _highest(member)
    if not before or not after or not current or _rank(current) != before_name:
        await interaction.response.send_message(f"❌ O membro precisa estar no cargo **{before.name if before else before_name}**.", ephemeral=True); return
    bot_member = getattr(guild, "me", None)
    if bot_member is None or not getattr(bot_member.guild_permissions, "manage_roles", False):
        await interaction.response.send_message("❌ O bot não possui Gerenciar Cargos.", ephemeral=True); return
    if int(after.position) >= int(bot_member.top_role.position):
        await interaction.response.send_message("❌ O cargo de destino está acima do cargo máximo do bot.", ephemeral=True); return
    try:
        async with _lock:
            keep = [r for r in member.roles if r not in _managed_roles(member)]
            keep.append(after)
            await member.edit(roles=keep, reason=f"DICOR Gestão V5: {label} por {interaction.user}")
            kind = "promocao" if after.position > before.position else "rebaixamento"
            await _publish(member, before, after, interaction.user, kind)
            _schedule_refresh(guild)
        await interaction.response.send_message(f"✅ {member.mention} atualizado: **{before.name} → {after.name}**.", ephemeral=True)
    except Exception as exc:
        print(f"⚠️ [GESTAO V5] alteração: {type(exc).__name__}: {exc}", flush=True)
        if not interaction.response.is_done(): await interaction.response.send_message("❌ Não foi possível alterar o cargo.", ephemeral=True)


async def _cleanup_and_panel(bot_module: Any) -> None:
    client = getattr(bot_module, "bot", None)
    if client is None: return
    configured = int(getattr(bot_module, "GUILD_ID", 0) or 0)
    for guild in getattr(client, "guilds", []) or []:
        if configured and int(guild.id) != configured: continue
        for channel in getattr(guild, "text_channels", []) or []:
            if _norm(getattr(channel, "name", "")) not in PANEL_NAMES: continue
            try:
                found = None
                async for message in channel.history(limit=100):
                    if getattr(getattr(message, "author", None), "id", None) != getattr(client.user, "id", None): continue
                    ids = {str(getattr(c, "custom_id", "")) for row in getattr(message, "components", []) or [] for c in getattr(row, "children", []) or []}
                    footer = " ".join(str(getattr(getattr(e, "footer", None), "text", "")) for e in getattr(message, "embeds", []) or [])
                    if PANEL_MARKER in footer or any(i.startswith("dicor:gestao:v5:") for i in ids): found = message; break
                    if any(x in (getattr(message, "content", "") or "") for x in ("DICOR_GESTAO_V2", "DICOR_GESTAO_V4")):
                        try: await message.delete()
                        except Exception: pass
                if found is None:
                    found = await channel.send(embed=_panel_embed(), view=GestaoV5Painel(), allowed_mentions=discord.AllowedMentions.none())
                else:
                    await found.edit(content="", embed=_panel_embed(), view=GestaoV5Painel(), allowed_mentions=discord.AllowedMentions.none())
            except Exception as exc:
                print(f"⚠️ [GESTAO V5] painel #{getattr(channel, 'name', '?')}: {type(exc).__name__}: {exc}", flush=True)


async def install(bot_module: Any) -> bool:
    global _bot_module, _installed
    _bot_module = bot_module
    client = getattr(bot_module, "bot", None)
    if client is None: return False
    if not _installed:
        try: client.add_view(GestaoV5Painel())
        except Exception as exc: print(f"⚠️ [GESTAO V5] view: {type(exc).__name__}: {exc}", flush=True)
        _installed = True
    await _cleanup_and_panel(bot_module)
    return True
