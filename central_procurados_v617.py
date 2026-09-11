# -*- coding: utf-8 -*-
"""Central DICOR V617 - refinamento da Central de Procurados.

Mantém a V616 e altera somente a experiência de Procurados:
- tela principal mostra somente os 2 procurados com maior pena;
- botão para abrir a base completa;
- busca por nome ou RG/passaporte continua disponível;
- "VER REGISTRO" abre uma página interna do procurado, nunca o Discord;
- página individual exibe nome, RG, último avistamento, crimes e foto;
- foto abre em tela cheia ao clicar;
- limpeza de markdown/asteriscos e rótulos repetidos no nome e campos;
- ordenação por pena quando a pena está registrada.
"""
from __future__ import annotations

import re
import html
from datetime import datetime, timezone
from typing import Any

import central_procurados_v616 as v616
import central_discord_v613 as base


def clean_markup(value: Any) -> str:
    s = str(value or "")
    s = re.sub(r"[*_~`]+", "", s)
    s = re.sub(r"\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\s+", " ", s).strip(" |•-—:;\t\r\n")
    return s


def esc(value: Any) -> str:
    return html.escape(clean_markup(value), quote=True)


def extract_label_clean(text: str, labels: tuple[str, ...], default: str = "Não informado") -> str:
    label = "|".join(re.escape(x) for x in labels)
    m = re.search(rf"(?:{label})\s*[:=-]\s*([^|•\n]+)", text, re.I)
    return clean_markup(m.group(1))[:180] if m else default


def normalize_name(raw: str) -> str:
    s = clean_markup(raw)
    s = re.sub(r"^(?:nome\s*(?:completo)?|indiv[ií]duo|procurado)\s*[:=-]\s*", "", s, flags=re.I)
    s = re.sub(r"^(?:n[ºo]|registro)\s*[:#-]?\s*\d+\s*[-|•:]\s*", "", s, flags=re.I)
    s = re.sub(r"\s{2,}", " ", s).strip()
    if "|" in s:
        s = s.split("|", 1)[0].strip()
    return s[:90] or "Indivíduo não identificado"


def extract_name_clean(text: str) -> str:
    value = extract_label_clean(text, ("nome completo", "nome", "indivíduo", "individuo"), "")
    if value:
        return normalize_name(value)
    # Formatos comuns de registro: NOME | RG | CRIME ...
    first = re.split(r"[|•\n]", text, maxsplit=1)[0]
    first = normalize_name(first)
    if first and not re.match(r"^(?:procurado|registro|rg|passaporte|crime|status)\b", first, re.I):
        return first
    return "Indivíduo não identificado"


def extract_rg_clean(text: str) -> str:
    value = extract_label_clean(text, ("rg", "registro geral", "passaporte", "identidade"), "")
    if value:
        return value
    m = re.search(r"\b(?:RG|PASSAPORTE|ID)\s*#?\s*[:=-]?\s*([A-Z0-9.-]{3,24})\b", text, re.I)
    return clean_markup(m.group(1)) if m else "Não informado"


def extract_last_seen(text: str) -> str:
    return extract_label_clean(
        text,
        ("último avistamento", "ultimo avistamento", "última localização", "ultima localização", "última localizacao", "ultima localizacao", "avistamento", "localização", "localizacao"),
        "Não informado",
    )


def extract_crimes(text: str) -> str:
    value = extract_label_clean(text, ("crimes", "crime", "acusação", "acusacao"), "Não informado")
    return clean_markup(value)


def parse_penalty(text: str) -> int:
    """Converte a pena para meses para permitir uma ordenação consistente."""
    t = clean_markup(text).casefold()
    patterns = [
        (r"pena\s*(?:total|aplicada)?\s*[:=-]?\s*(\d+)\s*anos?\s*(?:e\s*(\d+)\s*mes", 12),
        (r"pena\s*(?:total|aplicada)?\s*[:=-]?\s*(\d+)\s*anos?", 12),
        (r"pena\s*(?:total|aplicada)?\s*[:=-]?\s*(\d+)\s*mes(?:es)?", 1),
        (r"senten[cç]a\s*[:=-]?\s*(\d+)\s*anos?", 12),
        (r"(\d+)\s*anos?\s*(?:de\s*)?pena", 12),
        (r"(\d+)\s*mes(?:es)?\s*(?:de\s*)?pena", 1),
    ]
    for pattern, multiplier in patterns:
        m = re.search(pattern, t)
        if m:
            total = int(m.group(1)) * multiplier
            if len(m.groups()) > 1 and m.group(2):
                total += int(m.group(2))
            return total
    # Fallback: se houver apenas "X anos" perto de pena/sentença.
    m = re.search(r"(?:pena|senten[cç]a).{0,30}?(\d+)\s*anos?", t)
    return int(m.group(1)) * 12 if m else 0


