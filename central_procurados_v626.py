# -*- coding: utf-8 -*-
"""Central DICOR V626.

Mantém a Central V625 e adiciona uma camada visual específica para
Boletins e Perícias, sem alterar a resolução dos atendimentos.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

import central_procurados_v625 as v625

base = v625.base
_CLIENT: Any = None
_ORIGINAL_START = v625._ORIGINAL_START


def esc(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def dt_label(v: Any) -> str:
    try:
        return v.astimezone().strftime("%d/%m/%Y • %H:%M")
    except Exception:
        return "--"


def status_label(row: dict[str, Any]) -> str:
    raw = str(row.get("status") or "").strip().upper()
    if raw in {"FINALIZADO", "ENCERRADO", "CONCLUÍDO", "CONCLUIDO"}:
        return "FINALIZADO"
    return "EM ANDAMENTO"


def op_card(row: dict[str, Any], kind: str) -> str:
    number = esc(row.get("number") or "SEM NÚMERO")
    name = esc(row.get("name") or row.get("title") or number)
    created = dt_label(row.get("created") or datetime.now(timezone.utc))
    status = status_label(row)
    source = str(row.get("url") or "")
    href = esc(source) if source.startswith("http") else "#"
    badge = "BOLETIM" if kind == "bo" else "PERÍCIA"
    icon = "📋" if kind == "bo" else "🧪"
    return f'''<article class="op-card"><div class="op-icon">{icon}</div><div class="op-main"><div class="op-top"><span class="op-badge">{badge}</span><span class="op-status">{status}</span></div><h3>{name}</h3><div class="op-number">{number}</div><div class="op-date">{created}</div><div class="op-actions"><a href="{href}" target="_blank" rel="noopener" class="op-link">ABRIR ATENDIMENTO →</a></div></div></article>'''


def module_page(title: str, subtitle: str, rows: list[dict[str, Any]], qra: str, kind: str) -> str:
    cards = "".join(op_card(r, kind) for r in rows) or '<div class="empty">Nenhum registro ativo encontrado no Discord.</div>'
    count = len(rows)
    icon = "📋" if kind == "bo" else "🧪"
    tab_bo = "active" if kind == "bo" else ""
    tab_pe = "active" if kind == "pe" else ""
    body = f'''<div class="app"><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i> {esc(qra)}</div></header><nav class="central-tabs"><a class="tab {tab_bo}" href="/boletins">📋 BOLETINS</a><a class="tab {tab_pe}" href="/pericias">🧪 PERÍCIAS</a><a class="tab" href="/procurados">👤 PROCURADOS</a><a class="tab" href="/fotos">📸 FOTOS</a></nav><section class="module-hero"><div class="eyebrow">CENTRAL DICOR • CONSULTA OPERACIONAL</div><div class="module-title-row"><div class="module-big-icon">{icon}</div><div><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div></div><div class="module-stat"><b>{count}</b><span>registro(s) ativo(s)</span></div></section><section class="wanted op-list"><div class="wanted-head"><b>REGISTROS ATIVOS</b><span>FONTE: DISCORD</span></div><div class="op-grid">{cards}</div></section><a class="back" href="/">← Voltar à Central</a></main></div>'''
    css = base.APP_CSS + '''.central-tabs{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.tab{padding:10px 14px;border:1px solid #20384e;border-radius:10px;color:#7890a6;font-size:9px;font-weight:900;letter-spacing:1px}.tab.active{background:#112a40;border-color:#3a6283;color:#e6c76b}.module-hero{position:relative;margin-top:18px;padding:24px;border:1px solid #234560;border-radius:18px;background:linear-gradient(120deg,#091a29,#07111c 70%);overflow:hidden}.module-title-row{display:flex;align-items:center;gap:16px;margin-top:10px}.module-big-icon{width:58px;height:58px;display:grid;place-items:center;border:1px solid #345977;border-radius:14px;background:#0c2133;font-size:27px}.module-hero h1{margin:0;font-size:32px}.module-hero p{margin:7px 0 0;color:#71869a;font-size:11px}.module-stat{position:absolute;right:24px;top:24px;text-align:right}.module-stat b{display:block;font-size:31px;color:#d7b65e}.module-stat span{font-size:8px;color:#60788f;text-transform:uppercase;letter-spacing:1px}.op-list{margin-top:15px}.op-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:12px}.op-card{display:grid;grid-template-columns:52px 1fr;min-height:150px;border:1px solid #1d3449;border-radius:14px;background:linear-gradient(145deg,#0b1825,#07111a);overflow:hidden;transition:.16s}.op-card:hover{border-color:#355e80;transform:translateY(-1px)}.op-icon{display:grid;place-items:center;background:#0b2133;border-right:1px solid #1a3348;font-size:24px}.op-main{padding:14px;min-width:0}.op-top{display:flex;justify-content:space-between;gap:8px;align-items:center}.op-badge{font-size:7px;color:#d9b65d;background:#172d40;border:1px solid #2a4f6d;border-radius:5px;padding:4px 7px;font-weight:900;letter-spacing:1px}.op-status{font-size:7px;color:#4bd18e;letter-spacing:.8px;font-weight:900}.op-card h3{margin:11px 0 4px;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.op-number{font-size:9px;color:#9cb1c2}.op-date{margin-top:7px;font-size:8px;color:#657d92}.op-actions{margin-top:12px}.op-link{display:inline-block;padding:8px 11px;border:1px solid #274762;border-radius:8px;color:#8dbce7;font-size:8px;font-weight:900}.empty{grid-column:1/-1;padding:45px;text-align:center;color:#63788b;border:1px dashed #294055;border-radius:12px}@media(max-width:760px){.op-grid{grid-template-columns:1fr}.module-stat{position:static;text-align:left;margin-top:18px}.module-title-row{align-items:flex-start}.module-hero h1{font-size:26px}}@media(max-width:480px){.main{padding:12px}.tab{font-size:8px;padding:9px 11px}.op-card{grid-template-columns:44px 1fr}.op-card h3{font-size:12px}}'''
    return base.web.Response(text=base.page("DICOR • " + title, body, css), content_type="text/html")


async def boletins(req: Any):
    session = base.read_session(req)
    if not session:
        raise base.web.HTTPFound("/cadastro-operador?next=/boletins")
    qra, _ = session
    rows = list(base.CACHE.get("bo", []) or [])
    return module_page("BOLETINS", "Acompanhamento dos boletins recebidos e áreas de atendimento.", rows, qra, "bo")


async def pericias(req: Any):
    session = base.read_session(req)
    if not session:
        raise base.web.HTTPFound("/cadastro-operador?next=/pericias")
    qra, _ = session
    rows = list(base.CACHE.get("pericia", []) or [])
    return module_page("PERÍCIAS", "Acompanhamento das perícias externas em andamento.", rows, qra, "pe")


class ApplicationPatch(v625.ApplicationPatch):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.router.add_get("/boletins", boletins, name="v626_boletins")
        self.router.add_get("/pericias", pericias, name="v626_pericias")


async def start_server_v626(client: Any):
    global _CLIENT
    _CLIENT = client
    v625._CLIENT = client
    original_app = base.web.Application
    base.web.Application = ApplicationPatch
    try:
        return await _ORIGINAL_START(client)
    finally:
        base.web.Application = original_app

base.start_server = start_server_v626
base.collect_procurados = v625.collect_procurados


def install(bot_module: Any):
    return base.install(bot_module)
