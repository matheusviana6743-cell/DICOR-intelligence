# -*- coding: utf-8 -*-
"""DICOR Core V604

Núcleo único para BO, Perícia Externa e Dossiê.
- qualquer mensagem nova na origem oficial abre atendimento automaticamente;
- mensagens recebidas durante deploy/restart são recuperadas pelo scanner;
- número oficial da origem é preservado e nunca é renomeado pelo núcleo;
- se a origem não trouxer número, é criado número de 4 dígitos por mês;
- seleção de responsável continua restrita a Inspetor+;
- PDF do dossiê é gerado localmente, sem base64/template externo.
"""
from __future__ import annotations

import asyncio
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
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
except Exception:
    colors = None
    TA_CENTER = TA_LEFT = None
    A4 = None
    ParagraphStyle = None
    mm = None
    SimpleDocTemplate = Paragraph = Spacer = PageBreak = None

BO_SOURCE_ID = int(os.getenv("DICOR_BO_SOURCE_ID", "1490200514837745754"))
BO_TARGET_ID = int(os.getenv("DICOR_BO_TARGET_ID", "1525762770253910136"))
PERICIA_SOURCE_ID = int(os.getenv("DICOR_PERICIA_SOURCE_ID", "1490200524367200297"))
LOG_ID = int(os.getenv("LOGS_CHANNEL_ID", "1490205503228477610"))
SCAN_SECONDS = max(5, int(os.getenv("DICOR_AUTO_SCAN_SECONDS", "10")))
SCAN_MESSAGES = max(500, int(os.getenv("DICOR_AUTO_SCAN_MESSAGES", "2000")))
DATA_DIR = Path(os.getenv("DICOR_DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "dicor_core_v604.json"
DOC_DIR = DATA_DIR / "dossies_v604"
DOC_DIR.mkdir(parents=True, exist_ok=True)

AUTH_ROLE_IDS = {
    int(x) for x in os.getenv(
        "DICOR_AUTH_ROLE_IDS",
        "1490200388912156692,1490200383614615725,1490200382776021132",
    ).replace(";", ",").split(",") if x.strip().isdigit()
}
TEAM_ROLE_IDS = {
    int(x) for x in os.getenv(
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
]


def _default_state() -> dict[str, Any]:
    return {"bo": [], "pericia": [], "counters": {"bo": {}, "pericia": {}}}


def load_state() -> dict[str, Any]:
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _default_state()
                base.update(data)
                base.setdefault("bo", [])
                base.setdefault("pericia", [])
                base.setdefault("counters", {"bo": {}, "pericia": {}})
                return base
    except Exception:
        traceback.print_exc()
    return _default_state()


def save_state(state: dict[str, Any]) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def norm(value: Any) -> str:
    text = " ".join(str(value or "").split()).casefold()
    return re.sub(r"[^0-9a-zA-ZÀ-ÿ]+", " ", text).strip()


def text_of(message: discord.Message) -> str:
    parts = [message.content or ""]
    for embed in message.embeds or []:
        parts.extend([embed.title or "", embed.description or ""])
        for field in embed.fields or []:
            parts.extend([field.name or "", field.value or ""])
    return "\n".join(p for p in parts if p).strip()


def month_of(message: discord.Message) -> str:
    dt = message.created_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%m/%Y")


def extract_number(text: str, kind: str) -> str:
    labels = ("boletim", "ocorrência", "ocorrencia", "b.o") if kind == "bo" else ("perícia", "pericia", "laudo")
    for label in labels:
        m = re.search(rf"{label}[^0-9]{{0,45}}(?:n[º°o.]?\s*)?(\d{{1,8}})", text, re.I)
        if m:
            return f"{int(m.group(1)):04d}"
    for pattern in (r"(?:N[º°O.]?|NO|#)\s*(\d{1,8})", r"\b(\d{4,8})\b"):
        m = re.search(pattern, text, re.I)
        if m:
            return f"{int(m.group(1)):04d}"
    return ""


def next_number(kind: str, month: str) -> str:
    state = load_state()
    records = state.setdefault(kind, [])
    counters = state.setdefault("counters", {}).setdefault(kind, {})
    used = {str(r.get("number")) for r in records if str(r.get("month")) == month}
    value = int(counters.get(month, 0) or 0)
    while f"{value + 1:04d}" in used:
        value += 1
    value += 1
    counters[month] = value
    save_state(state)
    return f"{value:04d}"


def record_for_source(kind: str, message_id: int) -> Optional[dict[str, Any]]:
    for row in load_state().get(kind, []):
        if str(row.get("source_message_id")) == str(message_id):
            return row
    return None


def record_for_thread(kind: str, thread_id: int) -> Optional[dict[str, Any]]:
    for row in load_state().get(kind, []):
        if str(row.get("thread_id")) == str(thread_id):
            return row
    return None


def update_record(kind: str, record_id: str, **patch: Any) -> Optional[dict[str, Any]]:
    state = load_state()
    for row in state.get(kind, []):
        if str(row.get("id")) == str(record_id):
            row.update(patch)
            save_state(state)
            return row
    return None


def authorized(member: discord.Member) -> bool:
    if any(getattr(r, "id", 0) in AUTH_ROLE_IDS for r in member.roles):
        return True
    return any("inspetor" in norm(r.name) or "diretor" in norm(r.name) for r in member.roles)


def selectable(member: discord.Member) -> bool:
    if member.bot:
        return False
    if any(getattr(r, "id", 0) in TEAM_ROLE_IDS for r in member.roles):
        return True
    keys = ("estagi", "investigador", "agente", "inspetor", "delegado", "dicor", "escriv")
    return any(k in norm(r.name) for r in member.roles for k in keys)


async def respond(interaction: discord.Interaction, text: str) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except Exception:
        pass


async def ack(interaction: discord.Interaction) -> bool:
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
        return True
    except Exception:
        return False


async def log(client: discord.Client, text: str) -> None:
    try:
        channel = client.get_channel(LOG_ID) or await client.fetch_channel(LOG_ID)
        await channel.send(text[:1900])
    except Exception:
        pass


class AgentSelect(UserSelect):
    def __init__(self, core: "CoreV604", kind: str):
        self.core = core
        self.kind = kind
        super().__init__(
            placeholder="Inspetor+: selecione o agente responsável",
            min_values=1,
            max_values=1,
            custom_id=f"dicor_v604_{kind}_agent",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not authorized(interaction.user):
            await respond(interaction, "❌ Apenas Inspetor+ pode selecionar o responsável.")
            return
        if not await ack(interaction):
            return
        member = self.values[0] if self.values else None
        thread_id = int(getattr(interaction.channel, "id", 0) or 0)
        row = record_for_thread(self.kind, thread_id)
        if not row or not isinstance(member, discord.Member) or not selectable(member):
            await respond(interaction, "❌ Atendimento ou agente inválido.")
            return
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        update_record(self.kind, row["id"], agent_id=member.id, agent_name=str(member), status="EM_ATENDIMENTO", assigned_at=now)
        try:
            await interaction.channel.add_user(member)
        except Exception:
            pass
        label = "BO" if self.kind == "bo" else "Perícia"
        try:
            await interaction.channel.send(f"👤 **{label} atribuído.** Responsável: {member.mention}")
        except Exception:
            pass
        await respond(interaction, f"✅ {label} Nº **{row['number']}** atribuído a {member.mention}.")


class AtendimentoView(View):
    def __init__(self, core: "CoreV604", kind: str):
        super().__init__(timeout=None)
        self.kind = kind
        self.add_item(AgentSelect(core, kind))
        button = Button(
            label="Finalizar atendimento" if kind == "bo" else "Concluir perícia",
            emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id=f"dicor_v604_{kind}_finish",
        )
        button.callback = self.finish
        self.add_item(button)

    async def finish(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not authorized(interaction.user):
            await respond(interaction, "❌ Apenas Inspetor+ pode concluir este atendimento.")
            return
        if not await ack(interaction):
            return
        row = record_for_thread(self.kind, int(getattr(interaction.channel, "id", 0) or 0))
        if not row:
            await respond(interaction, "❌ Registro não encontrado.")
            return
        if not row.get("agent_id"):
            await respond(interaction, "⚠️ Selecione o agente responsável primeiro.")
            return
        update_record(self.kind, row["id"], status="CONCLUIDO", closed_at=datetime.now().strftime("%d/%m/%Y %H:%M"))
        await respond(interaction, "✅ Atendimento concluído e salvo.")


class CoreV604:
    def __init__(self, client: discord.Client):
        self.client = client
        self.busy: set[tuple[str, int]] = set()
        self.scanner_task: Optional[asyncio.Task] = None

    async def channel(self, channel_id: int):
        channel = self.client.get_channel(channel_id)
        if channel:
            return channel
        try:
            return await self.client.fetch_channel(channel_id)
        except Exception:
            return None

    async def create_private_thread(self, parent: discord.TextChannel, name: str, reason: str) -> discord.Thread:
        try:
            return await parent.create_thread(
                name=name[:100], type=discord.ChannelType.private_thread,
                invitable=False, auto_archive_duration=10080, reason=reason[:450],
            )
        except discord.HTTPException:
            return await parent.create_thread(
                name=name[:100], type=discord.ChannelType.private_thread,
                invitable=False, auto_archive_duration=1440, reason=reason[:450],
            )

    async def copy_files(self, source: discord.Message, thread: discord.Thread) -> int:
        total = 0
        for attachment in source.attachments or []:
            try:
                await thread.send(file=await attachment.to_file(use_cached=True))
                total += 1
            except Exception:
                try:
                    await thread.send(attachment.url)
                    total += 1
                except Exception:
                    pass
        return total

    async def add_default_members(self, thread: discord.Thread, guild: discord.Guild, source: discord.Message) -> None:
        candidates: list[discord.Member] = []
        author = source.author if isinstance(source.author, discord.Member) else None
        if author and not author.bot:
            candidates.append(author)
        for member in guild.members:
            if member.bot:
                continue
            if authorized(member):
                candidates.append(member)
        seen: set[int] = set()
        for member in candidates:
            if member.id in seen:
                continue
            seen.add(member.id)
            try:
                await thread.add_user(member)
            except Exception:
                pass
            if len(seen) >= 10:
                break

    async def create_attendance(self, kind: str, message: discord.Message) -> bool:
        source_id = BO_SOURCE_ID if kind == "bo" else PERICIA_SOURCE_ID
        target_id = BO_TARGET_ID if kind == "bo" else PERICIA_SOURCE_ID
        if not message.guild or int(message.channel.id) != source_id:
            return False
        if record_for_source(kind, message.id):
            return False
        key = (kind, int(message.id))
        if key in self.busy:
            return False
        self.busy.add(key)
        try:
            month = month_of(message)
            text = text_of(message)
            number = extract_number(text, kind) or next_number(kind, month)
            parent = await self.channel(target_id)
            if not isinstance(parent, discord.TextChannel):
                raise RuntimeError(f"canal destino {target_id} indisponível")
            prefix = "📋 BOLETIM DE OCORRÊNCIA" if kind == "bo" else "🔬 PERÍCIA"
            # Nome é definido UMA ÚNICA VEZ. Nenhum loop do núcleo renomeia a thread.
            thread = await self.create_private_thread(parent, f"{prefix} — Nº {number}" if kind == "bo" else f"🔬 PERÍCIA Nº {number} • AGUARDANDO AGENTE", f"DICOR V604 • {kind} {number}")
            await self.add_default_members(thread, message.guild, message)
            embed = discord.Embed(
                title=(f"📋 BOLETIM DE OCORRÊNCIA — Nº {number}" if kind == "bo" else f"🔬 CONTROLE DA PERÍCIA EXTERNA — Nº {number}"),
                description=text[:3800] if text else "Sem texto. Evidências anexadas na origem.",
                color=0xC8A84E,
            )
            embed.add_field(name="Status", value="🟡 Aguardando agente", inline=True)
            embed.add_field(name="Responsável", value="Ainda não selecionado", inline=True)
            embed.add_field(name="Origem", value=message.jump_url, inline=False)
            copied = await self.copy_files(message, thread)
            embed.add_field(name="Evidências copiadas", value=str(copied), inline=True)
            await thread.send(embed=embed, view=AtendimentoView(self, kind))
            state = load_state()
            state.setdefault(kind, []).append({
                "id": f"{kind.upper()}-{message.id}",
                "number": number,
                "month": month,
                "source_message_id": message.id,
                "source_channel_id": source_id,
                "thread_id": thread.id,
                "agent_id": None,
                "agent_name": "",
                "status": "AGUARDANDO_AGENTE",
                "created_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "source_url": message.jump_url,
                "attachments": len(message.attachments or []),
            })
            save_state(state)
            await log(self.client, f"✅ V604 {kind.upper()} automático | Nº {number} | origem={message.id} | tópico={thread.id}")
            return True
        except Exception as exc:
            traceback.print_exc()
            await log(self.client, f"❌ V604 {kind.upper()} {message.id}: {type(exc).__name__}: {exc}")
            return False
        finally:
            self.busy.discard(key)

    async def on_message(self, message: discord.Message) -> None:
        if not message.guild:
            return
        cid = int(getattr(message.channel, "id", 0) or 0)
        # IMPORTANTE: não existe mais filtro pelo texto. O canal oficial é o gatilho.
        if cid == BO_SOURCE_ID:
            await self.create_attendance("bo", message)
        elif cid == PERICIA_SOURCE_ID:
            await self.create_attendance("pericia", message)

    async def recover_channel(self, kind: str, channel_id: int) -> tuple[int, int]:
        channel = await self.channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return (0, 0)
        seen = 0
        created = 0
        try:
            async for message in channel.history(limit=SCAN_MESSAGES, oldest_first=True):
                seen += 1
                if await self.create_attendance(kind, message):
                    created += 1
        except Exception as exc:
            await log(self.client, f"⚠️ V604 scanner {kind}: {type(exc).__name__}: {exc}")
        return seen, created

    async def scanner(self) -> None:
        await asyncio.sleep(2)
        while True:
            try:
                bo_seen, bo_created = await self.recover_channel("bo", BO_SOURCE_ID)
                pe_seen, pe_created = await self.recover_channel("pericia", PERICIA_SOURCE_ID)
                await log(self.client, f"🔎 V604 scanner | BO vistos={bo_seen} novos={bo_created} | Perícias vistas={pe_seen} novas={pe_created}")
            except Exception as exc:
                traceback.print_exc()
                await log(self.client, f"⚠️ V604 scanner geral: {type(exc).__name__}: {exc}")
            await asyncio.sleep(SCAN_SECONDS)

    async def on_ready(self) -> None:
        if self.scanner_task is None or self.scanner_task.done():
            self.scanner_task = asyncio.create_task(self.scanner(), name="dicor-v604-scanner")
        await log(self.client, "🟢 V604 READY | gatilho por canal + recuperação automática ativos")

    def topic_index(self, name: str) -> int:
        n = norm(name)
        aliases = [
            ("painel", "organizacao"), ("fotos dos lideres", "foto lider"),
            ("fotos dos membros", "foto membro"), ("radio", "comunicacao"),
            ("localizacao", "coordenada", "endereco"), ("crimes da comunidade", "crime"),
            ("bau de lider",), ("bau de membros",), ("rota de farm", "farm"),
            ("rota de producao", "producao"), ("ingredientes base", "produto", "ingrediente"),
            ("informante",), ("informacoes gerais",),
        ]
        for idx, keys in enumerate(aliases):
            if any(k in n for k in keys):
                return idx
        return 12

    async def build_dossier(self, channel: Any) -> Path:
        if SimpleDocTemplate is None:
            raise RuntimeError("ReportLab não está disponível")
        groups: list[list[tuple[str, str, str]]] = [[] for _ in TOPICS]
        threads: list[discord.Thread] = []
        if isinstance(channel, discord.Thread):
            threads = [channel]
        else:
            try:
                active = list(getattr(channel, "threads", []) or [])
                archived = [t async for t in channel.archived_threads(limit=None)]
                ids = {t.id for t in active}
                threads = active + [t for t in archived if t.id not in ids]
            except Exception:
                pass
        for thread in threads:
            try:
                async for message in thread.history(limit=None, oldest_first=True):
                    text = text_of(message) or "[mídia sem texto]"
                    idx = self.topic_index(f"{thread.name} {text}")
                    groups[idx].append((local_date(message), str(message.author), text))
            except Exception:
                continue
        path = DOC_DIR / f"DOSSIE-PF-DICOR-{getattr(channel, 'id', 'mesa')}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
        doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=50*mm, bottomMargin=18*mm, title="Dossiê Operacional PF DICOR")
        title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=16, leading=19, alignment=TA_CENTER, textColor=colors.HexColor("#1F3444"), spaceAfter=8)
        section = ParagraphStyle("s", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#B58A2A"), spaceAfter=7)
        body = ParagraphStyle("b", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.black, spaceAfter=5)
        story: list[Any] = [Paragraph("POLÍCIA FEDERAL — DICOR", title), Paragraph("DOSSIÊ OPERACIONAL", title), Paragraph(f"Mesa: {getattr(channel, 'name', getattr(channel, 'id', ''))}", body), Paragraph(f"Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}", body), PageBreak()]
        for i, topic in enumerate(TOPICS):
            story.append(Paragraph(f"{i+1:02d}. {topic.upper()}", section))
            rows = groups[i]
            if not rows:
                story.append(Paragraph("Nenhum registro encontrado nesta seção.", body))
            else:
                for date, author, text in rows:
                    safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>"))[:4500]
                    story.append(Paragraph(f"<b>{date} • {author}</b><br/>{safe}", body))
            if i < len(TOPICS)-1:
                story.append(PageBreak())
        story += [PageBreak(), Paragraph("ENCERRAMENTO", section), Paragraph("Documento consolidado automaticamente a partir dos registros da mesa. A validação final permanece sob responsabilidade da DICOR.", body), Spacer(1, 30*mm), Paragraph("POLÍCIA FEDERAL — DICOR", title)]
        def header(canvas_obj, doc_obj):
            w, h = A4
            canvas_obj.saveState()
            canvas_obj.setStrokeColor(colors.HexColor("#B58A2A")); canvas_obj.setLineWidth(1.3); canvas_obj.rect(10*mm,10*mm,w-20*mm,h-20*mm)
            canvas_obj.setStrokeColor(colors.HexColor("#5E8297")); canvas_obj.setLineWidth(.6); canvas_obj.rect(14*mm,14*mm,w-28*mm,h-28*mm)
            canvas_obj.setFillColor(colors.HexColor("#1F3444")); canvas_obj.setFont("Helvetica-Bold", 13); canvas_obj.drawCentredString(w/2,h-27*mm,"POLÍCIA FEDERAL — DICOR")
            canvas_obj.setFillColor(colors.HexColor("#B58A2A")); canvas_obj.setFont("Helvetica-Bold", 8); canvas_obj.drawCentredString(w/2,h-34*mm,"DOCUMENTO OPERACIONAL")
            canvas_obj.restoreState()
        doc.build(story, onFirstPage=header, onLaterPages=header)
        return path

    async def dossie_command(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not authorized(interaction.user):
            await respond(interaction, "❌ Apenas Inspetor+ pode gerar o Dossiê.")
            return
        if not await ack(interaction):
            return
        try:
            path = await self.build_dossier(interaction.channel)
            await interaction.followup.send(content=f"✅ Dossiê criado: **{path.name}**", file=discord.File(str(path)), ephemeral=False)
        except Exception as exc:
            traceback.print_exc()
            await respond(interaction, f"❌ Falha ao gerar Dossiê: {type(exc).__name__}: {exc}")


def local_date(message: discord.Message) -> str:
    dt = message.created_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%d/%m/%Y %H:%M")


def install(bot_module: Any) -> CoreV604:
    client = getattr(bot_module, "bot", None)
    if client is None or not hasattr(client, "add_listener"):
        raise RuntimeError("cliente Discord inválido")
    existing = getattr(client, "_dicor_v604_core", None)
    if existing is not None:
        return existing
    core = CoreV604(client)
    client._dicor_v604_core = core
    client.add_listener(core.on_message, "on_message")
    client.add_listener(core.on_ready, "on_ready")
    try:
        client.add_view(AtendimentoView(core, "bo"))
        client.add_view(AtendimentoView(core, "pericia"))
    except Exception:
        traceback.print_exc()
    try:
        if client.tree.get_command("dossie") is None:
            client.tree.add_command(app_commands.Command(name="dossie", description="Gerar Dossiê Operacional da mesa atual", callback=core.dossie_command))
    except Exception:
        traceback.print_exc()
    print(f"✅ DICOR Core V604 instalado | BO {BO_SOURCE_ID}->{BO_TARGET_ID} | Perícia {PERICIA_SOURCE_ID} | scanner={SCAN_SECONDS}s", flush=True)
    return core
