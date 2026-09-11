# -*- coding: utf-8 -*-
"""Central Web DICOR V606.

Painel somente leitura para Boletins, Procurados e Perícias.
Não cria, renomeia ou reabre registros; apenas consulta os dados existentes.
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

import discord
from aiohttp import web

BO_SOURCE_ID = int(os.getenv("DICOR_BO_SOURCE_ID", "1490200514837745754"))
BO_TARGET_ID = int(os.getenv("DICOR_BO_TARGET_ID", "1525762770253910136"))
PERICIA_SOURCE_ID = int(os.getenv("DICOR_PERICIA_SOURCE_ID", "1490200524367200297"))
DATA_DIR = Path(os.getenv("DICOR_DATA_DIR", "data"))
STATE_FILE = DATA_DIR / "dicor_core_v605.json"


def _state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"bo": [], "pericia": []}


def _records(kind: str) -> list[dict[str, Any]]:
    rows = _state().get(kind, [])
    return [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []


def _active(row: dict[str, Any]) -> bool:
    return str(row.get("status", "")).upper() not in {"CONCLUIDO", "FINALIZADO", "FECHADO", "CANCELADO"}


def _esc(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def _card(kind: str, row: dict[str, Any]) -> str:
    n = _esc(row.get("number") or "S/N")
    status = _esc(str(row.get("status") or "AGUARDANDO_AGENTE").replace("_", " "))
    agent = _esc(row.get("agent_name") or "Aguardando responsável")
    created = _esc(row.get("created_at") or "—")
    label = "BOLETIM" if kind == "bo" else "PERÍCIA"
    thread_id = _esc(row.get("thread_id") or "")
    return f'''<article class="card"><div class="card-top"><span class="tag">{label}</span><span class="status">{status}</span></div><h3>Nº {n}</h3><div class="meta"><span>Responsável</span><b>{agent}</b></div><div class="meta"><span>Registro</span><b>{created}</b></div><a class="open" href="/registro/{kind}/{thread_id}">Abrir registro <span>→</span></a></article>'''


def _page(title: str, body: str, counts: tuple[int, int, int], active: str) -> str:
    b, p, pe = counts
    nav = "".join(f'<a class="{"active" if active == key else ""}" href="{href}">{label}<strong>{num}</strong></a>' for key, href, label, num in [("central","/","Central",b+p+pe),("bo","/boletins","Boletins",b),("procurados","/procurados","Procurados",p),("pericia","/pericias","Perícias",pe)])
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DICOR • {title}</title><style>
:root{{--bg:#080a0d;--panel:#11151a;--panel2:#171c22;--line:#2b3138;--gold:#c9a44c;--gold2:#f0d27a;--text:#f1f2f3;--muted:#89919b;--green:#79b889;--red:#c97878}}*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 50% -10%,#20262d 0,#080a0d 45%);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}}header{{border-bottom:1px solid #292e34;background:rgba(8,10,13,.96);position:sticky;top:0;z-index:5;backdrop-filter:blur(12px)}}.head{{max-width:1180px;margin:auto;padding:18px 22px 14px;display:flex;align-items:center;gap:16px}}.logo{{width:52px;height:52px;border:1px solid var(--gold);border-radius:50%;display:grid;place-items:center;color:var(--gold2);font-weight:900;letter-spacing:-2px;box-shadow:0 0 25px #c9a44c22}}.brand h1{{margin:0;font-size:19px;letter-spacing:1.5px}}.brand small{{color:var(--muted);font-size:10px;letter-spacing:2px}}nav{{max-width:1180px;margin:auto;display:flex;gap:4px;padding:0 22px}}nav a{{color:#9ca4ad;text-decoration:none;padding:13px 16px;border-bottom:2px solid transparent;font-size:12px;font-weight:800;letter-spacing:.8px}}nav a:hover,nav a.active{{color:var(--gold2);border-bottom-color:var(--gold)}}nav strong{{margin-left:7px;color:#69717a}}main{{max-width:1180px;margin:0 auto;padding:30px 22px 60px}}.hero{{border:1px solid #30363d;background:linear-gradient(135deg,#151a20,#0e1115);padding:30px;border-radius:14px;box-shadow:0 18px 55px #0007;margin-bottom:20px}}.eyebrow{{color:var(--gold);font-size:11px;font-weight:900;letter-spacing:2.5px}}h2{{font-size:34px;margin:8px 0}}.hero p{{color:var(--muted);margin:0;max-width:700px}}.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:18px 0 26px}}.stat{{background:var(--panel);border:1px solid var(--line);padding:20px;border-radius:12px}}.stat span{{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:1px}}.stat b{{display:block;color:var(--gold2);font-size:30px;margin-top:5px}}.section{{display:flex;justify-content:space-between;align-items:center;margin:25px 0 12px}}.section h3{{font-size:12px;letter-spacing:1.8px;margin:0;color:#c9cdd1}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}.card{{background:linear-gradient(145deg,#14191f,#0f1216);border:1px solid var(--line);border-radius:12px;padding:19px;transition:.18s}}.card:hover{{border-color:#6e5b30;transform:translateY(-1px)}}.card-top{{display:flex;justify-content:space-between;gap:10px}}.tag{{font-size:9px;color:var(--gold2);border:1px solid #66542d;padding:5px 8px;border-radius:20px;letter-spacing:1px;font-weight:900}}.status{{font-size:9px;color:var(--green);text-transform:uppercase;letter-spacing:.7px}}.card h3{{font-size:23px;margin:14px 0}}.meta{{border-top:1px solid #22272d;padding:9px 0;display:flex;justify-content:space-between;gap:10px;font-size:11px}}.meta span{{color:var(--muted)}}.open{{display:flex;justify-content:space-between;margin-top:8px;padding:10px 0 0;color:var(--gold2);text-decoration:none;font-size:11px;font-weight:800}}.empty{{border:1px dashed #343a41;border-radius:12px;padding:35px;text-align:center;color:var(--muted)}}footer{{max-width:1180px;margin:auto;padding:0 22px 35px;color:#555d65;font-size:10px;letter-spacing:1px}}@media(max-width:700px){{.grid,.stats{{grid-template-columns:1fr}}nav{{overflow:auto}}h2{{font-size:27px}}}}
</style></head><body><header><div class="head"><div class="logo">PF<br><small>D</small></div><div class="brand"><h1>DICOR • CENTRAL DE INTELIGÊNCIA</h1><small>POLÍCIA FEDERAL • CONSULTA INTERNA • SOMENTE LEITURA</small></div></div><nav>{nav}</nav></header><main>{body}</main><footer>DICOR • POLÍCIA FEDERAL • AMBIENTE FICTÍCIO DE GTA RP</footer></body></html>'''


def _cards(kind: str, rows: list[dict[str, Any]]) -> str:
    active = [r for r in rows if _active(r)]
    return ''.join(_card(kind, r) for r in active) or '<div class="empty">Nenhum registro ativo no momento.</div>'


def _dashboard() -> str:
    bo = _records("bo"); pe = _records("pericia"); proc = []
    body = '''<section class="hero"><div class="eyebrow">PAINEL OPERACIONAL</div><h2>Central de Inteligência</h2><p>Visão rápida dos módulos operacionais da DICOR, com acesso aos boletins, procurados e perícias.</p></section>'''
    body += f'<section class="stats"><a class="stat" href="/boletins"><span>Boletins ativos</span><b>{sum(_active(x) for x in bo)}</b></a><a class="stat" href="/procurados"><span>Procurados ativos</span><b>{len(proc)}</b></a><a class="stat" href="/pericias"><span>Perícias pendentes</span><b>{sum(_active(x) for x in pe)}</b></a></section>'
    body += '<div class="section"><h3>MÓDULOS DA CENTRAL</h3></div><section class="grid"><article class="card"><span class="tag">BOLETINS</span><h3>Boletins de ocorrência</h3><p style="color:#89919b">Acompanhe os atendimentos e responsáveis.</p><a class="open" href="/boletins">Acessar boletins →</a></article><article class="card"><span class="tag">PERÍCIAS</span><h3>Perícias externas</h3><p style="color:#89919b">Consulte perícias pendentes e em andamento.</p><a class="open" href="/pericias">Acessar perícias →</a></article><article class="card"><span class="tag">PROCURADOS</span><h3>Procurados</h3><p style="color:#89919b">Consulta do cadastro de procurados.</p><a class="open" href="/procurados">Acessar procurados →</a></article></section>'
    return _page("Central de Inteligência", body, (sum(_active(x) for x in bo), len(proc), sum(_active(x) for x in pe)), "central")


def _listing(kind: str) -> str:
    rows = _records(kind)
    active = [x for x in rows if _active(x)]
    title = "Boletins" if kind == "bo" else "Perícias"
    label = "BOLETINS ATIVOS" if kind == "bo" else "PERÍCIAS PENDENTES / EM ANDAMENTO"
    body = f'<section class="hero"><div class="eyebrow">{label}</div><h2>{title}</h2><p>Somente leitura. Este painel não cria, renomeia ou reabre registros.</p></section><section class="grid">{_cards(kind, rows)}</section>'
    bo = len([x for x in _records("bo") if _active(x)]); pe = len([x for x in _records("pericia") if _active(x)])
    return _page(title, body, (bo,0,pe), "bo" if kind == "bo" else "pericia")


def _procurados() -> str:
    # O cadastro legado de procurados pode variar. A Central mantém a rota e deixa claro quando não há fonte disponível.
    body = '<section class="hero"><div class="eyebrow">CADASTRO OPERACIONAL</div><h2>Procurados</h2><p>Consulta interna de pessoas marcadas como procuradas no sistema DICOR.</p></section><div class="empty">Nenhum cadastro de procurados disponível na fonte atual.</div>'
    bo = len([x for x in _records("bo") if _active(x)]); pe = len([x for x in _records("pericia") if _active(x)])
    return _page("Procurados", body, (bo,0,pe), "procurados")


def setup_central(client: discord.Client) -> web.Application:
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text=_dashboard(), content_type='text/html'))
    app.router.add_get('/boletins', lambda r: web.Response(text=_listing('bo'), content_type='text/html'))
    app.router.add_get('/pericias', lambda r: web.Response(text=_listing('pericia'), content_type='text/html'))
    app.router.add_get('/procurados', lambda r: web.Response(text=_procurados(), content_type='text/html'))
    return app
