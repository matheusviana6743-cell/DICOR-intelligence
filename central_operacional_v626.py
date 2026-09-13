# -*- coding: utf-8 -*-
"""DICOR Central V626 - visual operacional para Boletins e Pericias."""
from __future__ import annotations
import re
from typing import Any
import central_procurados_v625 as v625
import central_discord_v613 as base

_ORIGINAL_LISTING = base.listing
_ORIGINAL_APP = v625.ApplicationPatch


def _date(row: dict[str, Any]) -> str:
    try:
        return row.get("created").astimezone().strftime("%d/%m/%Y • %H:%M")
    except Exception:
        return "--"


def _record_url(row: dict[str, Any], kind: str) -> str:
    raw = str(row.get("url") or "")
    m = re.search(r"discord\.com/channels/\d+/(\d+)", raw)
    return f"/registro/{kind}/{m.group(1)}" if m else raw or "#"


def listing(title: str, description: str, rows: list[dict[str, Any]], qra: str, kind: str) -> str:
    is_bo = kind == "bo"
    label = "BOLETINS DE OCORRÊNCIA" if is_bo else "PERÍCIAS"
    eyebrow = "CENTRAL DICOR • REGISTROS OPERACIONAIS" if is_bo else "CENTRAL DICOR • NÚCLEO PERICIAL"
    sub = "Ocorrências registradas e ainda em atendimento." if is_bo else "Perícias externas pendentes de conclusão."
    icon = "▣" if is_bo else "◈"
    empty = "Nenhum registro ativo encontrado." if rows else "Nenhum registro ativo encontrado."
    cards = []
    for r in rows:
        number = base.esc(r.get("number", "S/N"))
        name = base.esc(r.get("name", "Registro operacional"))
        status = base.esc(r.get("status", "EM ABERTO"))
        date = base.esc(_date(r))
        preview = base.esc(r.get("preview", "") or sub)
        href = base.esc(_record_url(r, kind))
        cards.append(f'''<a class="record" href="{href}"><div class="record-top"><span class="record-icon">{icon}</span><div><small>{label}</small><strong>Nº {number}</strong></div><span class="status">{status}</span></div><div class="record-title">{name}</div><div class="record-preview">{preview}</div><div class="record-foot"><span>REGISTRADO EM {date}</span><b>VER {"BOLETIM" if is_bo else "PERÍCIA"} COMPLETO →</b></div></a>''')
    cards_html = "".join(cards) or f'<div class="empty">{empty}</div>'
    total = len(rows)
    body = f'''<div class="app"><aside class="side"><div class="brand">{base.img(base.DICOR_LOGO, "", "DICOR")}<div><b>DICOR</b><small>INTELIGÊNCIA</small></div></div><nav class="side-nav"><a href="/">⌂ <span>Central</span></a><a class="active" href="/boletins">▣ <span>Boletins</span></a><a href="/procurados">◎ <span>Procurados</span></a><a class="{'' if is_bo else 'active'}" href="/pericias">◈ <span>Perícias</span></a><a href="/fichas">▤ <span>Banco de Dados</span></a><a href="/arvore">⌘ <span>Árvore</span></a></nav><div class="side-note">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<br><br>CONSULTA INTERNA<br>SISTEMA INTEGRADO</div></aside><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i> {base.esc(qra)}</div></header><nav class="tabs"><a class="{'active' if is_bo else ''}" href="/boletins">BOLETINS</a><a class="{'active' if not is_bo else ''}" href="/pericias">PERÍCIAS</a></nav><section class="hero"><div class="eyebrow">{eyebrow}</div><h1>{label}</h1><p>{sub}</p><div class="hero-stats"><div><span>REGISTROS ATIVOS</span><b>{total}</b></div><div><span>CONSULTA</span><b>INTERNA</b></div><div><span>STATUS</span><b>MONITORADO</b></div></div></section><section class="records"><div class="section-head"><div><small>PAINEL OPERACIONAL</small><h2>{label}</h2></div><span>{total:02d} REGISTRO(S)</span></div><div class="record-grid">{cards_html}</div></section><div class="foot">DICOR • INTELIGÊNCIA E COMBATE AO CRIME ORGANIZADO</div></main></div>'''
    css = base.APP_CSS + '''.side-nav{display:flex;flex-direction:column;gap:5px;margin-top:18px}.side-nav a{display:flex;align-items:center;gap:12px;padding:12px 11px;border:1px solid transparent;border-radius:10px;color:#71869a;font-size:11px;font-weight:800}.side-nav a:hover,.side-nav a.active{background:#0d1c2b;border-color:#25435e;color:#e6c766}.side-nav a.active{box-shadow:inset 3px 0 #d0a541}.tabs{display:flex;gap:8px;margin-top:17px}.tabs a{padding:10px 17px;border:1px solid #1d344b;border-radius:9px;color:#6f859a;font-size:9px;font-weight:900;letter-spacing:1.4px}.tabs a.active{border-color:#80601e;background:#17140c;color:#e8c55d}.hero{margin-top:14px;padding:24px 26px}.hero h1{font-size:31px}.hero-stats{display:flex;gap:9px;margin-top:18px;flex-wrap:wrap}.hero-stats div{min-width:145px;padding:10px 13px;border:1px solid #1c344a;border-radius:9px;background:#07101a}.hero-stats span{display:block;font-size:7px;color:#587188;letter-spacing:1.2px}.hero-stats b{display:block;margin-top:5px;font-size:13px;color:#dcb75c}.records{margin-top:16px;border:1px solid #1b3043;border-radius:15px;background:#070e16;overflow:hidden}.section-head{display:flex;align-items:center;justify-content:space-between;padding:17px 19px;border-bottom:1px solid #182a3b}.section-head small{color:#d2aa50;font-size:8px;font-weight:900;letter-spacing:1.8px}.section-head h2{margin:5px 0 0;font-size:15px}.section-head>span{color:#5e768d;font-size:8px;font-weight:900}.record-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:13px}.record{display:block;padding:16px;border:1px solid #1b3247;border-radius:13px;background:linear-gradient(145deg,#0c1825,#071019);transition:.18s}.record:hover{transform:translateY(-2px);border-color:#876820;box-shadow:0 12px 35px #0007}.record-top{display:flex;align-items:center;gap:10px}.record-icon{width:39px;height:39px;display:grid;place-items:center;border:1px solid #765b20;border-radius:9px;background:#121109;color:#dfbb5e;font-size:17px}.record-top small{display:block;color:#627b92;font-size:7px;font-weight:900;letter-spacing:1.3px}.record-top strong{display:block;color:#e8eef3;font-size:12px;margin-top:4px}.status{margin-left:auto;padding:5px 7px;border-radius:6px;background:#102b25;color:#66d3a4;font-size:7px;font-weight:900;letter-spacing:.8px}.record-title{margin-top:16px;color:#f0f4f7;font-size:16px;font-weight:900}.record-preview{margin-top:8px;color:#71859a;font-size:10px;line-height:1.55;min-height:32px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.record-foot{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-top:16px;padding-top:11px;border-top:1px solid #172a3b;color:#4f687f;font-size:7px;letter-spacing:.8px}.record-foot b{color:#d9b453;font-size:8px;white-space:nowrap}.empty{grid-column:1/-1;padding:55px 20px;text-align:center;color:#61778c;font-size:10px}@media(max-width:800px){.side-nav{flex-direction:row;overflow:auto}.side-nav a{white-space:nowrap}.side-nav a span{display:none}.record-grid{grid-template-columns:1fr}.hero-stats div{flex:1;min-width:120px}}@media(max-width:520px){.record{padding:13px}.record-foot{align-items:flex-start;flex-direction:column}.record-foot b{white-space:normal}.hero{padding:20px}.hero h1{font-size:26px}}
'''
    return base.page(f"DICOR • {label.title()}", body, css)


