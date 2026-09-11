# -*- coding: utf-8 -*-
"""Central DICOR V620 - Procurados corrigidos.

Corrige: nome/crimes vindos de campos do embed, fotos de embeds/attachments,
e registro individual interno sem redirecionamento para o Discord.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any

import central_procurados_v616 as v616
import central_discord_v613 as base

SCAN_LIMIT = 1000


def clean(v: Any) -> str:
    s = str(v or "")
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[*_~`]+", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" |•-—:;\t\r\n")


def esc(v: Any) -> str:
    return html.escape(clean(v), quote=True)


def norm_label(v: Any) -> str:
    s = clean(v).casefold()
    s = re.sub(r"[^a-zà-ÿ0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def get_fields(m: Any) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for e in getattr(m, "embeds", []) or []:
        for f in getattr(e, "fields", []) or []:
            n = clean(getattr(f, "name", ""))
            v = clean(getattr(f, "value", ""))
            if n or v:
                out.append((n, v))
    return out


def message_text(m: Any) -> str:
    parts = [clean(getattr(m, "content", "") or "")]
    for e in getattr(m, "embeds", []) or []:
        parts += [clean(getattr(e, "title", "") or ""), clean(getattr(e, "description", "") or "")]
        for n, v in get_fields(m):
            parts.append(f"{n}: {v}")
    return clean(" | ".join(x for x in parts if x))


def image_url(m: Any) -> str:
    # Prioridade: imagem principal do embed, thumbnail, autor e anexos.
    for e in getattr(m, "embeds", []) or []:
        for attr in ("image", "thumbnail"):
            obj = getattr(e, attr, None)
            url = clean(getattr(obj, "url", "") if obj else "")
            if url:
                return url
        author = getattr(e, "author", None)
        url = clean(getattr(author, "icon_url", "") if author else "")
        if url:
            return url
    for a in getattr(m, "attachments", []) or []:
        url = clean(getattr(a, "url", ""))
        if url:
            return url
    return ""


def field_value(fields: list[tuple[str, str]], labels: tuple[str, ...]) -> str:
    wanted = tuple(norm_label(x) for x in labels)
    for name, value in fields:
        n = norm_label(name)
        if any(n == x or x in n for x in wanted):
            return clean(value)
    return ""


def extract_from_text(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        m = re.search(rf"(?:{re.escape(label)})\s*[:=-]\s*([^|\n]+)", text, re.I)
        if m:
            return clean(m.group(1))[:220]
    return ""


def normalize_name(value: Any) -> str:
    s = clean(value)
    s = re.sub(r"^(?:nome\s*(?:completo)?|indiv[ií]duo|procurado)\s*[:=-]\s*", "", s, flags=re.I)
    s = re.sub(r"^(?:n[ºo]|registro)\s*[:#-]?\s*\d+\s*[-|•:]\s*", "", s, flags=re.I)
    s = re.split(r"\s+[|•]\s+", s, maxsplit=1)[0].strip()
    return s[:90] or "Indivíduo não identificado"


def extract_name(m: Any, text: str, fields: list[tuple[str, str]]) -> str:
    value = field_value(fields, ("nome completo", "nome", "indivíduo", "individuo", "nome do procurado"))
    if value:
        return normalize_name(value)
    value = extract_from_text(text, ("nome completo", "nome", "indivíduo", "individuo"))
    if value:
        return normalize_name(value)
    for e in getattr(m, "embeds", []) or []:
        title = clean(getattr(e, "title", "") or "")
        if title:
            mt = re.search(r"(?:procurado|registro)\s*(?:[:#-])\s*(.+)$", title, re.I)
            if mt:
                return normalize_name(mt.group(1))
    # Último fallback: somente a primeira linha/segmento, nunca o registro inteiro.
    first = re.split(r"\s*[|\n•]\s*", text, maxsplit=1)[0]
    if first and not re.match(r"^(nome|rg|passaporte|crime|crimes|status|situa[cç]a)o?\b", first, re.I):
        return normalize_name(first)
    return "Indivíduo não identificado"


def extract_rg(text: str, fields: list[tuple[str, str]]) -> str:
    value = field_value(fields, ("rg", "registro geral", "passaporte", "identidade", "id"))
    if value:
        return value[:80]
    value = extract_from_text(text, ("rg", "registro geral", "passaporte", "identidade"))
    if value:
        return value[:80]
    m = re.search(r"\b(?:RG|PASSAPORTE|ID)\s*#?\s*[:=-]?\s*([A-Z0-9.-]{3,24})\b", text, re.I)
    return clean(m.group(1)) if m else "Não informado"


def extract_crime(text: str, fields: list[tuple[str, str]]) -> str:
    value = field_value(fields, ("crimes", "crime", "crimes cometidos", "acusação", "acusacao", "infrações", "infracoes"))
    if value:
        return value[:300]
    value = extract_from_text(text, ("crimes cometidos", "crimes", "crime", "acusação", "acusacao"))
    return value[:300] if value else "Não informado"


def extract_last_seen(text: str, fields: list[tuple[str, str]]) -> str:
    value = field_value(fields, ("último avistamento", "ultimo avistamento", "última localização", "ultima localização", "localização", "localizacao", "avistamento"))
    if value:
        return value[:220]
    value = extract_from_text(text, ("último avistamento", "ultimo avistamento", "última localização", "ultima localização", "localização", "localizacao", "avistamento"))
    return value[:220] if value else "Não informado"


def parse_penalty(text: str) -> int:
    t = clean(text).casefold()
    m = re.search(r"(?:pena|senten[cç]a).{0,35}?(\d+)\s*anos?(?:\s*e\s*(\d+)\s*mes(?:es)?)?", t)
    if m:
        return int(m.group(1)) * 12 + int(m.group(2) or 0)
    m = re.search(r"(?:pena|senten[cç]a).{0,35}?(\d+)\s*mes(?:es)?", t)
    return int(m.group(1)) if m else 0


def is_closed(text: str) -> bool:
    s = clean(text).casefold()
    return bool(re.search(r"\b(capturad[oa]s?|pres[oa]s?|encerrad[oa]s?|cancelad[oa]s?|finalizad[oa]s?)\b", s))


async def collect_procurados(client: Any) -> list[dict[str, Any]]:
    channel = await base.get_channel(client, base.PROCURADOS_ID)
    if channel is None:
        return []
    rows: list[dict[str, Any]] = []
    try:
        async for m in channel.history(limit=SCAN_LIMIT, oldest_first=False):
            text = message_text(m)
            if not text or is_closed(text):
                continue
            fields = get_fields(m)
            created = getattr(m, "created_at", None) or datetime.now(timezone.utc)
            rows.append({
                "number": base.number_from(text),
                "name": extract_name(m, text, fields),
                "rg": extract_rg(text, fields),
                "crime": extract_crime(text, fields),
                "last_seen": extract_last_seen(text, fields),
                "status": field_value(fields, ("status", "situação", "situacao")) or "ATIVO",
                "created": created,
                "url": getattr(m, "jump_url", "#"),
                "image": image_url(m),
                "preview": text[:2000],
                "source_id": getattr(m, "id", 0),
                "penalty_months": parse_penalty(text),
            })
    except Exception as exc:
        print(f"⚠️ Central V620 Procurados: {type(exc).__name__}: {exc}", flush=True)
        return []
    unique: dict[Any, dict[str, Any]] = {}
    for row in rows:
        unique[row.get("source_id") or row.get("url") or id(row)] = row
    return sorted(unique.values(), key=lambda r: r.get("created") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


base.collect_procurados = collect_procurados
v616.collect_procurados = collect_procurados
base.start_server = v616.start_server_v616

base.APP_CSS += """
.wanted-card{cursor:pointer;transition:transform .18s ease,border-color .18s ease}
.wanted-card:hover{transform:translateY(-2px);border-color:#c9a84d}
.photo img{cursor:pointer}
.detail-wrap{max-width:1050px;margin:30px auto;padding:0 18px}
.detail-card{display:grid;grid-template-columns:minmax(280px,42%) 1fr;gap:26px;padding:22px;border:1px solid #284967;border-radius:18px;background:linear-gradient(145deg,#0a1521,#07101a);box-shadow:0 15px 45px rgba(0,0,0,.25)}
.detail-photo{min-height:360px;border-radius:14px;overflow:hidden;background:#050a0f;display:flex;align-items:center;justify-content:center}
.detail-photo img{width:100%;max-height:620px;object-fit:contain;cursor:zoom-in}
.detail-title{font-size:31px;line-height:1.08;margin:8px 0 7px;color:#f4f7fa}
.detail-rg{color:#a7bfd2;font-size:12px;margin-bottom:25px}
.detail-field{padding:14px 0;border-top:1px solid #20384d}.detail-field b{display:block;color:#c9a84d;font-size:9px;letter-spacing:.12em;margin-bottom:7px}.detail-field span{color:#e5edf4;font-size:13px;line-height:1.5}
.photo-modal{position:fixed;inset:0;background:rgba(0,0,0,.94);display:none;align-items:center;justify-content:center;z-index:9999;padding:20px;cursor:zoom-out}.photo-modal img{max-width:96vw;max-height:94vh;object-fit:contain}
@media(max-width:760px){.detail-card{grid-template-columns:1fr}.detail-photo{min-height:250px}.detail-title{font-size:24px}}
"""


def card(row: dict[str, Any]) -> str:
    rid = esc(row.get("source_id"))
    img = f'<img src="{esc(row.get("image"))}" alt="Foto do procurado" loading="lazy">' if row.get("image") else '<div class="placeholder">SEM FOTO</div>'
    return f'<article class="card wanted-card" onclick="location.href=\'/procurados?q=__REGISTRO__:{rid}\'"><div class="photo">{img}</div><div class="card-body"><span class="tag">PROCURADO</span><h3>{esc(row.get("name"))}</h3><div class="rg">RG/PASSAPORTE: {esc(row.get("rg"))}</div><div class="meta">Crimes: {esc(row.get("crime"))}</div></div></article>'


def detail_page(row: dict[str, Any], qra: str, passport: str) -> str:
    image = f'<img src="{esc(row.get("image"))}" alt="Foto do procurado" onclick="openPhoto()">' if row.get("image") else '<div class="placeholder">SEM FOTO</div>'
    body = f'''<div class="app"><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i> {esc(qra)} • {esc(passport)}</div></header><div class="detail-wrap"><a class="detail-back" href="/procurados">← VOLTAR A PROCURADOS</a><div class="detail-card"><div class="detail-photo">{image}</div><div><span class="tag">PROCURADO • ATIVO</span><h1 class="detail-title">{esc(row.get("name"))}</h1><div class="detail-rg">RG/PASSAPORTE: {esc(row.get("rg"))}</div><div class="detail-field"><b>ÚLTIMO AVISTAMENTO</b><span>{esc(row.get("last_seen"))}</span></div><div class="detail-field"><b>CRIMES</b><span>{esc(row.get("crime"))}</span></div><div class="detail-field"><b>PENA REGISTRADA</b><span>{esc(row.get("penalty_months"))} mês(es)</span></div></div></div><div id="photoModal" class="photo-modal" onclick="closePhoto()"><img src="{esc(row.get("image"))}" alt="Foto em tela cheia"></div></div></main></div><script>function openPhoto(){{document.getElementById('photoModal').style.display='flex'}}function closePhoto(){{document.getElementById('photoModal').style.display='none'}}</script>'''
    return base.page("DICOR • Registro do Procurado", body, base.APP_CSS)


def dashboard(rows: list[dict[str, Any]], qra: str, passport: str, query: str = "") -> str:
    rows = list(rows or [])
    # O registro individual usa a mesma rota /procurados, eliminando qualquer dependência de URL do Discord.
    if query.startswith("__REGISTRO__:"):
        rid = query.split(":", 1)[1].strip()
        row = next((r for r in rows if str(r.get("source_id")) == rid), None)
        if row:
            return detail_page(row, qra, passport)
    query_clean = clean(query)
    if query_clean:
        result = [r for r in rows if query_clean.casefold() in clean(r.get("name")).casefold() or query_clean.casefold() in clean(r.get("rg")).casefold()]
        heading = "RESULTADOS DA PESQUISA"
        note = f"{len(result)} resultado(s) encontrado(s)"
    else:
        result = sorted(rows, key=lambda r:(r.get("penalty_months",0), r.get("created") or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)[:2]
        heading = "MAIORES PENAS"
        note = f"Exibindo 2 de {len(rows)} procurado(s) ativo(s)"
    cards = "".join(card(r) for r in result) or '<div class="empty">Nenhum procurado encontrado.</div>'
    search_value = "" if query.startswith("__REGISTRO__:") else query_clean
    body = f'''<div class="app"><aside class="side"><div class="brand">{base.img(base.DICOR_LOGO,"","DICOR")}<div><b>DICOR</b><small>INTELIGÊNCIA</small></div></div><div class="side-note">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<br><br>CONSULTA INTERNA<br>SISTEMA SOMENTE LEITURA</div></aside><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i> {esc(qra)} • {esc(passport)}</div></header><section class="hero"><div class="eyebrow">CENTRAL DICOR • MONITORAMENTO</div><h1>PROCURADOS</h1><p>Consulta integrada ao canal de Procurados, sem expor a navegação interna ao Discord.</p></section><section class="search-box"><form style="display:flex;gap:9px;width:100%" method="get" action="/procurados"><input name="q" value="{esc(search_value)}" placeholder="Pesquisar por nome ou RG / passaporte..."><button type="submit">PESQUISAR</button></form></section><div class="result-note">{esc(note)} • sincronizado • {datetime.now().strftime("%d/%m/%Y • %H:%M")}</div><section class="wanted"><div class="wanted-head"><b>{heading}</b><span>{len(rows)} REGISTRO(S) ATIVO(S)</span></div><div class="grid">{cards}</div></section>{('<a class="access" href="/procurados"><div><strong>VER TODOS OS PROCURADOS</strong><span>ABRIR A BASE COMPLETA E CONTINUAR A PESQUISA</span></div><div class="access-btn">VER TODOS&nbsp; →</div></a>' if not query_clean else '')}<a class="access" href="/funcionalidades"><div><strong>ACESSAR TODAS AS FUNCIONALIDADES</strong><span>BOLETINS • PERÍCIAS • BANCO DE DADOS • ÁRVORE • OPERAÇÕES</span></div><div class="access-btn">ACESSAR&nbsp; →</div></a><div class="foot">DICOR • INTELIGÊNCIA E OPERAÇÕES ESPECIAIS</div></main></div>'''
    return base.page("DICOR • Procurados", body, base.APP_CSS)


base.dashboard = dashboard
v616.dashboard = dashboard


def install(bot_module: Any):
    return base.install(bot_module)
