# -*- coding: utf-8 -*-
"""DICOR Core V603

Núcleo independente e limpo para:
- abertura automática de BO;
- abertura automática de Perícia Externa;
- seleção de agente por Inspetor+;
- recuperação de mensagens recebidas durante deploy/restart;
- numeração mensal de BO/Perícia quando a origem não informa número;
- geração de Dossiê Operacional em PDF, sem template/base64 externo.

Este módulo não depende dos antigos V1xx/V2xx/V6xx.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ui import Button, UserSelect, View

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, KeepTogether, Image as RLImage,
    )
except Exception:
    colors = None
    A4 = None
    ParagraphStyle = None
    TA_CENTER = TA_LEFT = None
    mm = None
    SimpleDocTemplate = Paragraph = Spacer = Table = TableStyle = PageBreak = KeepTogether = RLImage = None


BO_SOURCE_ID = int(os.getenv("DICOR_BO_SOURCE_ID", "1490200514837745754"))
BO_TARGET_ID = int(os.getenv("DICOR_BO_TARGET_ID", "1525762770253910136"))
PERICIA_SOURCE_ID = int(os.getenv("DICOR_PERICIA_SOURCE_ID", "1490200524367200297"))
LOG_ID = int(os.getenv("LOGS_CHANNEL_ID", "1490205503228477610"))
SCAN_SECONDS = max(8, int(os.getenv("DICOR_AUTO_SCAN_SECONDS", "15")))
SCAN_MESSAGES = max(100, int(os.getenv("DICOR_AUTO_SCAN_MESSAGES", "500")))
STATE_DIR = Path(os.getenv("DICOR_DATA_DIR", "data"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "dicor_core_v603.json"
DOC_DIR = STATE_DIR / "dossies_v603"
DOC_DIR.mkdir(parents=True, exist_ok=True)

# Somente estes cargos podem escolher/finalizar atendimentos.
AUTH_ROLE_IDS = {
    int(x.strip()) for x in os.getenv(
        "DICOR_AUTH_ROLE_IDS",
        "1490200388912156692,1490200383614615725,1490200382776021132",
    ).replace(";", ",").split(",") if x.strip().isdigit()
}

# Cargos que podem ser escolhidos como responsáveis.
TEAM_ROLE_IDS = {
    int(x.strip()) for x in os.getenv(
        "DICOR_TEAM_ROLE_IDS",
        "1490200391239864352,1490200390426165290",
    ).replace(";", ",").split(",") if x.strip().isdigit()
}

TOPICS = [
    "Painel da organização",
    "Fotos dos líderes",
    "Fotos dos membros",
    "Rádio",
    "Localização",
    "Crimes da comunidade",
    "Baú de líder",
    "Baú de membros",
    "Rota de farm",
    "Rota de produção",
    "Ingredientes base e produtos",
    "Informante",
    "Informações gerais",
    "Assinaturas",
    "Conclusão e análise",
]


def load_state() -> dict[str, Any]:
    try:
        if STATE_FILE.exists():
            obj = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return obj
    except Exception:
        traceback.print_exc()
    return {"bo": [], "pericia": [], "counters": {"bo": {}, "pericia": {}}, "rr": {"bo": {}, "pericia": {}}}


def save_state(state: dict[str, Any]) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def normalized(text: Any) -> str:
    value = clean(text).casefold()
    value = re.sub(r"[^0-9a-zA-ZÀ-ÿ]+", " ", value)
    return " ".join(value.split())


def message_text(message: discord.Message) -> str:
    chunks = [message.content or ""]
    for embed in message.embeds or []:
        chunks += [embed.title or "", embed.description or ""]
        for field in embed.fields or []:
            chunks += [field.name or "", field.value or ""]
    return "\n".join(str(x) for x in chunks if x).strip()


def local_dt(message: discord.Message) -> datetime:
    dt = message.created_at
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def month_key(dt: datetime) -> str:
    return dt.strftime("%m/%Y")


def four_digit_number(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        pattern = rf"{label}[^0-9]{{0,30}}(?:n[º°o.]?\s*)?(\d{{1,8}})"
        m = re.search(pattern, text, flags=re.I)
        if m:
            return f"{int(m.group(1)):04d}"
    for pattern in (r"N[º°O.]?\s*(\d{1,8})", r"#\s*(\d{1,8})"):
        m = re.search(pattern, text, flags=re.I)
        if m:
            return f"{int(m.group(1)):04d}"
    return ""


def next_number(kind: str, month: str) -> str:
    state = load_state()
    counters = state.setdefault("counters", {}).setdefault(kind, {})
    records = state.setdefault(kind, [])
    used = {str(r.get("number")) for r in records if str(r.get("month")) == month}
    value = max(0, int(counters.get(month, 0)))
    while f"{value + 1:04d}" in used:
        value += 1
    value += 1
    counters[month] = value
    save_state(state)
    return f"{value:04d}"


def has_source(kind: str, source_id: int) -> bool:
    return any(str(r.get("source_message_id")) == str(source_id) for r in load_state().get(kind, []))


def get_record(kind: str, record_id: str) -> Optional[dict[str, Any]]:
    for r in load_state().get(kind, []):
        if str(r.get("id")) == str(record_id):
            return r
    return None


def get_record_by_thread(kind: str, thread_id: int) -> Optional[dict[str, Any]]:
    for r in load_state().get(kind, []):
        if str(r.get("thread_id")) == str(thread_id):
            return r
    return None


def update_record(kind: str, record_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
    state = load_state()
    for r in state.get(kind, []):
        if str(r.get("id")) == str(record_id):
            r.update(patch)
            save_state(state)
            return r
    return None


def authorized(member: discord.Member) -> bool:
    if any(getattr(role, "id", 0) in AUTH_ROLE_IDS for role in member.roles):
        return True
    return any("inspetor" in normalized(role.name) or "diretor" in normalized(role.name) for role in member.roles)


def selectable(member: discord.Member) -> bool:
    if member.bot:
        return False
    if any(getattr(role, "id", 0) in TEAM_ROLE_IDS for role in member.roles):
        return True
    keys = ("estagi", "investigador", "agente", "inspetor", "delegado", "dicor", "escriv")
    return any(any(k in normalized(role.name) for k in keys) for role in member.roles)


async def reply(interaction: discord.Interaction, text: str) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except Exception:
        pass


async def defer(interaction: discord.Interaction) -> bool:
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
        return True
    except Exception:
        return False


async def send_log(client: discord.Client, text: str) -> None:
    try:
        channel = client.get_channel(LOG_ID)
        if channel is None:
            channel = await client.fetch_channel(LOG_ID)
        if hasattr(channel, "send"):
            await channel.send(clean(text)[:1900])
    except Exception:
        pass


class AgentSelect(UserSelect):
    def __init__(self, core: "CoreV603", kind: str):
        self.core = core
        self.kind = kind
        super().__init__(
            placeholder="Inspetor+: selecione o agente responsável",
            min_values=1,
            max_values=1,
            custom_id=f"dicor_v603_{kind}_agent",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not authorized(interaction.user):
            await reply(interaction, "❌ Apenas Inspetor+ pode selecionar o responsável.")
            return
        if not await defer(interaction):
            return
        member = self.values[0] if self.values else None
        record = get_record_by_thread(self.kind, int(getattr(interaction.channel, "id", 0)))
        if not record or not isinstance(member, discord.Member) or not selectable(member):
            await reply(interaction, "❌ Atendimento ou agente inválido.")
            return
        update_record(self.kind, record["id"], {
            "agent_id": member.id,
            "agent_name": str(member),
            "status": "EM_ATENDIMENTO",
            "assigned_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        })
        try:
            await interaction.channel.add_user(member)
        except Exception:
            pass
        label = "BO" if self.kind == "bo" else "Perícia"
        try:
            await interaction.channel.send(f"👤 **{label} atribuído.** Responsável: {member.mention}")
        except Exception:
            pass
        await reply(interaction, f"✅ {member.mention} agora é o responsável por {label} Nº **{record['number']}**.")


class AtendimentoView(View):
    def __init__(self, core: "CoreV603", kind: str):
        super().__init__(timeout=None)
        self.add_item(AgentSelect(core, kind))
        self.kind = kind
        button = Button(
            label="Finalizar atendimento" if kind == "bo" else "Concluir perícia",
            emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id=f"dicor_v603_{kind}_finish",
        )
        button.callback = self.finish
        self.add_item(button)

    async def finish(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not authorized(interaction.user):
            await reply(interaction, "❌ Apenas Inspetor+ pode concluir este atendimento.")
            return
        if not await defer(interaction):
            return
        record = get_record_by_thread(self.kind, int(getattr(interaction.channel, "id", 0)))
        if not record:
            await reply(interaction, "❌ Atendimento não encontrado no controle V603.")
            return
        if not record.get("agent_id"):
            await reply(interaction, "⚠️ Selecione o agente responsável antes de concluir.")
            return
        update_record(self.kind, record["id"], {
            "status": "CONCLUIDO",
            "closed_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        })
        await reply(interaction, "✅ Atendimento concluído. O registro foi salvo.")


class CoreV603:
    def __init__(self, client: discord.Client):
        self.client = client
        self.processing: set[tuple[str, int]] = set()
        self.scanner_task: Optional[asyncio.Task] = None
        self.views_registered = False

    async def channel(self, channel_id: int):
        channel = self.client.get_channel(channel_id)
        if channel is not None:
            return channel
        try:
            return await self.client.fetch_channel(channel_id)
        except Exception:
            return None

    async def choose_initial_agent(self, guild: discord.Guild, kind: str, mo: str) -> Optional[discord.Member]:
        # O responsável não é escolhido automaticamente: Inspetor+ define pelo painel.
        # Isso evita atribuir um membro errado quando o atendimento exige escolha manual.
        return None

    async def create_thread(self, parent: discord.TextChannel, name: str, reason: str) -> discord.Thread:
        # Um único caminho de criação. Sem reutilização de tópicos antigos.
        return await parent.create_thread(
            name=name[:100],
            type=discord.ChannelType.private_thread,
            invitable=False,
            auto_archive_duration=10080,
            reason=reason[:450],
        )

    async def copy_attachments(self, source: discord.Message, target: discord.Thread) -> int:
        copied = 0
        for attachment in source.attachments or []:
            try:
                await target.send(file=await attachment.to_file(use_cached=True))
                copied += 1
            except Exception:
                try:
                    await target.send(attachment.url)
                    copied += 1
                except Exception:
                    pass
        return copied

    async def create_bo(self, message: discord.Message) -> None:
        if not message.guild or int(message.channel.id) != BO_SOURCE_ID:
            return
        key = ("bo", int(message.id))
        if key in self.processing or has_source("bo", message.id):
            return
        text = message_text(message)
        if "boletim de ocorr" not in normalized(text):
            return
        self.processing.add(key)
        try:
            mo = month_key(local_dt(message))
            number = four_digit_number(text, ("boletim", "b o", "ocorrencia")) or next_number("bo", mo)
            parent = await self.channel(BO_TARGET_ID)
            if not isinstance(parent, discord.TextChannel):
                raise RuntimeError(f"canal de atendimento BO {BO_TARGET_ID} indisponível")
            thread = await self.create_thread(parent, f"📋 BOLETIM DE OCORRÊNCIA — Nº {number}", f"DICOR V603 • BO {number}")
            record_id = f"BO-{message.id}"
            state = load_state()
            state.setdefault("bo", []).append({
                "id": record_id,
                "number": number,
                "month": mo,
                "source_message_id": message.id,
                "source_channel_id": BO_SOURCE_ID,
                "thread_id": thread.id,
                "agent_id": None,
                "agent_name": "",
                "status": "AGUARDANDO_AGENTE",
                "created_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "source_url": message.jump_url,
                "attachments": len(message.attachments or []),
            })
            save_state(state)
            embed = discord.Embed(
                title=f"📋 BOLETIM DE OCORRÊNCIA — Nº {number}",
                description=(text[:3800] if text else "Sem descrição textual."),
            )
            embed.add_field(name="Status", value="🟡 Aguardando agente", inline=True)
            embed.add_field(name="Responsável", value="Ainda não selecionado", inline=True)
            embed.add_field(name="Origem", value=message.jump_url, inline=False)
            await thread.send(embed=embed, view=AtendimentoView(self, "bo"))
            await self.copy_attachments(message, thread)
            await send_log(self.client, f"✅ V603 BO automático | Nº {number} | origem {message.id} | tópico {thread.id}")
        except Exception as exc:
            traceback.print_exc()
            await send_log(self.client, f"❌ V603 BO {message.id}: {type(exc).__name__}: {exc}")
        finally:
            self.processing.discard(key)

    async def create_pericia(self, message: discord.Message) -> None:
        if not message.guild or int(message.channel.id) != PERICIA_SOURCE_ID:
            return
        key = ("pericia", int(message.id))
        if key in self.processing or has_source("pericia", message.id):
            return
        # Mensagens geradas pelo próprio V603 não são tratadas porque ficam dentro do tópico.
        self.processing.add(key)
        try:
            text = message_text(message)
            mo = month_key(local_dt(message))
            number = four_digit_number(text, ("per[ií]cia", "laudo")) or next_number("pericia", mo)
            parent = await self.channel(PERICIA_SOURCE_ID)
            if not isinstance(parent, discord.TextChannel):
                raise RuntimeError(f"canal de Perícia Externa {PERICIA_SOURCE_ID} indisponível")
            thread = await self.create_thread(parent, f"🔬 PERÍCIA Nº {number} • AGUARDANDO AGENTE", f"DICOR V603 • Perícia {number}")
            record_id = f"PERICIA-{message.id}"
            state = load_state()
            state.setdefault("pericia", []).append({
                "id": record_id,
                "number": number,
                "month": mo,
                "source_message_id": message.id,
                "source_channel_id": PERICIA_SOURCE_ID,
                "thread_id": thread.id,
                "agent_id": None,
                "agent_name": "",
                "status": "AGUARDANDO_AGENTE",
                "created_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "source_url": message.jump_url,
                "attachments": len(message.attachments or []),
            })
            save_state(state)
            embed = discord.Embed(
                title=f"🔬 CONTROLE DA PERÍCIA EXTERNA — Nº {number}",
                description="Fluxo controlado da DICOR. Um Inspetor+ deve selecionar o agente responsável.",
            )
            embed.add_field(name="Status", value="🟡 Aguardando agente", inline=True)
            embed.add_field(name="Evidências copiadas", value=str(len(message.attachments or [])), inline=True)
            embed.add_field(name="Origem", value=message.jump_url, inline=False)
            await thread.send(embed=embed, view=AtendimentoView(self, "pericia"))
            await self.copy_attachments(message, thread)
            await send_log(self.client, f"✅ V603 Perícia automática | Nº {number} | origem {message.id} | tópico {thread.id}")
        except Exception as exc:
            traceback.print_exc()
            await send_log(self.client, f"❌ V603 Perícia {message.id}: {type(exc).__name__}: {exc}")
        finally:
            self.processing.discard(key)

    async def on_message(self, message: discord.Message) -> None:
        if not message.guild:
            return
        channel_id = int(getattr(message.channel, "id", 0) or 0)
        if channel_id == BO_SOURCE_ID:
            await self.create_bo(message)
        elif channel_id == PERICIA_SOURCE_ID:
            await self.create_pericia(message)

    async def scan_channel(self, kind: str, channel_id: int, guild: discord.Guild) -> None:
        channel = await self.channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            async for message in channel.history(limit=SCAN_MESSAGES, oldest_first=False):
                if kind == "bo":
                    await self.create_bo(message)
                else:
                    await self.create_pericia(message)
        except Exception as exc:
            await send_log(self.client, f"⚠️ V603 scanner {kind}: {type(exc).__name__}: {exc}")

    async def scanner(self) -> None:
        await asyncio.sleep(3)
        while True:
            try:
                for guild in list(self.client.guilds):
                    await self.scan_channel("bo", BO_SOURCE_ID, guild)
                    await self.scan_channel("pericia", PERICIA_SOURCE_ID, guild)
            except Exception:
                traceback.print_exc()
            await asyncio.sleep(SCAN_SECONDS)

    async def on_ready(self) -> None:
        if self.scanner_task is None or self.scanner_task.done():
            self.scanner_task = asyncio.create_task(self.scanner(), name="dicor-v603-scanner")
        await send_log(self.client, "🟢 V603 pronto | scanner automático BO + Perícia ativo")

    # ------------------------- Dossiê -------------------------
    def topic_code(self, text: str) -> int:
        n = normalized(text)
        aliases = [
            ("painel", "organizacao", "lider"),
            ("fotos dos lideres", "foto lider"),
            ("fotos dos membros", "foto membro", "integrantes"),
            ("radio", "comunicacao"),
            ("localizacao", "coordenada", "endereco"),
            ("crimes da comunidade", "crime", "ocorrencia"),
            ("bau de lider",),
            ("bau de membros",),
            ("rota de farm", "farm"),
            ("rota de producao", "producao"),
            ("ingredientes base", "produto", "ingrediente"),
            ("informante", "informacoes do informante"),
            ("informacoes gerais",),
            ("assinatura", "assinaturas"),
            ("conclusao", "analise consolidada", "encerramento"),
        ]
        for idx, words in enumerate(aliases, start=1):
            if any(w in n for w in words):
                return idx
        return 15

    async def collect_dossier(self, channel: discord.abc.GuildChannel) -> list[list[dict[str, Any]]]:
        groups: list[list[dict[str, Any]]] = [[] for _ in TOPICS]
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
                pass
        for thread in threads:
            try:
                async for message in thread.history(limit=None, oldest_first=True):
                    text = message_text(message)
                    item = {
                        "date": local_dt(message).strftime("%d/%m/%Y %H:%M"),
                        "author": str(message.author),
                        "thread": str(thread.name),
                        "text": text or "[mídia sem texto]",
                        "attachments": [a.url for a in message.attachments or []],
                    }
                    groups[self.topic_code(f"{thread.name} {text}") - 1].append(item)
            except Exception:
                continue
        return groups

    def draw_header(self, canvas_obj, doc) -> None:
        width, height = A4
        # Moldura dupla inspirada no modelo enviado, sem imagem/base64 externo.
        canvas_obj.saveState()
        canvas_obj.setStrokeColor(colors.HexColor("#B58A2A"))
        canvas_obj.setLineWidth(1.4)
        canvas_obj.rect(10 * mm, 10 * mm, width - 20 * mm, height - 20 * mm)
        canvas_obj.setStrokeColor(colors.HexColor("#5E8297"))
        canvas_obj.setLineWidth(0.6)
        canvas_obj.rect(14 * mm, 14 * mm, width - 28 * mm, height - 28 * mm)
        # Escudos estilizados: PF à esquerda e DICOR à direita.
        for x, fill, top, bottom in [
            (30 * mm, colors.HexColor("#D5B64A"), "POLÍCIA", "FEDERAL"),
            (width - 48 * mm, colors.HexColor("#294A63"), "DICOR", "PF"),
        ]:
            path = canvas_obj.beginPath()
            path.moveTo(x, height - 42 * mm)
            path.lineTo(x + 18 * mm, height - 35 * mm)
            path.lineTo(x + 16 * mm, height - 62 * mm)
            path.lineTo(x + 2 * mm, height - 62 * mm)
            path.close()
            canvas_obj.setFillColor(fill)
            canvas_obj.setStrokeColor(colors.HexColor("#B58A2A"))
            canvas_obj.drawPath(path, fill=1, stroke=1)
            canvas_obj.setFillColor(colors.white if fill == colors.HexColor("#294A63") else colors.black)
            canvas_obj.setFont("Helvetica-Bold", 7.5)
            canvas_obj.drawCentredString(x + 9 * mm, height - 46 * mm, top)
            canvas_obj.drawCentredString(x + 9 * mm, height - 52 * mm, bottom)
        canvas_obj.setFillColor(colors.black)
        canvas_obj.setFont("Helvetica-Bold", 17)
        canvas_obj.drawCentredString(width / 2, height - 31 * mm, "POLÍCIA FEDERAL — DICOR")
        canvas_obj.setFont("Helvetica-Bold", 11)
        canvas_obj.drawCentredString(width / 2, height - 39 * mm, "DO ESTADO DA CAPITAL")
        canvas_obj.setFont("Helvetica-Bold", 11)
        canvas_obj.drawCentredString(width / 2, height - 47 * mm, "MORADA DO VALLEY")
        canvas_obj.restoreState()

    async def build_dossier(self, channel: discord.abc.GuildChannel) -> Path:
        if SimpleDocTemplate is None:
            raise RuntimeError("ReportLab não está instalado")
        groups = await self.collect_dossier(channel)
        output = DOC_DIR / f"DOSSIE-PF-DICOR-{channel.id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
        doc = SimpleDocTemplate(
            str(output), pagesize=A4,
            rightMargin=22 * mm, leftMargin=22 * mm,
            topMargin=61 * mm, bottomMargin=18 * mm,
            title="Dossiê Operacional — Polícia Federal DICOR",
            author="DICOR Intelligence",
        )
        title_style = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=13, leading=17, alignment=TA_CENTER, spaceAfter=10)
        section_style = ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=11, leading=14, alignment=TA_LEFT, textColor=colors.HexColor("#B58A2A"), spaceAfter=8)
        body_style = ParagraphStyle("body", fontName="Helvetica", fontSize=8.8, leading=12, alignment=TA_LEFT, spaceAfter=5)
        small_style = ParagraphStyle("small", fontName="Helvetica", fontSize=7.5, leading=10, textColor=colors.HexColor("#444444"))
        story: list[Any] = []
        story.append(Paragraph("DOSSIÊ OPERACIONAL", title_style))
        story.append(Paragraph("POLÍCIA FEDERAL — DICOR", title_style))
        story.append(Paragraph(f"Mesa/Origem: {clean(getattr(channel, 'name', channel.id))}", body_style))
        story.append(Paragraph(f"Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}", body_style))
        story.append(Spacer(1, 4 * mm))
        story.append(PageBreak())
        for index, topic in enumerate(TOPICS):
            story.append(Paragraph(f"{index + 1:02d} — {topic.upper()}", section_style))
            rows = groups[index]
            if not rows:
                story.append(Paragraph("Nenhum registro encontrado nesta seção.", body_style))
            else:
                for row in rows:
                    header = f"<b>{row['date']}</b> • {row['author']} • {row['thread']}"
                    story.append(Paragraph(header, small_style))
                    safe = row["text"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
                    story.append(Paragraph(safe[:5000], body_style))
                    if row["attachments"]:
                        story.append(Paragraph(f"Evidências anexadas: {len(row['attachments'])}", small_style))
            if index != len(TOPICS) - 1:
                story.append(PageBreak())
        story.append(PageBreak())
        story.append(Paragraph("DECLARAÇÃO DE ENCERRAMENTO", section_style))
        story.append(Paragraph("Documento consolidado automaticamente a partir dos registros disponíveis na mesa. A análise e a validação final permanecem sob responsabilidade da DICOR.", body_style))
        story.append(Spacer(1, 30 * mm))
        story.append(Paragraph("POLÍCIA FEDERAL — DICOR", title_style))
        doc.build(story, onFirstPage=self.draw_header, onLaterPages=self.draw_header)
        return output

    async def dossie_command(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not authorized(interaction.user):
            await reply(interaction, "❌ Apenas Inspetor+ pode gerar o Dossiê Operacional.")
            return
        if not await defer(interaction):
            return
        try:
            output = await self.build_dossier(interaction.channel)
            await reply(interaction, f"✅ Dossiê criado: `{output.name}`")
            if isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
                await interaction.channel.send(file=discord.File(str(output), filename=output.name))
        except Exception as exc:
            traceback.print_exc()
            await reply(interaction, f"❌ Falha na criação do Dossiê: {type(exc).__name__}: {exc}")


def install(bot_module: Any) -> CoreV603:
    client = getattr(bot_module, "bot", None)
    if client is None or not hasattr(client, "add_listener"):
        raise RuntimeError("cliente Discord inválido para o Core V603")
    existing = getattr(client, "_dicor_v603_core", None)
    if existing is not None:
        return existing
    core = CoreV603(client)
    client._dicor_v603_core = core
    client.add_listener(core.on_message, "on_message")
    client.add_listener(core.on_ready, "on_ready")
    try:
        client.add_view(AtendimentoView(core, "bo"))
        client.add_view(AtendimentoView(core, "pericia"))
    except Exception:
        traceback.print_exc()
    try:
        if client.tree.get_command("dossie") is None:
            client.tree.add_command(app_commands.Command(name="dossie", description="Gera o Dossiê Operacional da mesa atual", callback=core.dossie_command))
    except Exception:
        traceback.print_exc()
    print(
        f"✅ DICOR Core V603 instalado | BO {BO_SOURCE_ID}->{BO_TARGET_ID} | Perícia {PERICIA_SOURCE_ID} | scanner {SCAN_SECONDS}s",
        flush=True,
    )
    return core
