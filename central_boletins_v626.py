# -*- coding: utf-8 -*-
"""Central DICOR V626 — módulo completo de Boletins e Perícias.

Não altera a resolução dos atendimentos do Discord. Apenas melhora a
visualização na Central web: lista, busca, detalhes completos e fotos/anexos.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import aiohttp
import central_discord_v613 as base
import central_procurados_v625 as previous

_CLIENT: Any = None
_ORIGINAL_START = previous._ORIGINAL_START


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def text_of(message: Any) -> str:
    parts = [getattr(message, "content", "") or ""]
    for embed in getattr(message, "embeds", []) or []:
        for attr in ("title", "description"):
            parts.append(getattr(embed, attr, "") or "")
        author = getattr(embed, "author", None)
        if author:
            parts.append(getattr(author, "name", "") or "")
        for field in getattr(embed, "fields", []) or []:
            parts.append(f"{getattr(field, 'name', '')}: {getattr(field, 'value', '')}")
    return clean_text("\n".join(str(x) for x in parts if x))


def clean_text(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", str(text or ""))
    text = re.sub(r"[*_~`]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def attachment_rows(message: Any) -> list[dict[str, str]]:
    rows = []
    for attachment in getattr(message, "attachments", []) or []:
        url = str(getattr(attachment, "url", "") or "")
        ctype = str(getattr(attachment, "content_type", "") or "")
        filename = str(getattr(attachment, "filename", "arquivo") or "arquivo")
        kind = "image" if ctype.startswith("image/") or re.search(r"\.(png|jpe?g|webp|gif)$", filename, re.I) else "file"
        rows.append({"url": url, "filename": filename, "kind": kind})
    return rows


def embed_images(message: Any) -> list[str]:
    urls: list[str] = []
    for embed in getattr(message, "embeds", []) or []:
        for attr in ("image", "thumbnail"):
            obj = getattr(embed, attr, None)
            url = str(getattr(obj, "url", "") or "") if obj else ""
            if url:
                urls.append(url)
    return list(dict.fromkeys(urls))


def status_label(row: dict[str, Any]) -> str:
    raw = clean_text(row.get("name", ""))
    if re.search(r"finaliz|encerr|conclu", raw, re.I):
        return "FINALIZADO"
    return "EM ATENDIMENTO"


def list_card(row: dict[str, Any], href: str) -> str:
    created = row.get("created")
    try:
        date = created.astimezone().strftime("%d/%m/%Y • %H:%M")
    except Exception:
        date = "--"
    status = status_label(row)
    color = "done" if status == "FINALIZADO" else "active"
    return f'''<a class="record" href="{esc(href)}"><div class="record-main"><div class="record-top"><span class="record-number">BO {esc(row.get("number") or "---")}</span><span class="status {color}">{status}</span></div><h3>{esc(row.get("name") or "Boletim de Ocorrência")}</h3><div class="record-meta"><span>Recebido {esc(date)}</span><span>{esc(row.get("kind", "bo").upper())}</span></div></div><div class="record-arrow">→</div></a>'''


async def fetch_thread_messages(thread: Any, limit: int = 100) -> list[Any]:
    messages = []
    try:
        async for message in thread.history(limit=limit, oldest_first=True):
            messages.append(message)
    except Exception as exc:
        print(f"⚠️ V626 mensagens: {type(exc).__name__}: {exc}", flush=True)
    return messages


async def get_thread_by_id(tid: int) -> Any:
    if not _CLIENT:
        return None
    try:
        for guild in getattr(_CLIENT, "guilds", []) or []:
            thread = guild.get_thread(tid)
            if thread:
                return thread
        for guild in getattr(_CLIENT, "guilds", []) or []:
            for channel in getattr(guild, "text_channels", []) or []:
                for thread in getattr(channel, "threads", []) or []:
                    if getattr(thread, "id", 0) == tid:
                        return thread
    except Exception:
        pass
    try:
        return await _CLIENT.fetch_channel(tid)
    except Exception:
        return None


async def boletim_detail(req: Any):
    session = base.read_session(req)
    if not session:
        raise base.web.HTTPFound("/cadastro-operador?next=" + quote(req.path))
    tid = int(req.match_info.get("thread_id", "0"))
    thread = await get_thread_by_id(tid)
    if thread is None:
        raise base.web.HTTPNotFound(text="Boletim não encontrado.")

    messages = await fetch_thread_messages(thread, 150)
    attachments = []
    blocks = []
    for message in messages:
        text = text_of(message)
        for a in attachment_rows(message):
            attachments.append(a)
        for u in embed_images(message):
            attachments.append({"url": u, "filename": "imagem do boletim", "kind": "image"})
        if text:
            author = esc(getattr(getattr(message, "author", None), "display_name", getattr(getattr(message, "author", None), "name", "")))
            created = getattr(message, "created_at", None)
            try:
                dt = created.astimezone().strftime("%d/%m/%Y • %H:%M")
            except Exception:
                dt = "--"
            blocks.append(f'''<article class="message-block"><div class="message-head"><b>{author or "Sistema"}</b><span>{esc(dt)}</span></div><div class="message-text">{esc(text)}</div></article>''')

    photos = []
    files = []
    seen = set()
    for a in attachments:
        key = a.get("url") or a.get("filename")
        if key in seen:
            continue
        seen.add(key)
        if a.get("kind") == "image" and a.get("url"):
            photos.append(f'<a class="bo-photo" href="{esc(a["url"])}" target="_blank"><img src="{esc(a["url"])}" alt="{esc(a["filename"])}" loading="lazy"><span>{esc(a["filename"])}</span></a>')
        elif a.get("url"):
            files.append(f'<a class="bo-file" href="{esc(a["url"])}" target="_blank">📎 {esc(a["filename"])}</a>')

    title = clean_text(getattr(thread, "name", "Boletim de Ocorrência"))
    qra, passport = session
    body = f'''<div class="app"><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • BOLETIM COMPLETO</span></div><div class="operator"><i class="online"></i> {esc(qra)} • {esc(passport)}</div></header><a class="back" href="/boletins">← Voltar para os boletins</a><section class="detail-hero"><div class="eyebrow">CENTRAL DICOR • REGISTRO OPERACIONAL</div><h1>{esc(title)}</h1><div class="detail-id">ATENDIMENTO INTERNO • {esc(getattr(thread, "id", ""))}</div></section><div class="detail-grid"><section class="panel"><div class="panel-title">CONTEÚDO DO BOLETIM</div>{"".join(blocks) or '<div class="empty">Nenhum texto disponível neste atendimento.</div>'}</section><aside><section class="panel"><div class="panel-title">FOTOS E EVIDÊNCIAS VISUAIS</div><div class="photo-grid">{"".join(photos) or '<div class="empty">Nenhuma foto anexada.</div>'}</div></section><section class="panel"><div class="panel-title">ANEXOS</div>{"".join(files) or '<div class="empty">Nenhum anexo adicional.</div>'}</section></aside></div><div class="footer-note">Os dados exibidos foram sincronizados do atendimento correspondente no Discord.</div></main></div>'''

    css = base.APP_CSS + '''.back{display:inline-block;margin:12px 0;color:#79a9da;font-size:10px}.detail-hero{margin-top:10px;padding:25px;border:1px solid #244666;border-radius:17px;background:linear-gradient(115deg,#0a1827,#07111b)}.detail-hero h1{margin:8px 0;font-size:28px}.detail-id{color:#667d92;font-size:8px;letter-spacing:1px}.detail-grid{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(280px,.9fr);gap:14px;margin-top:14px}.panel{border:1px solid #1c344b;border-radius:15px;background:#070e16;overflow:hidden;margin-bottom:14px}.panel-title{padding:13px 15px;border-bottom:1px solid #172a3c;color:#d8b65c;font-size:10px;font-weight:900;letter-spacing:1.2px}.message-block{padding:14px 15px;border-bottom:1px solid #112232}.message-block:last-child{border-bottom:0}.message-head{display:flex;justify-content:space-between;gap:10px;color:#91abc0;font-size:8px;margin-bottom:8px}.message-text{color:#d7e0e8;font-size:10px;line-height:1.7;overflow-wrap:anywhere}.photo-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:10px}.bo-photo{display:block;border:1px solid #1c344b;border-radius:10px;overflow:hidden;background:#05090f}.bo-photo img{display:block;width:100%;height:150px;object-fit:cover}.bo-photo span{display:block;padding:7px;color:#91a6b8;font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.bo-file{display:block;margin:10px;padding:10px;border:1px solid #1c344b;border-radius:8px;color:#91b9df;font-size:9px;overflow-wrap:anywhere}.footer-note{color:#52687c;font-size:8px;text-align:center;margin-top:10px}.empty{padding:28px;text-align:center;color:#617588;font-size:9px}@media(max-width:850px){.detail-grid{grid-template-columns:1fr}.detail-hero h1{font-size:22px}}@media(max-width:520px){.photo-grid{grid-template-columns:1fr}.bo-photo img{height:190px}}
'''
    return base.web.Response(text=base.page("DICOR • Boletim", body, css), content_type="text/html")


async def listing_boletins(req: Any):
    session = base.read_session(req)
    if not session:
        raise base.web.HTTPFound("/cadastro-operador?next=/boletins")
    qra, passport = session
    rows = list(base.CACHE.get("bo", []))
    query = clean_text(req.query.get("q", "")).casefold()
    if query:
        rows = [r for r in rows if query in clean_text(r.get("name", "")).casefold() or query in clean_text(r.get("number", "")).casefold()]
    rows = sorted(rows, key=lambda r: r.get("created") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    cards = "".join(list_card(r, f"/boletim/{getattr(r, 'source_id', '')}") if getattr(r, 'source_id', 0) else list_card(r, r.get("url", "#")) for r in rows)
    body = f'''<div class="app"><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE BOLETINS</span></div><div class="operator"><i class="online"></i> {esc(qra)} • {esc(passport)}</div></header><div class="central-tabs"><a class="tab active" href="/boletins">BOLETINS</a><a class="tab" href="/pericias">PERÍCIAS</a><a class="tab" href="/procurados">PROCURADOS</a><a class="tab" href="/fotos">FOTOS</a></div><section class="hero"><div class="eyebrow">CENTRAL DICOR • BANCO OPERACIONAL</div><h1>BOLETINS</h1><p>Consulta organizada dos atendimentos sincronizados do Discord.</p><form class="search-box" method="get" action="/boletins"><input name="q" value="{esc(req.query.get("q", ""))}" placeholder="Pesquisar por número ou título"><button type="submit">PESQUISAR</button></form></section><section class="wanted"><div class="wanted-head"><b>ATENDIMENTOS DE BOLETINS</b><span>{len(rows)} REGISTRO(S)</span></div><div class="records">{cards or '<div class="empty">Nenhum boletim ativo encontrado.</div>'}</div></section></main></div>'''
    css = base.APP_CSS + '''.central-tabs{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.tab{padding:10px 14px;border:1px solid #20384e;border-radius:10px;color:#7890a6;font-size:9px;font-weight:900;letter-spacing:1.1px}.tab.active{background:#102b43;color:#e5b84e;border-color:#315979}.search-box{display:flex;gap:8px;margin-top:18px}.search-box input{flex:1;min-width:0;height:44px;border:1px solid #25425d;background:#07111c;color:#eef4f8;border-radius:10px;padding:0 13px;outline:none}.search-box button{height:44px;border:0;border-radius:10px;padding:0 18px;background:#c99b32;color:#080b0e;font-weight:900;cursor:pointer}.records{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;padding:11px}.record{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:15px;border:1px solid #1e354a;border-radius:12px;background:linear-gradient(150deg,#0b1722,#071019);min-width:0}.record:hover{border-color:#3b6688}.record-main{min-width:0}.record-top{display:flex;align-items:center;gap:7px}.record-number{font-size:8px;color:#6aa7df;font-weight:900}.status{padding:4px 6px;border-radius:4px;font-size:7px;font-weight:900}.status.active{background:#123b54;color:#8fc9ee}.status.done{background:#233021;color:#b6cf9d}.record h3{font-size:11px;margin:8px 0 5px;color:#e6edf3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.record-meta{display:flex;gap:10px;color:#667d91;font-size:8px}.record-arrow{font-size:18px;color:#d8b65c}.empty{grid-column:1/-1;padding:35px;text-align:center;color:#617588;font-size:9px}@media(max-width:800px){.records{grid-template-columns:1fr}}@media(max-width:520px){.main{padding:13px}.record{padding:13px}.record h3{font-size:10px}}
'''
    return base.web.Response(text=base.page("DICOR • Boletins", body, css), content_type="text/html")


async def listing_pericias(req: Any):
    session = base.read_session(req)
    if not session:
        raise base.web.HTTPFound("/cadastro-operador?next=/pericias")
    qra, passport = session
    rows = list(base.CACHE.get("pericia", []))
    cards = "".join(list_card(r, r.get("url", "#")) for r in rows)
    body = f'''<div class="app"><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE PERÍCIAS</span></div><div class="operator"><i class="online"></i> {esc(qra)} • {esc(passport)}</div></header><div class="central-tabs"><a class="tab" href="/boletins">BOLETINS</a><a class="tab active" href="/pericias">PERÍCIAS</a><a class="tab" href="/procurados">PROCURADOS</a><a class="tab" href="/fotos">FOTOS</a></div><section class="hero"><div class="eyebrow">CENTRAL DICOR • LABORATÓRIO</div><h1>PERÍCIAS</h1><p>Acompanhamento das perícias sincronizadas do Discord.</p></section><section class="wanted"><div class="wanted-head"><b>ATENDIMENTOS DE PERÍCIAS</b><span>{len(rows)} REGISTRO(S)</span></div><div class="records">{cards or '<div class="empty">Nenhuma perícia ativa encontrada.</div>'}</div></section></main></div>'''
    return base.web.Response(text=base.page("DICOR • Perícias", body, base.APP_CSS), content_type="text/html")


# Usa exatamente a mesma instância/servidor base para não interferir no bot.
async def start_server_v626(client: Any):
    global _CLIENT
    _CLIENT = client
    previous._CLIENT = client
    original_app = base.web.Application
    base.web.Application = ApplicationPatch
    try:
        return await _ORIGINAL_START(client)
    finally:
        base.web.Application = original_app


class ApplicationPatch(base.web.Application):
    def __init__(self, *args: Any, **kwargs: Any):
        kwargs["client_max_size"] = 12 * 1024 * 1024
        super().__init__(*args, **kwargs)
        self.router.add_get("/boletins", listing_boletins, name="v626_boletins")
        self.router.add_get("/pericias", listing_pericias, name="v626_pericias")
        self.router.add_get("/boletim/{thread_id}", boletim_detail, name="v626_boletim_detail")
        # Mantém as rotas da V625 (Procurados/Fotos) via servidor anterior.
        self.router.add_get("/procurado/{source_id}", previous.v624.v622.detail_route, name="v626_procurado_detail")
        self.router.add_get("/imagem-procurado/{message_id}", previous.v624.v622.procurado_photo, name="v626_wanted_photo")
        self.router.add_get("/fotos", previous.v624.v622.photos_page, name="v626_photos")
        self.router.add_get("/foto/{message_id}", previous.v624.v622.stable_photo, name="v626_stable_photo")
        self.router.add_post("/fotos/upload", previous.upload_to_fivemanage if hasattr(previous, "upload_to_fivemanage") else previous.v624.v622.upload_photo, name="v626_upload")


base.start_server = start_server_v626
base.collect_procurados = collect_procurados


def install(bot_module: Any):
    return base.install(bot_module)
