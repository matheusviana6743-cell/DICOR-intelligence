# -*- coding: utf-8 -*-
"""Painel de Gestão DICOR V4.

Um único painel em #criterios-de-up, quatro ações de movimentação e histórico.
Não publica hierarquia no canal do painel.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import discord

PANEL_MARKER = "DICOR_GESTAO_V4"
PANEL_NAMES = {"criterios-de-up", "criterios de up"}
PROMOCOES_CHANNEL_ID = 1545160616522813520
REBAIXAMENTOS_CHANNEL_ID = 1545160585216532530
HISTORY_FILE = "historico_movimentacoes_cargo.json"

ACTIONS = {
    "promover_estagiario": ("estagiario", "investigador", "⬆️ Estagiário → Investigador"),
    "promover_investigador": ("investigador", "inspetor", "⬆️ Investigador → Inspetor"),
    "rebaixar_inspetor": ("inspetor", "investigador", "⬇️ Inspetor → Investigador"),
    "rebaixar_investigador": ("investigador", "estagiario", "⬇️ Investigador → Estagiário"),
}
NEW_IDS = {f"dicor:gestao:v4:{action}" for action in ACTIONS}
_INSTALLED = False
_BOT_MODULE: Any = None
_LOCK = asyncio.Lock()
_REFRESH: dict[int, asyncio.Task] = {}


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


def _role(guild: Any, rank: str) -> Optional[Any]:
    candidates = [r for r in getattr(guild, "roles", []) or [] if _rank(r) == rank]
    dicor = [r for r in candidates if "dicor" in _norm(getattr(r, "name", ""))]
    return max(dicor or candidates, key=lambda r: int(getattr(r, "position", 0) or 0), default=None)


def _highest(member: Any) -> Optional[Any]:
    return max([r for r in getattr(member, "roles", []) or [] if _rank(r)], key=lambda r: int(getattr(r, "position", 0) or 0), default=None)


def _manager(member: Any, bot_module: Any) -> bool:
    fn = getattr(bot_module, "usuario_e_administrador", None)
    if callable(fn):
        try:
            if fn(member):
                return True
        except Exception:
            pass
    for role in getattr(member, "roles", []) or []:
        name = _norm(getattr(role, "name", ""))
        if "vice diretor" in name or "inspetor" in name or ("diretor" in name and "dicor" in name):
            return True
    return False


def _qra(member: Any) -> str:
    values = [getattr(member, "nick", ""), getattr(member, "display_name", ""), getattr(member, "name", "")]
    for value in values:
        match = re.search(r"(?:\||-|#)\s*(\d{4,})\b", str(value or ""))
        if match:
            return match.group(1)
        match = re.search(r"\b(\d{4,})\s*$", str(value or ""))
        if match:
            return match.group(1)
    return "Não identificado"


def _history_path(bot_module: Any) -> Path:
    return Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data"))) / HISTORY_FILE


def _save_history(bot_module: Any, event: dict[str, Any]) -> None:
    path = _history_path(bot_module)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"eventos": []}
        if not isinstance(data, dict):
            data = {"eventos": []}
        eventos = data.setdefault("eventos", [])
        if not isinstance(eventos, list):
            eventos = []
            data["eventos"] = eventos
        key = event.get("key")
        if not any(isinstance(x, dict) and x.get("key") == key for x in eventos):
            eventos.append(event)
        data["eventos"] = eventos[-500:]
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:
        print(f"⚠️ [GESTAO] histórico: {type(exc).__name__}: {exc}", flush=True)


def _panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🔐 GESTÃO DICOR",
        description="Painel administrativo de movimentação de cargos.\n\nAs alterações são aplicadas diretamente nos cargos reais do Discord e a hierarquia é atualizada automaticamente.",
        color=discord.Color.gold(),
    )
    embed.add_field(name="⬆️ PROMOÇÕES", value="Estagiário → Investigador\nInvestigador → Inspetor", inline=True)
    embed.add_field(name="⬇️ REBAIXAMENTOS", value="Inspetor → Investigador\nInvestigador → Estagiário", inline=True)
    embed.add_field(name="👮 AUTORIZAÇÃO", value="Inspetor • Vice-Diretor • Diretor", inline=False)
    embed.set_footer(text=PANEL_MARKER)
    return embed


class MemberSelect(discord.ui.UserSelect):
    def __init__(self, action: str):
        self.action = action
        super().__init__(placeholder="Selecione o oficial…", min_values=1, max_values=1, custom_id=f"dicor:gestao:v4:select:{action}")

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            member = self.values[0]
            if not isinstance(member, discord.Member):
                member = interaction.guild.get_member(int(getattr(member, "id", 0)))
            if member is None:
                await interaction.response.send_message("❌ Oficial não encontrado.", ephemeral=True)
                return
            await _change(interaction, self.action, member)
        except Exception as exc:
            print(f"⚠️ [GESTAO] seleção: {type(exc).__name__}: {exc}", flush=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Ocorreu um erro ao processar a seleção.", ephemeral=True)
            except Exception:
                pass


class SelectView(discord.ui.View):
    def __init__(self, action: str):
        super().__init__(timeout=180)
        self.add_item(MemberSelect(action))


class GestaoV4Painel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if _manager(interaction.user, _BOT_MODULE):
            return True
        try:
            await interaction.response.send_message("❌ Apenas Inspetor, Vice-Diretor ou Diretor pode usar este painel.", ephemeral=True)
        except Exception:
            pass
        return False

    @discord.ui.button(label="Estagiário → Investigador", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="dicor:gestao:v4:promover_estagiario", row=0)
    async def up_estagiario(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message("Selecione o **Estagiário** que será promovido:", view=SelectView("promover_estagiario"), ephemeral=True)

    @discord.ui.button(label="Investigador → Inspetor", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="dicor:gestao:v4:promover_investigador", row=0)
    async def up_investigador(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message("Selecione o **Investigador** que será promovido:", view=SelectView("promover_investigador"), ephemeral=True)

    @discord.ui.button(label="Inspetor → Investigador", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="dicor:gestao:v4:rebaixar_inspetor", row=1)
    async def down_inspetor(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message("Selecione o **Inspetor** que será rebaixado:", view=SelectView("rebaixar_inspetor"), ephemeral=True)

    @discord.ui.button(label="Investigador → Estagiário", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="dicor:gestao:v4:rebaixar_investigador", row=1)
    async def down_investigador(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message("Selecione o **Investigador** que será rebaixado:", view=SelectView("rebaixar_investigador"), ephemeral=True)


async def _hierarchy_refresh(guild: Any) -> None:
    try:
        module = __import__("hierarquia_v7")
        refresh = getattr(module, "refresh_hierarchy", None)
        if callable(refresh):
            await refresh(guild)
            return
    except Exception:
        pass
    try:
        module = __import__("hierarquia_dicor")
        refresh = getattr(module, "refresh_hierarchy", None)
        if callable(refresh):
            await refresh(guild)
    except Exception:
        pass


def _schedule_refresh(guild: Any, delay: float = 0.6) -> None:
    if guild is None:
        return
    gid = int(getattr(guild, "id", 0) or 0)
    task = _REFRESH.get(gid)
    if task and not task.done():
        return
    async def runner() -> None:
        await asyncio.sleep(delay)
        await _hierarchy_refresh(guild)
    _REFRESH[gid] = asyncio.create_task(runner(), name=f"dicor-hierarchy-refresh-{gid}")


def _movement_text(kind: str, member: Any, before: Any, after: Any, actor: Any) -> str:
    data = datetime.now().astimezone().strftime("%d/%m/%Y às %H:%M")
    qra = _qra(member)
    responsavel = str(actor) if actor is not None else "Sistema DICOR"
    if kind == "promocao":
        return ("🏅 PROMOÇÃO DE CARGO\n\n"
                f"👤 Oficial: {member.mention}\n"
                f"📋 QRA: {qra}\n"
                f"⬆️ Cargo anterior: {before.name}\n"
                f"🏅 Novo cargo: {after.name}\n\n"
                f"Após análise e avaliação interna, fica registrada a promoção do(a) oficial ao cargo de {after.name}.\n\n"
                "A promoção reconhece o desempenho, comprometimento e conduta apresentados durante o período de atuação.\n\n"
                f"📅 Data: {data}\n👮 Responsável: {responsavel}\n\n"
                "────────────────────────────\n🔒 DICOR — Gestão da DICOR")
    return ("⚠️ REBAIXAMENTO DE CARGO\n\n"
            f"👤 Oficial: {member.mention}\n"
            f"📋 QRA: {qra}\n"
            f"⬇️ Cargo anterior: {before.name}\n"
            f"📉 Novo cargo: {after.name}\n\n"
            f"Fica registrado o rebaixamento do(a) oficial ao cargo de {after.name}, conforme decisão administrativa interna.\n\n"
            "A alteração passa a valer imediatamente após a publicação deste comunicado.\n\n"
            f"📅 Data: {data}\n👮 Responsável: {responsavel}\n\n"
            "────────────────────────────\n🔒 DICOR — Gestão da DICOR")


async def _publish_movement(member: Any, before: Any, after: Any, actor: Any, kind: str) -> None:
    channel_id = PROMOCOES_CHANNEL_ID if kind == "promocao" else REBAIXAMENTOS_CHANNEL_ID
    client = getattr(_BOT_MODULE, "bot", None)
    if client is None:
        return
    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except Exception:
            return
    key = f"manual:{member.id}:{before.id}:{after.id}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    text = _movement_text(kind, member, before, after, actor)
    try:
        await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
    except Exception as exc:
        print(f"⚠️ [GESTAO] comunicado: {type(exc).__name__}: {exc}", flush=True)
        return
    _save_history(_BOT_MODULE, {
        "key": key, "tipo": kind, "member_id": int(member.id),
        "cargo_anterior_id": int(before.id), "cargo_anterior": str(before.name),
        "novo_cargo_id": int(after.id), "novo_cargo": str(after.name),
        "qra": _qra(member), "responsavel_id": int(getattr(actor, "id", 0) or 0),
        "responsavel": str(actor) if actor is not None else "Sistema DICOR",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def _change(interaction: discord.Interaction, action: str, member: Any) -> None:
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Esta ação só pode ser usada no servidor.", ephemeral=True)
        return
    before_name, after_name, label = ACTIONS[action]
    before = _role(guild, before_name)
    after = _role(guild, after_name)
    current = _highest(member)
    if not before or not after or not current or _rank(current) != before_name:
        await interaction.response.send_message(f"❌ O membro selecionado precisa estar como **{before.name if before else before_name}**.", ephemeral=True)
        return
    bot_member = getattr(guild, "me", None)
    if bot_member is None or not getattr(bot_member.guild_permissions, "manage_roles", False):
        await interaction.response.send_message("❌ O bot não possui a permissão Gerenciar Cargos.", ephemeral=True)
        return
    if int(after.position) >= int(bot_member.top_role.position):
        await interaction.response.send_message("❌ O cargo de destino está acima do cargo máximo do bot.", ephemeral=True)
        return
    actor = interaction.user
    try:
        async with _LOCK:
            old_roles = _managed_roles(member)
            keep = [r for r in member.roles if r not in old_roles]
            keep.append(after)
            await member.edit(roles=keep, reason=f"DICOR Gestão: {label} por {actor}")
            await _publish_movement(member, before, after, actor, "promocao" if after.position > before.position else "rebaixamento")
            _schedule_refresh(guild)
        await interaction.response.send_message(f"✅ {member.mention} atualizado: **{before.name} → {after.name}**.", ephemeral=True)
    except Exception as exc:
        print(f"⚠️ [GESTAO] alteração: {type(exc).__name__}: {exc}", flush=True)
        try:
            await interaction.response.send_message("❌ Não foi possível alterar o cargo.", ephemeral=True)
        except Exception:
            pass


def _managed_roles(member: Any) -> list[Any]:
    return [r for r in getattr(member, "roles", []) or [] if _rank(r)]


async def _upgrade_panel(bot_module: Any) -> None:
    client = getattr(bot_module, "bot", None)
    if client is None:
        return
    guilds = list(getattr(client, "guilds", []) or [])
    target = []
    configured = int(getattr(bot_module, "GUILD_ID", 0) or 0)
    for guild in guilds:
        if configured and int(guild.id) != configured:
            continue
        for channel in getattr(guild, "text_channels", []) or []:
            if _norm(getattr(channel, "name", "")) in PANEL_NAMES:
                target.append(channel)
    for channel in target[:3]:
        try:
            async for message in channel.history(limit=100):
                if getattr(getattr(message, "author", None), "id", None) != getattr(client.user, "id", None):
                    continue
                ids = {str(getattr(child, "custom_id", "")) for row in getattr(message, "components", []) or [] for child in getattr(row, "children", []) or []}
                content = str(getattr(message, "content", ""))
                footers = " ".join(str(getattr(getattr(e, "footer", None), "text", "")) for e in getattr(message, "embeds", []) or [])
                if PANEL_MARKER in footers or "DICOR_GESTAO_V2" in content or ids.intersection({"dicor:gestao:subir:v72", "dicor:gestao:descer:v72", "dicor:gestao:retirar:v72"}) or any(i.startswith("dicor:gestao:v3:") for i in ids):
                    await message.edit(content="", embed=_panel_embed(), view=GestaoV4Painel(), allowed_mentions=discord.AllowedMentions.none())
                    return
            await channel.send(embed=_panel_embed(), view=GestaoV4Painel(), allowed_mentions=discord.AllowedMentions.none())
            return
        except Exception as exc:
            print(f"⚠️ [GESTAO] painel #{getattr(channel, 'name', '?')}: {type(exc).__name__}: {exc}", flush=True)


async def _on_member_update(before: Any, after: Any) -> None:
    try:
        if getattr(after, "bot", False):
            return
        old = {int(getattr(r, "id", 0) or 0) for r in getattr(before, "roles", []) or []}
        new = {int(getattr(r, "id", 0) or 0) for r in getattr(after, "roles", []) or []}
        if old != new:
            _schedule_refresh(getattr(after, "guild", None))
    except Exception as exc:
        print(f"⚠️ [GESTAO] listener: {type(exc).__name__}: {exc}", flush=True)


async def install(bot_module: Any) -> bool:
    global _INSTALLED, _BOT_MODULE
    _BOT_MODULE = bot_module
    client = getattr(bot_module, "bot", None)
    if client is None:
        return False
    # Evita que a implementação V2 continue recriando o painel antigo.
    try:
        import gestao_v2
        async def _noop(*_args: Any, **_kwargs: Any) -> None:
            return None
        for name in ("_upgrade_existing_panel", "_upgrade_panel", "_ensure_panel", "ensure_panel", "refresh_panel", "_publish_panel", "_post_panel"):
            if hasattr(gestao_v2, name):
                setattr(gestao_v2, name, _noop)
    except Exception:
        pass
    if not _INSTALLED:
        try:
            client.add_view(GestaoV4Painel())
        except Exception as exc:
            print(f"⚠️ [GESTAO] View V4: {type(exc).__name__}: {exc}", flush=True)
        try:
            client.add_listener(_on_member_update, "on_member_update")
        except Exception:
            pass
        _INSTALLED = True
        print("✅ [GESTAO V4] painel único e movimentação estável carregados.", flush=True)
    # Migra o painel existente somente quando o Discord já estiver pronto.
    if bool(getattr(client, "is_ready", lambda: False)()):
        await _upgrade_panel(bot_module)
    return True


# Compatibilidade com módulos legados que ainda importam estes nomes.
V72PainelGestaoView = GestaoV4Painel
V72SelecionarMembroView = SelectView