async def detail(req: Any):
    session = base.read_session(req)
    if not session:
        raise base.web.HTTPFound("/cadastro-operador")
    qra, _ = session
    kind = req.match_info.get("kind", "bo")
    rid = req.match_info.get("rid", "")
    channel = await base.get_channel(v625._CLIENT, int(rid)) if rid.isdigit() else None
    msgs = []
    if channel is not None:
        try:
            async for m in channel.history(limit=80, oldest_first=True):
                txt = base.text_of(m)
                if txt:
                    msgs.append((m, txt))
        except Exception:
            pass
    title = "BOLETIM DE OCORRÊNCIA" if kind == "bo" else "PERÍCIA"
    number = base.number_from(getattr(channel, "name", "")) if channel else "S/N"
    blocks = "".join(f'<article class="msg"><div class="msg-head"><b>{base.esc(getattr(getattr(m,"author",None),"display_name", "Registro"))}</b><span>{base.esc(getattr(m,"created_at",None).astimezone().strftime("%d/%m/%Y • %H:%M") if getattr(m,"created_at",None) else "--")}</span></div><div>{base.esc(txt)}</div></article>' for m,txt in msgs) or '<div class="empty">Não foi possível carregar o conteúdo completo deste registro.</div>'
    body = f'''<div class="app"><aside class="side"><div class="brand">{base.img(base.DICOR_LOGO, "", "DICOR")}<div><b>DICOR</b><small>INTELIGÊNCIA</small></div></div><div class="side-note">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<br><br>CONSULTA INTERNA</div></aside><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i> {base.esc(qra)}</div></header><a class="back" href="/{'boletins' if kind=='bo' else 'pericias'}">← VOLTAR AOS REGISTROS</a><section class="hero"><div class="eyebrow">REGISTRO OPERACIONAL • {title}</div><h1>{title}</h1><p>Nº {base.esc(number)} • Visualização completa dentro da Central.</p></section><section class="records"><div class="section-head"><div><small>CONTEÚDO ORIGINAL</small><h2>Histórico do registro</h2></div><span>{len(msgs):02d} MENSAGEM(NS)</span></div><div class="messages">{blocks}</div></section></main></div>'''
    css = base.APP_CSS + '''.back{margin:15px 0 0 2px;display:inline-block}.messages{padding:14px;display:grid;gap:10px}.msg{padding:15px;border:1px solid #1b3348;border-radius:12px;background:#0a141f}.msg-head{display:flex;justify-content:space-between;gap:12px;padding-bottom:9px;margin-bottom:10px;border-bottom:1px solid #182b3d}.msg-head b{font-size:10px;color:#e5c15e}.msg-head span{font-size:8px;color:#5e768d}.msg>div:last-child{font-size:11px;line-height:1.7;color:#c3ced8;white-space:pre-wrap}.empty{padding:45px;text-align:center;color:#62778b}@media(max-width:600px){.msg-head{flex-direction:column}}
'''
    return base.web.Response(text=base.page(f"DICOR • {title}", body, css), content_type="text/html")


class ApplicationPatch(_ORIGINAL_APP):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.router.add_get("/registro/{kind}/{rid}", detail, name="v626_record_detail")


async def start_server_v626(client: Any):
    old_listing = base.listing
    old_app = v625.ApplicationPatch
    base.listing = listing
    v625.ApplicationPatch = ApplicationPatch
    try:
        return await v625.start_server_v625(client)
    finally:
        base.listing = old_listing
        v625.ApplicationPatch = old_app

base.start_server = start_server_v626


def install(bot_module: Any):
    return base.install(bot_module)