def row_v617(row: dict[str, Any]) -> dict[str, Any]:
    text = clean_markup(row.get("preview"))
    name = extract_name_clean(text) if text else normalize_name(row.get("name"))
    rg = extract_rg_clean(text) if text else clean_markup(row.get("rg"))
    crime = extract_crimes(text) if text else clean_markup(row.get("crime"))
    last_seen = extract_last_seen(text) if text else "Não informado"
    penalty = parse_penalty(text)
    out = dict(row)
    out.update({"name": name, "rg": rg, "crime": crime, "last_seen": last_seen, "penalty_months": penalty})
    return out


async def collect_procurados(client: Any) -> list[dict[str, Any]]:
    rows = await v616.collect_procurados(client)
    return [row_v617(r) for r in rows]

base.collect_procurados = collect_procurados
v616.collect_procurados = collect_procurados


# CSS complementar: visual DICOR preservado, foto clicável e página individual.
base.APP_CSS += """
.wanted-card{cursor:pointer;transition:transform .18s ease,border-color .18s ease}
.wanted-card:hover{transform:translateY(-2px);border-color:#c9a84d}
.photo img{cursor:zoom-in}
.photo-modal{position:fixed;inset:0;background:rgba(0,0,0,.94);display:none;align-items:center;justify-content:center;z-index:9999;padding:22px;cursor:zoom-out}
.photo-modal img{max-width:96vw;max-height:94vh;width:auto;height:auto;object-fit:contain;border-radius:10px;box-shadow:0 15px 60px rgba(0,0,0,.65)}
.detail-wrap{max-width:1050px;margin:30px auto;padding:0 18px}
.detail-back{display:inline-flex;align-items:center;gap:8px;color:#9bb3c8;text-decoration:none;font-size:11px;margin-bottom:16px}
.detail-card{display:grid;grid-template-columns:minmax(280px,42%) 1fr;gap:26px;padding:22px;border:1px solid #284967;border-radius:18px;background:linear-gradient(145deg,#0a1521,#07101a);box-shadow:0 15px 45px rgba(0,0,0,.25)}
.detail-photo{min-height:360px;border-radius:14px;overflow:hidden;background:#050a0f;display:flex;align-items:center;justify-content:center}
.detail-photo img{width:100%;height:100%;max-height:620px;object-fit:contain;cursor:zoom-in}
.detail-title{font-size:31px;line-height:1.08;margin:8px 0 7px;color:#f4f7fa}
.detail-rg{color:#a7bfd2;font-size:12px;margin-bottom:25px}
.detail-field{padding:14px 0;border-top:1px solid #20384d}.detail-field b{display:block;color:#c9a84d;font-size:9px;letter-spacing:.12em;margin-bottom:7px}.detail-field span{color:#e5edf4;font-size:13px;line-height:1.5}
@media(max-width:760px){.detail-card{grid-template-columns:1fr}.detail-photo{min-height:250px}.detail-title{font-size:24px}}
"""


def card_v617(row: dict[str, Any]) -> str:
    image = f'<img src="{esc(row.get("image"))}" alt="Foto do procurado" loading="lazy">' if row.get("image") else '<div class="placeholder">◉</div>'
    return f'''<article class="card wanted-card"><div class="photo" onclick="location.href='/procurado/{esc(row.get('source_id'))}'">{image}</div><div class="card-body"><span class="tag">PROCURADO</span><h3>{esc(row.get("name"))}</h3><div class="rg">RG/PASSAPORTE: {esc(row.get("rg"))}</div><div class="meta">Crime: {esc(row.get("crime"))}</div><a class="details" href="/procurado/{esc(row.get('source_id'))}">VER REGISTRO&nbsp; →</a></div></article>'''


