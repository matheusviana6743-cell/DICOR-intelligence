# -*- coding: utf-8 -*-
"""DICOR Core V602.

Um único núcleo para BO, Perícia Externa e Dossiê.
A entrada de BO/Perícia é baseada exclusivamente nos canais configurados,
então mensagens encaminhadas por bots/webhooks também são aceitas.
A recuperação é contínua para cobrir mensagens recebidas durante deploy/restart.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ui import Button, UserSelect, View

try:
    from PIL import Image
except Exception:
    Image = None
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
except Exception:
    canvas = None
    A4 = None
    ImageReader = None

SOURCE_BO_ID = int(os.getenv("DICOR_BO_SOURCE_ID", "1490200514837745754"))
TARGET_BO_ID = int(os.getenv("DICOR_BO_TARGET_ID", "1525762770253910136"))
SOURCE_PERICIA_ID = int(os.getenv("DICOR_PERICIA_SOURCE_ID", "1490200524367200297"))
LOG_ID = int(os.getenv("LOGS_CHANNEL_ID", "1490205503228477610"))
SCAN_INTERVAL = max(10, int(os.getenv("DICOR_AUTO_SCAN_INTERVAL", "20")))
SCAN_LIMIT = max(50, int(os.getenv("DICOR_AUTO_SCAN_LIMIT", "250")))
DATA_DIR = Path(os.getenv("DICOR_DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE = DATA_DIR / "dicor_v602_state.json"
DOCS = DATA_DIR / "dossies_v602"
DOCS.mkdir(exist_ok=True)
TEMPLATE_B64 = Path(__file__).with_name("dicor_template_v600.b64")
TEMPLATE = DATA_DIR / "dicor_v602_template.png"

AUTH_ROLE_IDS = {int(x) for x in os.getenv("DICOR_AUTH_ROLE_IDS", "1490200388912156692,1490200383614615725,1490200382776021132").replace(";", ",").split(",") if x.strip().isdigit()}
TEAM_ROLE_IDS = {int(x) for x in os.getenv("DICOR_TEAM_ROLE_IDS", "1490200391239864352,1490200390426165290").replace(";", ",").split(",") if x.strip().isdigit()}

DOC_SECTIONS = [
    ("01", "Painel da organização"),
    ("02", "Fotos dos membros"),
    ("03", "Localização"),
    ("04", "Foto de cima da organização"),
    ("05", "Materiais que vendem"),
    ("06", "Registro de compra"),
    ("07", "Informante"),
    ("08", "Baú de membros"),
    ("09", "Baú de líder"),
    ("10", "Local de fabricação"),
    ("11", "Local de produção"),
    ("12", "Informações gerais"),
    ("13", "Assinaturas"),
    ("14", "Análise consolidada"),
    ("15", "Evidências adicionais"),
    ("16", "Cronologia"),
    ("17", "Conclusões"),
    ("18", "Encerramento"),
]


def load_state() -> dict:
    try:
        if STATE.exists():
            value = json.loads(STATE.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
    except Exception:
        traceback.print_exc()
    return {}


def save_state(value: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE)


def now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def month(dt: datetime) -> str:
    return dt.strftime("%m/%Y")


def norm(text: Any) -> str:
    return " ".join(re.sub(r"[^0-9a-zA-ZÀ-ÿ]+", " ", str(text or "").casefold()).split())


def text_of(message: discord.Message) -> str:
    parts = [str(message.content or "")]
    for embed in message.embeds or []:
        parts.append(str(embed.title or ""))
        parts.append(str(embed.description or ""))
        for field in embed.fields or []:
            parts.extend((str(field.name or ""), str(field.value or "")))
    return "\n".join(x for x in parts if x).strip()


def get_records(kind: str) -> list[dict]:
    data = load_state().get(kind, [])
    return data if isinstance(data, list) else []


def append_record(kind: str, record: dict) -> None:
    data = load_state()
    data.setdefault(kind, []).append(record)
    save_state(data)


def update_record(kind: str, record_id: str, patch: dict) -> Optional[dict]:
    data = load_state()
    for record in data.get(kind, []):
        if str(record.get("id")) == str(record_id):
            record.update(patch)
            save_state(data)
            return record
    return None


def source_exists(kind: str, message_id: int) -> bool:
    return any(str(r.get("source_message_id")) == str(message_id) for r in get_records(kind))


def thread_record(kind: str, thread_id: int) -> Optional[dict]:
    return next((r for r in get_records(kind) if str(r.get("thread_id")) == str(thread_id)), None)


def explicit_number(text: str, label: str) -> str:
    patterns = (
        rf"{label}[^0-9]{{0,25}}(?:N[º°O.]?\s*)?(\d{{1,8}})",
        r"N[º°O.]?\s*(\d{1,8})",
        r"#\s*(\d{1,8})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return f"{int(match.group(1)):04d}"
    return ""


def next_number(kind: str, mo: str) -> str:
    data = load_state()
    counters = data.setdefault("counters", {}).setdefault(kind, {})
    current = int(counters.get(mo, 0))
    used = {str(r.get("number")) for r in get_records(kind) if r.get("month") == mo}
    while f"{current + 1:04d}" in used:
        current += 1
    current += 1
    counters[mo] = current
    save_state(data)
    return f"{current:04d}"


def authorized(member: discord.Member) -> bool:
    if any(getattr(role, "id", 0) in AUTH_ROLE_IDS for role in member.roles):
        return True
    return any(("inspetor" in norm(role.name) or "diretor" in norm(role.name)) for role in member.roles)


def team_member(member: discord.Member) -> bool:
    if any(getattr(role, "id", 0) in TEAM_ROLE_IDS for role in member.roles):
        return True
    keys = ("estagi", "investigador", "inspetor", "agente", "delegado", "dicor", "escriv")
    return any(any(key in norm(role.name) for key in keys) for role in member.roles)


async def safe_ack(interaction: discord.Interaction) -> bool:
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
        return True
    except Exception:
        return False


async def safe_reply(interaction: discord.Interaction, text: str) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except Exception:
        pass


async def log(client: discord.Client, text: str) -> None:
    try:
        channel = client.get_channel(LOG_ID)
        if channel:
            await channel.send(str(text)[:1900])
    except Exception:
        pass


class CoreV602:
    def __init__(self, client: discord.Client):
        self.client = client
        self.locks: set[tuple[str, int]] = set()
        self.scanner_task: Optional[asyncio.Task] = None

    async def get_channel(self, guild: discord.Guild, channel_id: int):
        channel = guild.get_channel(channel_id)
        if channel is not None:
            return channel
        try:
            return await self.client.fetch_channel(channel_id)
        except Exception:
            return None

    async def choose_agent(self, guild: discord.Guild, kind: str, mo: str) -> Optional[discord.Member]:
        candidates = [m for m in guild.members if not m.bot and team_member(m) and not authorized(m)]
        if not candidates:
            candidates = [m for m in guild.members if not m.bot and team_member(m)]
        if not candidates:
            return None
        candidates.sort(key=lambda m: (m.display_name.casefold(), m.id))
        data = load_state()
        rr = data.setdefault("round_robin", {}).setdefault(kind, {})
        index = int(rr.get(mo, 0)) % len(candidates)
        rr[mo] = index + 1
        save_state(data)
        return candidates[index]

    async def create_bo(self, message: discord.Message) -> None:
        if not message.guild or int(message.channel.id) != SOURCE_BO_ID:
            return
        key = ("bo", int(message.id))
        if key in self.locks or source_exists("bo", message.id):
            return
        text = text_of(message)
        if "boletim de ocorr" not in norm(text):
            return
        self.locks.add(key)
        try:
            mo = month(message.created_at)
            number = explicit_number(text, "boletim") or next_number("bo", mo)
            parent = await self.get_channel(message.guild, TARGET_BO_ID)
            if not isinstance(parent, discord.TextChannel):
                raise RuntimeError(f"Canal de atendimento BO {TARGET_BO_ID} não encontrado")
            agent = await self.choose_agent(message.guild, "bo", mo)
            thread = await parent.create_thread(
                name=f"📋 BOLETIM DE OCORRÊNCIA — Nº {number}",
                type=discord.ChannelType.private_thread,
                invitable=False,
                auto_archive_duration=10080,
                reason=f"DICOR V602 • BO {number}",
            )
            if agent:
                try:
                    await thread.add_user(agent)
                except Exception:
                    pass
            embed = discord.Embed(title="📋 BOLETIM DE OCORRÊNCIA", description=text[:4000] or "Sem texto.")
            embed.add_field(name="Número", value=f"`{number}`", inline=True)
            embed.add_field(name="Responsável", value=agent.mention if agent else "Aguardando seleção", inline=True)
            embed.add_field(name="Origem", value=message.jump_url, inline=False)
            await thread.send(
                content=agent.mention if agent else None,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            )
            for attachment in message.attachments or []:
                try:
                    await thread.send(file=await attachment.to_file(use_cached=True))
                except Exception:
                    await thread.send(attachment.url)
            record_id = f"BO-{message.id}"
            append_record("bo", {
                "id": record_id, "number": number, "month": mo,
                "source_message_id": message.id, "source_channel_id": SOURCE_BO_ID,
                "thread_id": thread.id, "agent_id": agent.id if agent else None,
                "agent_name": str(agent) if agent else "", "status": "EM_ATENDIMENTO" if agent else "AGUARDANDO_AGENTE",
                "created_at": now(), "source_url": message.jump_url,
            })
            await thread.send(view=BOView(self, record_id))
            await log(self.client, f"✅ V602 BO aberto automaticamente | Nº {number} | tópico {thread.id}")
        except Exception as exc:
            traceback.print_exc()
            await log(self.client, f"❌ V602 falha BO {message.id}: {type(exc).__name__}: {exc}")
        finally:
            self.locks.discard(key)

    async def create_pericia(self, message: discord.Message) -> None:
        if not message.guild or int(message.channel.id) != SOURCE_PERICIA_ID:
            return
        key = ("pericia", int(message.id))
        if key in self.locks or source_exists("pericia", message.id):
            return
        self.locks.add(key)
        try:
            text = text_of(message)
            mo = month(message.created_at)
            number = explicit_number(text, "per[ií]cia") or next_number("pericia", mo)
            parent = await self.get_channel(message.guild, SOURCE_PERICIA_ID)
            if not isinstance(parent, discord.TextChannel):
                raise RuntimeError(f"Canal de Perícia Externa {SOURCE_PERICIA_ID} não encontrado")
            thread = await parent.create_thread(
                name=f"🔬 PERÍCIA Nº {number} • AGUARDANDO AGENTE",
                type=discord.ChannelType.private_thread,
                invitable=False,
                auto_archive_duration=10080,
                reason=f"DICOR V602 • Perícia {number}",
            )
            for attachment in message.attachments or []:
                try:
                    await thread.send(file=await attachment.to_file(use_cached=True))
                except Exception:
                    await thread.send(attachment.url)
            record_id = f"PERICIA-{message.id}"
            append_record("pericia", {
                "id": record_id, "number": number, "month": mo,
                "source_message_id": message.id, "source_channel_id": SOURCE_PERICIA_ID,
                "thread_id": thread.id, "agent_id": None, "status": "AGUARDANDO_AGENTE",
                "attachments": len(message.attachments or []), "created_at": now(), "source_url": message.jump_url,
            })
            await thread.send(
                embed=discord.Embed(
                    title=f"🔬 CONTROLE DA PERÍCIA EXTERNA — Nº {number}",
                    description="Um Inspetor+ deve selecionar o agente responsável abaixo.",
                ),
                view=PericiaView(self, record_id),
            )
            await log(self.client, f"✅ V602 Perícia aberta automaticamente | Nº {number} | tópico {thread.id}")
        except Exception as exc:
            traceback.print_exc()
            await log(self.client, f"❌ V602 falha Perícia {message.id}: {type(exc).__name__}: {exc}")
        finally:
            self.locks.discard(key)

    async def on_message(self, message: discord.Message) -> None:
        if not message.guild:
            return
        # Não filtra message.author.bot. Os canais de entrada podem receber
        # mensagens encaminhadas por bots/webhooks durante o fluxo do servidor.
        channel_id = int(getattr(message.channel, "id", 0) or 0)
        if channel_id == SOURCE_BO_ID:
            await self.create_bo(message)
        elif channel_id == SOURCE_PERICIA_ID:
            await self.create_pericia(message)

    async def scan_once(self, guild: discord.Guild) -> None:
        bo = await self.get_channel(guild, SOURCE_BO_ID)
        if isinstance(bo, discord.TextChannel):
            try:
                async for message in bo.history(limit=SCAN_LIMIT, oldest_first=False):
                    await self.create_bo(message)
            except Exception:
                traceback.print_exc()
        pericia = await self.get_channel(guild, SOURCE_PERICIA_ID)
        if isinstance(pericia, discord.TextChannel):
            try:
                async for message in pericia.history(limit=SCAN_LIMIT, oldest_first=False):
                    await self.create_pericia(message)
            except Exception:
                traceback.print_exc()

    async def scanner(self) -> None:
        await asyncio.sleep(2)
        while True:
            for guild in list(getattr(self.client, "guilds", []) or []):
                await self.scan_once(guild)
            await asyncio.sleep(SCAN_INTERVAL)

    async def start(self) -> None:
        if self.scanner_task is None or self.scanner_task.done():
            self.scanner_task = asyncio.create_task(self.scanner(), name="dicor-v602-auto-scanner")

    def find_by_thread(self, kind: str, thread_id: int) -> Optional[dict]:
        return thread_record(kind, thread_id)


class BOAgentSelect(UserSelect):
    def __init__(self, core: CoreV602):
        super().__init__(placeholder="Inspetor+: selecione o agente responsável", min_values=1, max_values=1, custom_id="dicor_v602_bo_agent")
        self.core = core

    async def callback(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not authorized(interaction.user):
            return await safe_reply(interaction, "❌ Apenas Inspetor+ pode alterar o responsável.")
        if not await safe_ack(interaction):
            return
        record = self.core.find_by_thread("bo", getattr(interaction.channel, "id", 0))
        member = self.values[0] if self.values else None
        if not record or not isinstance(member, discord.Member) or not team_member(member):
            return await safe_reply(interaction, "❌ Atendimento ou membro inválido.")
        update_record("bo", record["id"], {"agent_id": member.id, "agent_name": str(member), "status": "EM_ATENDIMENTO"})
        try:
            await interaction.channel.add_user(member)
            await interaction.channel.send(f"📌 {member.mention} foi definido como responsável pelo BO **{record['number']}**.")
        except Exception:
            pass
        await safe_reply(interaction, f"✅ {member.mention} agora é o responsável pelo BO **{record['number']}**.")


class BOView(View):
    def __init__(self, core: CoreV602, record_id: str = ""):
        super().__init__(timeout=None)
        self.add_item(BOAgentSelect(core))
        button = Button(label="Finalizar BO", emoji="✅", style=discord.ButtonStyle.success, custom_id="dicor_v602_bo_done")
        async def done(interaction: discord.Interaction):
            if not await safe_ack(interaction):
                return
            if not isinstance(interaction.user, discord.Member) or not authorized(interaction.user):
                return await safe_reply(interaction, "❌ Apenas Inspetor+ pode finalizar.")
            record = core.find_by_thread("bo", getattr(interaction.channel, "id", 0))
            if not record:
                return await safe_reply(interaction, "❌ Atendimento não encontrado.")
            update_record("bo", record["id"], {"status": "FINALIZADO", "closed_at": now()})
            await safe_reply(interaction, "✅ BO finalizado.")
        button.callback = done
        self.add_item(button)


class PericiaAgentSelect(UserSelect):
    def __init__(self, core: CoreV602):
        super().__init__(placeholder="Inspetor+: selecione o agente responsável", min_values=1, max_values=1, custom_id="dicor_v602_pericia_agent")
        self.core = core

    async def callback(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not authorized(interaction.user):
            return await safe_reply(interaction, "❌ Apenas Inspetor+ pode escolher o responsável.")
        if not await safe_ack(interaction):
            return
        record = self.core.find_by_thread("pericia", getattr(interaction.channel, "id", 0))
        member = self.values[0] if self.values else None
        if not record or not isinstance(member, discord.Member) or not team_member(member):
            return await safe_reply(interaction, "❌ Perícia ou membro inválido.")
        update_record("pericia", record["id"], {"agent_id": member.id, "agent_name": str(member), "status": "PENDENTE"})
        try:
            await interaction.channel.add_user(member)
            await interaction.channel.send(f"📌 {member.mention}\n**TAREFA DE PERÍCIA ATRIBUÍDA**\nVocê é o responsável pela Perícia Nº {record['number']}.")
        except Exception:
            pass
        await safe_reply(interaction, f"✅ {member.mention} foi definido como responsável pela Perícia Nº **{record['number']}**.")


class PericiaView(View):
    def __init__(self, core: CoreV602, record_id: str = ""):
        super().__init__(timeout=None)
        self.add_item(PericiaAgentSelect(core))
        button = Button(label="Marcar concluída", emoji="✅", style=discord.ButtonStyle.success, custom_id="dicor_v602_pericia_done")
        async def done(interaction: discord.Interaction):
            if not await safe_ack(interaction):
                return
            if not isinstance(interaction.user, discord.Member) or not authorized(interaction.user):
                return await safe_reply(interaction, "❌ Apenas Inspetor+ pode concluir.")
            record = core.find_by_thread("pericia", getattr(interaction.channel, "id", 0))
            if not record:
                return await safe_reply(interaction, "❌ Perícia não encontrada.")
            update_record("pericia", record["id"], {"status": "CONCLUIDA", "closed_at": now()})
            await safe_reply(interaction, "✅ Perícia concluída.")
        button.callback = done
        self.add_item(button)


def template_png() -> Optional[Path]:
    if TEMPLATE.exists() and TEMPLATE.stat().st_size > 10000:
        return TEMPLATE
    if not TEMPLATE_B64.exists():
        return None
    raw = "".join(TEMPLATE_B64.read_text(encoding="utf-8").split())
    data = base64.b64decode(raw, validate=True)
    TEMPLATE.write_bytes(data)
    if Image:
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.convert("RGB").save(TEMPLATE, "PNG")
        except Exception:
            pass
    return TEMPLATE


def section_code(text: str) -> str:
    value = norm(text)
    rules = {
        "01": ("painel", "lideran"), "02": ("fotos dos membros", "integrantes"),
        "03": ("localizacao", "coordenadas", "endereco"), "04": ("foto de cima", "visao aerea", "aerea"),
        "05": ("material", "ingrediente", "produto"), "06": ("compra",), "07": ("informante",),
        "08": ("bau de membros",), "09": ("bau de lider",), "10": ("fabricacao",),
        "11": ("producao",), "12": ("informacoes gerais",),
    }
    for code, words in rules.items():
        if any(norm(word) in value for word in words):
            return code
    return "15"


def wrap_lines(text: str, width: int = 95) -> list[str]:
    cleaned = re.sub(r"(?:/tmp|/mnt)/[^\s]+", "", str(text or "")).strip()
    result: list[str] = []
    for paragraph in cleaned.splitlines() or [""]:
        words = paragraph.split()
        line = ""
        for word in words:
            candidate = word if not line else f"{line} {word}"
            if len(candidate) <= width:
                line = candidate
            else:
                if line:
                    result.append(line)
                line = word
        if line:
            result.append(line)
    return result


async def collect_dossier(channel: discord.abc.GuildChannel) -> dict[str, list[dict]]:
    threads: list[discord.Thread] = []
    if isinstance(channel, discord.Thread):
        threads = [channel]
    else:
        try:
            active = list(getattr(channel, "threads", []) or [])
            archived = [t async for t in channel.archived_threads(limit=None)]
            seen = {t.id for t in active}
            threads = active + [t for t in archived if t.id not in seen]
        except Exception:
            traceback.print_exc()
    grouped: dict[str, list[dict]] = {code: [] for code, _ in DOC_SECTIONS}
    for thread in threads:
        try:
            async for message in thread.history(limit=None, oldest_first=True):
                content = text_of(message)
                grouped[section_code(f"{thread.name} {content}")].append({
                    "thread": thread.name, "author": str(message.author),
                    "date": message.created_at.strftime("%d/%m/%Y %H:%M"),
                    "content": content or "[mídia sem texto]",
                    "attachments": [(a.url, a.filename) for a in message.attachments or []],
                })
        except Exception:
            traceback.print_exc()
    return grouped


async def generate_dossier(channel: discord.abc.GuildChannel) -> Path:
    if canvas is None or ImageReader is None or A4 is None:
        raise RuntimeError("ReportLab não está disponível")
    background = template_png()
    if background is None:
        raise RuntimeError("Template PF/DICOR não encontrado no repositório")
    grouped = await collect_dossier(channel)
    output = DOCS / f"PF-DICOR-{channel.id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
    page_w, page_h = A4
    pdf = canvas.Canvas(str(output), pagesize=A4)
    for index, (code, title) in enumerate(DOC_SECTIONS, start=1):
        pdf.drawImage(ImageReader(str(background)), 0, 0, width=page_w, height=page_h, preserveAspectRatio=False, mask="auto")
        y = page_h - (230 if index == 1 else 155)
        if index == 1:
            for line in (
                f"Nº do Pedido de Pacificação:   PF-DICOR-{channel.id % 1000000:06d}",
                f"Data de Expedição:      {now()}",
                f"Nº do Processo:   PF-DICOR-{channel.id}",
                "Requerente:             Polícia Federal - DICOR",
            ):
                pdf.setFont("Courier", 10.5)
                pdf.drawString(45, y, line[:105])
                y -= 23
        pdf.setFont("Courier-Bold", 11.5)
        pdf.drawString(45, y, f"{code}. {title.upper()}")
        y -= 22
        rows = grouped.get(code, [])
        if not rows:
            pdf.setFont("Courier", 9)
            pdf.drawString(45, y, "Nenhum registro encontrado nesta seção.")
        else:
            for row in rows[:15]:
                for line in wrap_lines(f"[{row['date']}] {row['author']}", 98)[:1] + wrap_lines(row["content"], 98)[:8]:
                    if y < 75:
                        break
                    pdf.setFont("Courier", 7.8 if line.startswith("[") else 8.5)
                    pdf.drawString(45, y, line[:105])
                    y -= 11
                if y < 75:
                    break
        pdf.showPage()
    pdf.save()
    return output


def install(bot_module: Any) -> CoreV602:
    client = getattr(bot_module, "bot", None)
    if client is None:
        raise RuntimeError("cliente Discord indisponível")
    core = CoreV602(client)
    if not hasattr(client, "_dicor_v602_core"):
        client._dicor_v602_core = core
        client.add_listener(core.on_message, "on_message")
        client.add_listener(lambda: core.start(), "on_ready")
    try:
        client.add_view(BOView(core))
        client.add_view(PericiaView(core))
    except Exception:
        traceback.print_exc()
    async def dossie(interaction: discord.Interaction):
        if not await safe_ack(interaction):
            return
        try:
            output = await generate_dossier(interaction.channel)
            await safe_reply(interaction, f"✅ Dossiê V602 gerado: `{output.name}`")
            if isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
                await interaction.channel.send(file=discord.File(str(output)))
        except Exception as exc:
            traceback.print_exc()
            await safe_reply(interaction, f"❌ Falha no Dossiê: {type(exc).__name__}: {exc}")
    try:
        client.tree.add_command(app_commands.Command(name="dossiev602", description="Gera o Dossiê Operacional da mesa atual", callback=dossie))
    except Exception:
        traceback.print_exc()
    print(f"✅ DICOR V602 ativo | BO entrada={SOURCE_BO_ID} -> {TARGET_BO_ID} | Perícia entrada={SOURCE_PERICIA_ID} | scanner={SCAN_INTERVAL}s", flush=True)
    return core
