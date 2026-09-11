# -*- coding: utf-8 -*-
"""Central DICOR V621.

Camada de correção sobre V620:
- leitura robusta dos campos reais dos embeds;
- nome/crimes/localização sem markdown;
- fotos dos Procurados servidas pela própria Central;
- registro individual sem qualquer link para Discord;
- aba FOTOS com upload para um canal de armazenamento e link estável da Central.
"""
from __future__ import annotations

import html
import io
import os
import re
from datetime import datetime, timezone
from typing import Any

import central_procurados_v620 as v620
import central_discord_v613 as base

SCAN_LIMIT = 1000
PHOTO_CHANNEL_ID = int(os.getenv("CENTRAL_FOTOS_CHANNEL_ID", "0") or 0)
PHOTO_CHANNEL_NAMES = {"central-fotos", "fotos-central", "fotos"}
_CLIENT: Any = None


def clean(v: Any) -> str:
    s = str(v or "")
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[*_~`]+", "", s)
    s = s.replace("\\n", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip(" |•-—:;\t\r\n")


def esc(v: Any) -> str:
    return html.escape(clean(v), quote=True)


def norm(v: Any) -> str:
    s = clean(v).casefold()
    s = re.sub(r"[^a-zà-ÿ0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fields_of(m: Any) -> list[tuple[str, str]]:
    out = []
    for e in getattr(m, "embeds", []) or []:
        for f in getattr(e, "fields", []) or []:
            n, val = clean(getattr(f, "name", "")), clean(getattr(f, "value", ""))
            if n or val:
                out.append((n, val))
    return out


def field(fields: list[tuple[str, str]], labels: tuple[str, ...]) -> str:
    wanted = [norm(x) for x in labels]
    for name, value in fields:
        n = norm(name)
        if any(n == w or w in n for w in wanted):
            return clean(value)
    return ""


def message_text(m: Any, fields: list[tuple[str, str]] | None = None) -> str:
    fields = fields if fields is not None else fields_of(m)
    parts = [clean(getattr(m, "content", "") or "")]
    for e in getattr(m, "embeds", []) or []:
        parts += [clean(getattr(e, "title", "") or ""), clean(getattr(e, "description", "") or "")]
    parts += [f"{n}: {v}" for n, v in fields]
    return clean(" | ".join(x for x in parts if x))


def text_field(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        m = re.search(rf"(?:{re.escape(label)})\s*[:=-]\s*([^|\n]+)", text, re.I)
        if m:
            return clean(m.group(1))[:300]
    return ""


def normalize_name(value: Any) -> str:
    s = clean(value)
    s = re.sub(r"^(?:nome(?:\s+completo)?|nome\s+do\s+(?:procurado|indiv[ií]duo)|indiv[ií]duo|procurado)\s*[:#=-]?\s*", "", s, flags=re.I)
    s = re.sub(r"^(?:n[ºo°]|registro)\s*[:#=-]?\s*\d+\s*[-|•:]\s*", "", s, flags=re.I)
    s = re.split(r"\s*[|•]\s*", s, maxsplit=1)[0]
    s = re.sub(r"\s+", " ", s).strip(" -:;")
    if re.match(r"^(?:rg|passaporte|crime|crimes|status|situa[cç][aã]o|pena|senten[cç]a)\b", s, re.I):
        return "Indivíduo não identificado"
    return s[:90] or "Indivíduo não identificado"


def extract_name(m: Any, fields: list[tuple[str, str]], text: str) -> str:
    value = field(fields, ("nome completo", "nome do procurado", "nome do indivíduo", "nome", "indivíduo", "individuo"))
    if value:
        return normalize_name(value)
    value = text_field(text, ("nome completo", "nome do procurado", "nome do indivíduo", "nome"))
    if value:
        return normalize_name(value)
    for e in getattr(m, "embeds", []) or []:
        author = getattr(e, "author", None)
        av = clean(getattr(author, "name", "") if author else "")
        if av and norm(av) not in {"procurado", "registro", "dicor", "central dicor"}:
            return normalize_name(av)
        title = clean(getattr(e, "title", "") or "")
        if title:
            title = re.sub(r"^(?:procurado|registro|mandado)\s*(?:n[ºo°#:-]?\s*\d+)?\s*[-:|•]?\s*", "", title, flags=re.I)
            if title and norm(title) not in {"procurados", "registro de procurado"}:
                return normalize_name(title)
    first = re.split(r"\s*[|•\n]\s*", text, maxsplit=1)[0]
    return normalize_name(first)


def extract_rg(fields: list[tuple[str, str]], text: str) -> str:
    value = field(fields, ("rg", "registro geral", "passaporte", "identidade", "id"))
    return (value or text_field(text, ("rg", "registro geral", "passaporte", "identidade")) or "Não informado")[:80]


def extract_crimes(fields: list[tuple[str, str]], text: str) -> str:
    value = field(fields, ("crimes cometidos", "crimes", "crime", "acusações", "acusação", "acusacao", "infrações", "infracoes", "artigos", "envolvimento"))
    if not value:
        value = text_field(text, ("crimes cometidos", "crimes", "crime", "acusações", "acusação", "acusacao", "infrações", "infracoes", "artigos"))
    return value[:500] if value else "Não informado"


def extract_last_seen(fields: list[tuple[str, str]], text: str) -> str:
    value = field(fields, ("último avistamento", "ultimo avistamento", "última localização", "ultima localização", "localização", "localizacao", "avistamento", "última vez visto"))
    if not value:
        value = text_field(text, ("último avistamento", "ultimo avistamento", "última localização", "ultima localização", "localização", "localizacao", "avistamento", "última vez visto"))
    return value[:250] if value else "Não informado"


def image_source(m: Any) -> str:
    for e in getattr(m, "embeds", []) or []:
        for attr in ("image", "thumbnail"):
            obj = getattr(e, attr, None)
            url = clean(getattr(obj, "url", "") if obj else "")
            if url:
                return url
    for a in getattr(m, "attachments", []) or []:
        url = clean(getattr(a, "url", ""))
        if url:
            return url
    return ""


def is_closed(text: str) -> bool:
    return bool(re.search(r"\b(capturad[oa]s?|pres[oa]s?|encerrad[oa]s?|cancelad[oa]s?|finalizad[oa]s?)\b", clean(text).casefold()))


def penalty(text: str) -> int:
    t = clean(text).casefold()
    m = re.search(r"(?:pena|senten[cç]a).{0,50}?(\d+)\s*anos?(?:\s*e\s*(\d+)\s*mes(?:es)?)?", t)
    if m:
        return int(m.group(1)) * 12 + int(m.group(2) or 0)
    m = re.search(r"(?:pena|senten[cç]a).{0,50}?(\d+)\s*mes(?:es)?", t)
    return int(m.group(1)) if m else 0


async def collect_procurados(client: Any) -> list[dict[str, Any]]:
    channel = await base.get_channel(client, base.PROCURADOS_ID)
    if channel is None:
        return []
    rows = []
    try:
        async for m in channel.history(limit=SCAN_LIMIT, oldest_first=False):
            fields = fields_of(m)
            text = message_text(m, fields)
            if not text or is_closed(text):
                continue
            mid = getattr(m, "id", 0)
            src = image_source(m)
            rows.append({
                "number": base.number_from(text),
                "name": extract_name(m, fields, text),
                "rg": extract_rg(fields, text),
                "crime": extract_crimes(fields, text),
                "last_seen": extract_last_seen(fields, text),
                "status": field(fields, ("status", "situação", "situacao")) or "ATIVO",
                "created": getattr(m, "created_at", None) or datetime.now(timezone.utc),
                "url": getattr(m, "jump_url", "#"),
                "image": f"/imagem-procurado/{mid}" if src and mid else "",
                "image_source": src,
                "preview": text[:2500],
                "source_id": mid,
                "penalty_months": penalty(text),
            })
    except Exception as exc:
        print(f"⚠️ V621 Procurados: {type(exc).__name__}: {exc}", flush=True)
        return []
    unique = {r.get("source_id") or r.get("url") or id(r): r for r in rows}
    return sorted(unique.values(), key=lambda r: r.get("created") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


# Substitui o coletor da cadeia antiga para que nenhum módulo intermediário volte ao parser antigo.
base.collect_procurados = collect_procurados
v620.collect_procurados = collect_procurados
v620.v616.collect_procurados = collect_procurados


def wanted_card(row: dict[str, Any]) -> str:
    rid = esc(row.get("source_id"))
    image = f'<img src="{esc(row.get("image"))}" alt="Foto do procurado" loading="lazy">' if row.get("image") else '<div class="placeholder">SEM FOTO</div>'
    return f'''<article class="card wanted-card" onclick="location.href='/procurado/{rid}'"><div class="photo">{image}</div><div class="card-body"><span class="tag">PROCURADO</span><h3>{esc(row.get("name"))}</h3><div class="rg">RG/PASSAPORTE: {esc(row.get("rg"))}</div><div class="meta">Crimes: {esc(row.get("crime"))}</div></div></article>'''


def wanted_detail(row: dict[str, Any], qra: str, passport: str) -> str:
    image = f'<img src="{esc(row.get("image"))}" alt="Foto do procurado" onclick="openPhoto()">' if row.get("image") else '<div class="placeholder">SEM FOTO</div>'
    body = f'''<div class="app"><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i> {esc(qra)} • {esc(passport)}</div></header><div class="detail-wrap"><a class="detail-back" href="/">← VOLTAR À CENTRAL</a><div class="detail-card"><div class="detail-photo">{image}</div><div><span class="tag">PROCURADO • ATIVO</span><h1 class="detail-title">{esc(row.get("name"))}</h1><div class="detail-rg">RG/PASSAPORTE: {esc(row.get("rg"))}</div><div class="detail-field"><b>ÚLTIMO AVISTAMENTO</b><span>{esc(row.get("last_seen"))}</span></div><div class="detail-field"><b>CRIMES</b><span>{esc(row.get("crime"))}</span></div><div class="detail-field"><b>PENA REGISTRADA</b><span>{esc(row.get("penalty_months"))} mês(es)</span></div></div></div><div id="photoModal" class="photo-modal" onclick="closePhoto()"><img src="{esc(row.get("image"))}" alt="Foto em tela cheia"></div></div></main></div><script>function openPhoto(){{document.getElementById('photoModal').style.display='flex'}}function closePhoto(){{document.getElementById('photoModal').style.display='none'}}</script>'''
    return base.page("DICOR • Registro do Procurado", body, base.APP_CSS)


def dashboard(rows: list[dict[str, Any]], qra: str, passport: str, query: str = "") -> str:
    rows = [dict(r) for r in (rows or [])]
    if query.startswith("__REGISTRO__:"):
        rid = query.split(":", 1)[1]
        row = next((r for r in rows if str(r.get("source_id")) == rid), None)
        if row:
            return wanted_detail(row, qra, passport)
    q = clean(query).casefold()
    if q:
        result = [r for r in rows if q in clean(r.get("name")).casefold() or q in clean(r.get("rg")).casefold()]
        heading = "RESULTADOS DA PESQUISA"
        note = f"{len(result)} resultado(s)"
    else:
        result = sorted(rows, key=lambda r:(r.get("penalty_months", 0), r.get("created") or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)[:2]
        heading = "MAIORES PENAS"
        note = f"Exibindo 2 de {len(rows)} procurado(s) ativo(s)"
    cards = "".join(wanted_card(r) for r in result) or '<div class="empty">Nenhum procurado encontrado.</div>'
    updated = datetime.now().strftime("%d/%m/%Y • %H:%M")
    nav = '<div class="central-tabs"><a class="tab active" href="/procurados">PROCURADOS</a><a class="tab" href="/fotos">FOTOS</a></div>'
    body = f'''<div class="app"><aside class="side"><div class="brand">{base.img(base.DICOR_LOGO, "", "DICOR")}<div><b>DICOR</b><small>INTELIGÊNCIA</small></div></div><div class="side-note">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<br><br>CONSULTA INTERNA<br>SISTEMA SOMENTE LEITURA</div></aside><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i> {esc(qra)} • {esc(passport)}</div></header>{nav}<section class="hero"><div class="eyebrow">CENTRAL DICOR • MONITORAMENTO</div><h1>PROCURADOS</h1><p>Consulta interna da base de procurados.</p></section><section class="search-box"><form style="display:flex;gap:9px;width:100%" method="get" action="/procurados"><input name="q" value="{esc(query)}" placeholder="Pesquisar por nome ou RG / passaporte..."><button type="submit">PESQUISAR</button></form></section><div class="result-note">{esc(note)} • atualização {esc(updated)}</div><section class="wanted"><div class="wanted-head"><b>{esc(heading)}</b><span>{len(rows)} REGISTRO(S) ATIVO(S)</span></div><div class="grid">{cards}</div></section>{('<a class="access" href="/procurados"><div><strong>VER TODOS OS PROCURADOS</strong><span>ABRIR A BASE COMPLETA</span></div><div class="access-btn">VER TODOS&nbsp; →</div></a>' if not q else '')}<a class="access" href="/funcionalidades"><div><strong>ACESSAR TODAS AS FUNCIONALIDADES</strong><span>BOLETINS • PERÍCIAS • BANCO DE DADOS • ÁRVORE • OPERAÇÕES</span></div><div class="access-btn">ACESSAR&nbsp; →</div></a></main></div>'''
    return base.page("DICOR • Procurados", body, base.APP_CSS + PHOTO_CSS)


PHOTO_CSS = """
.central-tabs{display:flex;gap:8px;margin:16px 0 4px}.central-tabs .tab{padding:10px 16px;border:1px solid #294965;border-radius:10px;color:#9db4c9;text-decoration:none;font-size:10px;font-weight:900;letter-spacing:.08em;background:#08121d}.central-tabs .tab.active,.central-tabs .tab:hover{color:#f4f7fa;border-color:#c9a84d;background:#142333}
.photo-manager{max-width:1120px;margin:28px auto;padding:0 18px}.photo-hero{padding:28px;border:1px solid #294965;border-radius:20px;background:linear-gradient(145deg,#0b1724,#07101a);box-shadow:0 18px 50px rgba(0,0,0,.28)}.photo-hero h1{margin:6px 0;font-size:30px}.photo-hero p{color:#8298aa;font-size:12px}.upload-zone{margin-top:20px;padding:26px;border:1px dashed #456782;border-radius:16px;background:#091522;text-align:center}.upload-zone input{display:block;width:100%;margin:12px 0;color:#b7c7d5}.upload-btn{display:inline-block;border:0;border-radius:10px;padding:13px 20px;background:linear-gradient(135deg,#e6c864,#a87517);font-weight:900;cursor:pointer}.photo-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px;margin-top:18px}.photo-item{border:1px solid #243f59;border-radius:15px;overflow:hidden;background:#08121d}.photo-item img{width:100%;height:190px;object-fit:cover;display:block}.photo-item .pi{padding:12px}.photo-item small{display:block;color:#8197a9;font-size:9px;margin-bottom:9px}.copy-link{width:100%;padding:9px;border:1px solid #355674;border-radius:8px;background:#0d1b29;color:#dbe7f0;font-size:10px;font-weight:800;cursor:pointer}.stable-link{word-break:break-all;color:#c9a84d;font-size:9px;margin:8px 0}.photo-msg{margin:14px 0;padding:12px;border-radius:10px;background:#102638;border:1px solid #315a78;color:#dbe8f2;font-size:11px}
.detail-wrap{max-width:1050px;margin:30px auto;padding:0 18px}.detail-card{display:grid;grid-template-columns:minmax(280px,42%) 1fr;gap:26px;padding:22px;border:1px solid #284967;border-radius:18px;background:linear-gradient(145deg,#0a1521,#07101a);box-shadow:0 15px 45px rgba(0,0,0,.25)}.detail-photo{min-height:360px;border-radius:14px;overflow:hidden;background:#050a0f;display:flex;align-items:center;justify-content:center}.detail-photo img{width:100%;max-height:620px;object-fit:contain;cursor:zoom-in}.detail-title{font-size:31px;line-height:1.08;margin:8px 0 7px;color:#f4f7fa}.detail-rg{color:#a7bfd2;font-size:12px;margin-bottom:25px}.detail-field{padding:14px 0;border-top:1px solid #20384d}.detail-field b{display:block;color:#c9a84d;font-size:9px;letter-spacing:.12em;margin-bottom:7px}.detail-field span{color:#e5edf4;font-size:13px;line-height:1.5}.photo-modal{position:fixed;inset:0;background:rgba(0,0,0,.94);display:none;align-items:center;justify-content:center;z-index:9999;padding:20px;cursor:zoom-out}.photo-modal img{max-width:96vw;max-height:94vh;object-fit:contain}
"""


def _auth(req: Any) -> tuple[str, str] | None:
    return base.read_session(req)


async def find_photo_channel(client: Any):
    if PHOTO_CHANNEL_ID:
        c = await base.get_channel(client, PHOTO_CHANNEL_ID)
        if c:
            return c
    for g in getattr(client, "guilds", []) or []:
        for c in getattr(g, "text_channels", []) or []:
            if clean(getattr(c, "name", "")).casefold() in PHOTO_CHANNEL_NAMES:
                return c
    return None


async def photo_page(req: Any):
    session = _auth(req)
    if not session:
        raise base.web.HTTPFound("/cadastro-operador?next=/fotos")
    channel = await find_photo_channel(_CLIENT)
    items = []
    if channel:
        try:
            async for m in channel.history(limit=60, oldest_first=False):
                for a in getattr(m, "attachments", []) or []:
                    if not re.search(r"\.(?:png|jpe?g|webp|gif)(?:$|\?)", clean(getattr(a, "url", "")), re.I):
                        continue
                    link = f"/foto/{m.id}"
                    items.append((link, clean(getattr(a, "filename", "Foto")), getattr(m, "created_at", datetime.now(timezone.utc))))
        except Exception as exc:
            print(f"⚠️ V621 Fotos: {type(exc).__name__}: {exc}", flush=True)
    qra, passport = session
    cards = "".join(f'<article class="photo-item"><img src="{esc(link)}" alt="{esc(name)}" loading="lazy"><div class="pi"><small>{esc(name)} • {dt.astimezone().strftime("%d/%m/%Y %H:%M")}</small><div class="stable-link">{esc(link)}</div><button class="copy-link" onclick="copyLink(\'{esc(link)}\')">COPIAR LINK ESTÁVEL</button></div></article>' for link, name, dt in items) or '<div class="empty">Nenhuma foto armazenada ainda.</div>'
    body = f'''<div class="app"><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i> {esc(qra)} • {esc(passport)}</div></header><div class="central-tabs"><a class="tab" href="/procurados">PROCURADOS</a><a class="tab active" href="/fotos">FOTOS</a></div><div class="photo-manager"><div class="photo-hero"><div class="eyebrow">CENTRAL DICOR • ARQUIVO VISUAL</div><h1>BANCO DE FOTOS</h1><p>Envie uma imagem para o armazenamento da Central e receba um link próprio. O link da Central não depende do endereço da mensagem do Discord.</p><form class="upload-zone" method="post" action="/fotos/upload" enctype="multipart/form-data"><b>ADICIONAR NOVA FOTO</b><input type="file" name="foto" accept="image/png,image/jpeg,image/webp,image/gif" required><button class="upload-btn" type="submit">ENVIAR E GERAR LINK</button></form></div><section class="wanted"><div class="wanted-head"><b>FOTOS ARMAZENADAS</b><span>{len(items)} ARQUIVO(S)</span></div><div class="photo-list">{cards}</div></section></div></main></div><script>function copyLink(path){{navigator.clipboard.writeText(location.origin+path).then(()=>alert('Link copiado.'))}}</script>'''
    return base.page("DICOR • Fotos", body, base.APP_CSS + PHOTO_CSS)


async def upload_photo(req: Any):
    session = _auth(req)
    if not session:
        raise base.web.HTTPFound("/cadastro-operador?next=/fotos")
    reader = await req.multipart()
    part = await reader.next()
    if part is None or part.name != "foto":
        raise base.web.HTTPBadRequest(text="Arquivo de imagem não enviado.")
    filename = os.path.basename(part.filename or "foto.png")
    if not re.search(r"\.(?:png|jpe?g|webp|gif)$", filename, re.I):
        raise base.web.HTTPBadRequest(text="Formato não permitido. Use PNG, JPG, WEBP ou GIF.")
    data = await part.read(decode=False)
    if not data or len(data) > 10 * 1024 * 1024:
        raise base.web.HTTPBadRequest(text="A imagem deve ter até 10 MB.")
    channel = await find_photo_channel(_CLIENT)
    if channel is None:
        raise base.web.HTTPServiceUnavailable(text="Canal de armazenamento de fotos não encontrado. Crie um canal chamado #central-fotos ou defina CENTRAL_FOTOS_CHANNEL_ID.")
    try:
        import discord
        file = discord.File(io.BytesIO(data), filename=filename)
        msg = await channel.send(content=f"CENTRAL DICOR • FOTO • {filename}", file=file)
        stable = f"/foto/{msg.id}"
        qra, passport = session
        body = f'''<main class="auth"><div class="eyebrow">CENTRAL DICOR • ARQUIVO VISUAL</div><h1>FOTO ARMAZENADA</h1><p class="sub">O arquivo foi guardado e a Central gerou um link próprio.</p><div class="photo-msg"><b>LINK ESTÁVEL</b><div class="stable-link">{esc(stable)}</div><button class="upload-btn" onclick="navigator.clipboard.writeText(location.origin+'{stable}');return false;">COPIAR LINK</button></div><a class="primary gold" style="display:block;text-decoration:none;padding-top:16px" href="/fotos">VOLTAR AO BANCO DE FOTOS</a></main>'''
        return base.web.Response(text=base.page("DICOR • Foto armazenada", body, base.AUTH_CSS + PHOTO_CSS), content_type="text/html")
    except Exception as exc:
        print(f"⚠️ V621 upload: {type(exc).__name__}: {exc}", flush=True)
        raise base.web.HTTPInternalServerError(text="Não foi possível armazenar a foto.")


async def stable_photo(req: Any):
    session = _auth(req)
    if not session:
        raise base.web.HTTPFound("/cadastro-operador?next=" + base.quote(req.path))
    mid = int(req.match_info.get("message_id", "0"))
    channel = await find_photo_channel(_CLIENT)
    if channel is None:
        raise base.web.HTTPNotFound()
    try:
        m = await channel.fetch_message(mid)
        attachment = next(iter(getattr(m, "attachments", []) or []), None)
        if attachment is None:
            raise base.web.HTTPNotFound()
        data = await attachment.read()
        ctype = getattr(attachment, "content_type", None) or "application/octet-stream"
        return base.web.Response(body=data, content_type=ctype, headers={"Cache-Control":"public, max-age=31536000, immutable"})
    except base.web.HTTPException:
        raise
    except Exception as exc:
        print(f"⚠️ V621 stable photo: {type(exc).__name__}: {exc}", flush=True)
        raise base.web.HTTPNotFound()


async def procurado_photo(req: Any):
    session = _auth(req)
    if not session:
        raise base.web.HTTPFound("/cadastro-operador?next=" + base.quote(req.path))
    mid = int(req.match_info.get("message_id", "0"))
    channel = await base.get_channel(_CLIENT, base.PROCURADOS_ID)
    if channel is None:
        raise base.web.HTTPNotFound()
    try:
        m = await channel.fetch_message(mid)
        src = image_source(m)
        if not src:
            raise base.web.HTTPNotFound()
        attachment = next(iter(getattr(m, "attachments", []) or []), None)
        if attachment is not None:
            data = await attachment.read()
            ctype = getattr(attachment, "content_type", None) or "image/jpeg"
            return base.web.Response(body=data, content_type=ctype, headers={"Cache-Control":"public, max-age=3600"})
        import aiohttp
        async with aiohttp.ClientSession() as session_http:
            async with session_http.get(src, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    raise base.web.HTTPNotFound()
                data = await resp.read()
                return base.web.Response(body=data, content_type=resp.headers.get("Content-Type", "image/jpeg"), headers={"Cache-Control":"public, max-age=3600"})
    except base.web.HTTPException:
        raise
    except Exception:
        raise base.web.HTTPNotFound()


class ApplicationPatch(base.web.Application):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        original_get, original_post = self.router.add_get, self.router.add_post
        original_get("/procurado/{source_id}", lambda req: wanted_detail_route(req), name="procurado_detail_v621")
        original_get("/imagem-procurado/{message_id}", procurado_photo, name="procurado_photo_v621")
        original_get("/fotos", photo_page, name="fotos_v621")
        original_get("/foto/{message_id}", stable_photo, name="foto_stable_v621")
        original_post("/fotos/upload", upload_photo, name="fotos_upload_v621")


async def wanted_detail_route(req: Any):
    session = _auth(req)
    if not session:
        raise base.web.HTTPFound("/cadastro-operador?next=" + base.quote(req.path))
    qra, passport = session
    rid = str(req.match_info.get("source_id", ""))
    rows = [dict(r) for r in base.CACHE.get("procurados", [])]
    row = next((r for r in rows if str(r.get("source_id")) == rid), None)
    if row is None:
        fresh = await collect_procurados(_CLIENT)
        row = next((r for r in fresh if str(r.get("source_id")) == rid), None)
    if row is None:
        raise base.web.HTTPNotFound(text="Registro não encontrado.")
    return base.web.Response(text=wanted_detail(row, qra, passport), content_type="text/html")


async def start_server_v621(client: Any):
    global _CLIENT
    _CLIENT = client
    original_app = base.web.Application
    base.web.Application = ApplicationPatch
    try:
        return await v620.v616.start_server_v616(client)
    finally:
        base.web.Application = original_app


base.dashboard = dashboard
v620.dashboard = dashboard
v620.v616.dashboard = dashboard
base.start_server = start_server_v621


def install(bot_module: Any):
    return base.install(bot_module)