def dashboard_v617(rows: list[dict[str, Any]], qra: str, passport: str, query: str = "") -> str:
    rows = [row_v617(r) for r in rows]
    if query.strip():
        result = v616.searched(rows, query)
        heading = "RESULTADOS DA PESQUISA"
        note = f"{len(result)} resultado(s) encontrado(s)"
    else:
        result = sorted(rows, key=lambda r: (r.get("penalty_months", 0), r.get("created") or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)[:2]
        heading = "MAIORES PENAS"
        note = f"Exibindo 2 de {len(rows)} procurado(s) ativo(s)"
    cards = "".join(card_v617(r) for r in result) or '<div class="empty">Nenhum procurado encontrado.</div>'
    updated = datetime.now().strftime("%d/%m/%Y • %H:%M")
    body = f'''<div class="app"><aside class="side"><div class="brand">{base.img(base.DICOR_LOGO, "", "DICOR")}<div><b>DICOR</b><small>INTELIGÊNCIA</small></div></div><div class="side-note">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<br><br>CONSULTA INTERNA<br>SISTEMA SOMENTE LEITURA</div></aside><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i> {esc(qra)} • {esc(passport)}</div></header><section class="hero"><div class="eyebrow">CENTRAL DICOR • MONITORAMENTO</div><h1>PROCURADOS</h1><p>Consulta integrada diretamente ao canal de Procurados do Discord.</p></section><section class="search-box"><form style="display:flex;gap:9px;width:100%" method="get" action="/procurados"><input name="q" value="{esc(query)}" placeholder="Pesquisar por nome ou RG / passaporte..."><button type="submit">PESQUISAR</button></form></section><div class="result-note">{esc(note)} • sincronizado do Discord • {esc(updated)}</div><section class="wanted"><div class="wanted-head"><b>{esc(heading)}</b><span>{len(rows)} REGISTRO(S) ATIVO(S)</span></div><div class="grid">{cards}</div></section>{('<a class="access" href="/procurados"><div><strong>VER TODOS OS PROCURADOS</strong><span>ABRIR A BASE COMPLETA E CONTINUAR A PESQUISA</span></div><div class="access-btn">VER TODOS&nbsp; →</div></a>' if not query.strip() else '')}<a class="access" href="/funcionalidades"><div><strong>ACESSAR TODAS AS FUNCIONALIDADES</strong><span>BOLETINS • PERÍCIAS • BANCO DE DADOS • ÁRVORE • OPERAÇÕES</span></div><div class="access-btn">ACESSAR&nbsp; →</div></a><div class="foot">DICOR • INTELIGÊNCIA E OPERAÇÕES ESPECIAIS</div></main></div>'''
    return base.page("DICOR • Procurados", body, base.APP_CSS)


base.dashboard = dashboard_v617
v616.dashboard = dashboard_v617


async def detail_handler(req: Any, client: Any):
    session = base.read_session(req)
    if not session:
        target = req.path + (("?" + req.query_string) if req.query_string else "")
        raise base.web.HTTPFound("/cadastro-operador?next=" + base.quote(target))
    source_id = str(req.match_info.get("source_id", ""))
    rows = [row_v617(r) for r in base.CACHE.get("procurados", [])]
    row = next((r for r in rows if str(r.get("source_id")) == source_id), None)
    if row is None:
        try:
            rows = await collect_procurados(client)
            row = next((r for r in rows if str(r.get("source_id")) == source_id), None)
        except Exception:
            row = None
    if row is None:
        body = '<main class="auth"><h1>REGISTRO NÃO ENCONTRADO</h1><a class="primary gold" href="/procurados">VOLTAR A PROCURADOS</a></main>'
        return base.web.Response(text=base.page("DICOR • Registro", body, base.AUTH_CSS), content_type="text/html")

    image = f'<img src="{esc(row.get("image"))}" alt="Foto do procurado" onclick="openPhoto()">' if row.get("image") else '<div class="placeholder">SEM FOTO</div>'
    body = f'''<main class="detail-wrap"><a class="detail-back" href="/">← VOLTAR À CENTRAL</a><div class="detail-card"><div class="detail-photo">{image}</div><div><span class="tag">PROCURADO • ATIVO</span><h1 class="detail-title">{esc(row.get("name"))}</h1><div class="detail-rg">RG/PASSAPORTE: {esc(row.get("rg"))}</div><div class="detail-field"><b>ÚLTIMO AVISTAMENTO</b><span>{esc(row.get("last_seen"))}</span></div><div class="detail-field"><b>CRIMES</b><span>{esc(row.get("crime"))}</span></div><div class="detail-field"><b>PENA REGISTRADA</b><span>{esc(row.get("penalty_months"))} mês(es)</span></div></div></div><div id="photoModal" class="photo-modal" onclick="closePhoto()"><img src="{esc(row.get("image"))}" alt="Foto em tela cheia"></div></main><script>function openPhoto(){{document.getElementById('photoModal').style.display='flex'}}function closePhoto(){{document.getElementById('photoModal').style.display='none'}}</script>'''
    return base.web.Response(text=base.page("DICOR • Registro do Procurado", body, base.APP_CSS), content_type="text/html")


class _ApplicationPatch(base.web.Application):
    """Intercepta a criação do app V616 para registrar a rota individual."""
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        original_add_get = self.router.add_get
        installed = {"value": False}

        def add_get(path: str, handler: Any, *a: Any, **kw: Any):
            result = original_add_get(path, handler, *a, **kw)
            if path == "/procurados" and not installed["value"]:
                installed["value"] = True
                original_add_get("/procurado/{source_id}", lambda req: detail_handler(req, _CLIENT), name="procurado_detail")
            return result

        self.router.add_get = add_get


_CLIENT: Any = None


async def start_server_v617(client: Any):
    global _CLIENT
    _CLIENT = client
    original_app = base.web.Application
    base.web.Application = _ApplicationPatch
    try:
        return await v616.start_server_v616(client)
    finally:
        base.web.Application = original_app


async def install(client: Any):
    return await start_server_v617(client)
