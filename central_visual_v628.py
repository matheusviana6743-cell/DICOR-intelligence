# -*- coding: utf-8 -*-
"""Central Visual V628 — painel operacional de Boletins e Perícias.

Mantém toda a infraestrutura V627/Procurados/Fotos e altera somente a
apresentação das listas de Boletins e Perícias para um painel operacional.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote
import html
import re

import central_visual_v627 as v627
import central_discord_v613 as base

base.esc = getattr(base, "esc", lambda x: html.escape(str(x or ""), quote=True))

PANEL_CSS = r'''
/* PAINEL OPERACIONAL V628 */
.panel-wrap{margin-top:18px}
.panel-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;padding:22px 22px 18px;border:1px solid #203a52;border-radius:18px 18px 0 0;background:linear-gradient(120deg,#0b1927,#08111b 60%,#0a1621);box-shadow:0 18px 55px #0004}
.panel-kicker{font-size:8px;letter-spacing:2.4px;font-weight:900;color:#5fa4df}
.panel-head h1{margin:7px 0 5px;font-size:28px;letter-spacing:1px}
.panel-head p{margin:0;color:#70869b;font-size:10px;line-height:1.5}
.panel-counter{text-align:right;min-width:130px}.panel-counter b{display:block;font-size:31px;color:#e0bc61}.panel-counter span{color:#617991;font-size:7px;letter-spacing:1.3px;font-weight:900}
.panel-toolbar{display:flex;align-items:center;gap:9px;padding:12px;border:1px solid #1c344a;border-top:0;background:#07101a}
.panel-search{flex:1;height:42px;border:1px solid #243f57;border-radius:9px;background:#091724;color:#edf4f8;padding:0 13px;outline:none;font-size:11px}.panel-search:focus{border-color:#4c8fca;box-shadow:0 0 0 3px #2e76ad24}
.panel-filter{height:42px;border:1px solid #243f57;border-radius:9px;background:#091724;color:#9ab0c4;padding:0 12px;font-size:10px}
.panel-body{border:1px solid #1c344a;border-top:0;border-radius:0 0 18px 18px;background:#060d14;overflow:hidden}
.panel-table-head{display:grid;grid-template-columns:110px minmax(0,1.6fr) minmax(0,1fr) 160px 112px;gap:12px;padding:11px 16px;border-bottom:1px solid #152b3e;background:#091622;color:#5c7892;font-size:7px;font-weight:900;letter-spacing:1.2px}
.case-row{display:grid;grid-template-columns:110px minmax(0,1.6fr) minmax(0,1fr) 160px 112px;gap:12px;align-items:center;padding:14px 16px;border-bottom:1px solid #122538;transition:.15s;background:#07111a}.case-row:last-child{border-bottom:0}.case-row:hover{background:#0b1825}
.case-no{color:#d8b258;font-size:9px;font-weight:900;letter-spacing:.8px}.case-title{min-width:0}.case-title b{display:block;color:#e8eff4;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.case-title span{display:block;margin-top:4px;color:#5f768b;font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.case-info{color:#8ba0b4;font-size:9px;line-height:1.45}.case-info strong{display:block;color:#5d7991;font-size:6px;letter-spacing:1px;margin-bottom:2px}
.case-time{color:#8298ab;font-size:8px}.case-status{display:inline-flex;justify-content:center;align-items:center;gap:6px;min-height:29px;border:1px solid #26553e;border-radius:8px;background:#0a2119;color:#63cf9e;font-size:7px;font-weight:900;letter-spacing:.8px}.case-status .dot{width:6px;height:6px;border-radius:50%;background:#35d38b;box-shadow:0 0 10px #35d38b}
.case-open{display:block;text-align:center;padding:9px 8px;border:1px solid #264761;border-radius:8px;background:#0b1824;color:#8ebee7;font-size:7px;font-weight:900;letter-spacing:.8px;transition:.15s}.case-open:hover{border-color:#4d83aa;background:#102334;color:#d8ecfb}
.panel-foot{display:flex;justify-content:space-between;gap:10px;padding:10px 14px;color:#4f6579;font-size:7px;background:#050b11;border-top:1px solid #122538}
.panel-foot b{color:#66829a}
.panel-empty{padding:55px 24px;text-align:center;color:#60778d;font-size:10px}
@media(max-width:1000px){.panel-table-head,.case-row{grid-template-columns:95px minmax(0,1.4fr) minmax(0,1fr) 120px}.panel-table-head span:nth-child(4),.case-row .case-time{display:none}}
@media(max-width:760px){.panel-head{align-items:flex-start;padding:18px;flex-direction:column}.panel-counter{text-align:left}.panel-toolbar{flex-direction:column;align-items:stretch}.panel-filter{width:100%}.panel-table-head{display:none}.case-row{display:grid;grid-template-columns:1fr auto;gap:10px;padding:13px}.case-no{grid-column:1/-1}.case-title{grid-column:1}.case-status{grid-column:2;grid-row:2/4;min-width:98px}.case-info{grid-column:1}.case-open{grid-column:1/-1}.panel-foot{flex-direction:column}}
@media(max-width:460px){.panel-head h1{font-size:24px}.case-title b{font-size:10px}.case-info{font-size:8px}}
'''


def clean_text(value: Any) -> str:
    s = str(value or "")
    s = re.sub(r"[*_~`]+", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" |•-—:;")


def format_number(row: dict[str, Any], fallback: str) -> str:
    value = clean_text(row.get("number"))
    if not value:
        return fallback
    return value.upper()


def format_date(dt: Any) -> str:
    if isinstance(dt, datetime):
        try:
            return dt.astimezone().strftime("%d/%m/%Y • %H:%M")
        except Exception:
            pass
    return "Data não informada"


def panel_row(row: dict[str, Any], index: int, kind: str) -> str:
    title = clean_text(row.get("name") or row.get("title") or row.get("number") or f"Registro {index}")
    number = format_number(row, f"REG-{index:03d}")
    created = format_date(row.get("created"))
    url = str(row.get("url") or "#")
    label = "BOLETIM" if kind == "bo" else "PERÍCIA"
    info_label = "ATENDIMENTO" if kind == "bo" else "TIPO DE PROCEDIMENTO"
    info_value = "Em andamento" if kind == "bo" else "Perícia externa"
    return f'''<article class="case-row"><div class="case-no">{html.escape(number)}</div><div class="case-title"><b>{html.escape(title)}</b><span>{label} • registro operacional</span></div><div class="case-info"><strong>{info_label}</strong>{html.escape(info_value)}</div><div class="case-time">{html.escape(created)}</div><a class="case-open" href="{html.escape(url, quote=True)}" target="_blank">ABRIR {label}</a></article>'''


def panel_listing(title: str, subtitle: str, rows: list[dict[str, Any]], qra: str, kind: str) -> str:
    label = "BOLETINS" if kind == "bo" else "PERÍCIAS"
    label_singular = "BOLETIM" if kind == "bo" else "PERÍCIA"
    rows = list(rows or [])
    content = "".join(panel_row(row, i + 1, kind) for i, row in enumerate(rows))
    if not content:
        content = f'<div class="panel-empty">Nenhum {label_singular.lower()} ativo encontrado no momento.</div>'
    body = f'''<div class="app"><aside class="side">{v627.sidebar(label)}</aside><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • PAINEL OPERACIONAL</span></div><div class="operator"><i class="online"></i> {html.escape(clean_text(qra))}</div></header><section class="panel-wrap"><div class="panel-head"><div><div class="panel-kicker">DICOR • CONTROLE OPERACIONAL</div><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div><div class="panel-counter"><b>{len(rows)}</b><span>REGISTRO(S) ATIVO(S)</span></div></div><div class="panel-toolbar"><input class="panel-search" placeholder="Pesquisar neste painel..." aria-label="Pesquisar"><select class="panel-filter" aria-label="Filtro"><option>Todos os registros</option><option>Mais recentes</option><option>Mais antigos</option></select></div><div class="panel-body"><div class="panel-table-head"><span>IDENTIFICAÇÃO</span><span>REGISTRO</span><span>SITUAÇÃO</span><span>DATA</span><span>AÇÃO</span></div>{content}<div class="panel-foot"><span><b>Fonte:</b> Discord • atualização automática</span><span><b>Operador:</b> {html.escape(clean_text(qra))}</span></div></div></section></main></div>'''
    return base.page(f"DICOR • {label}", body, base.APP_CSS + PANEL_CSS)


base.listing = panel_listing

async def start_server_v628(client: Any):
    return await v627.start_server_v627(client)

base.start_server = start_server_v628

def install(bot_module: Any):
    return base.install(bot_module)
