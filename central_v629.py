# -*- coding: utf-8 -*-
"""DICOR Central V629 - refinamento visual de Boletins e Perícias.

Mantém a base V628/V627 e altera somente a apresentação e os cards
internos de Boletins e Perícias. Procurados/Fotos permanecem intactos.
"""
from __future__ import annotations

import html
from typing import Any

import central_v628 as v628

base = v628.base
v627 = v628.v627

CSS = r'''
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;color:#edf3f7}body{background:#04080d;overflow-x:hidden}body:before{content:"";position:fixed;inset:0;pointer-events:none;background:radial-gradient(circle at 78% -8%,#24537c44 0,transparent 38%),radial-gradient(circle at 8% 30%,#b8862410 0,transparent 28%),linear-gradient(135deg,#07111b,#04080d 58%,#070b10)}a{text-decoration:none;color:inherit}.wrap{position:relative;z-index:1;width:min(1320px,calc(100% - 28px));margin:auto;padding:18px 0 52px}.bar{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:14px 18px;border:1px solid #203b53;border-radius:18px;background:linear-gradient(135deg,#0b1724f5,#07101af5);box-shadow:0 22px 65px #0009}.brand{display:flex;align-items:center;gap:13px;min-width:0}.brand img{width:50px;height:50px;object-fit:contain;filter:drop-shadow(0 8px 18px #0009)}.brand strong{display:block;font-size:11px;letter-spacing:1.8px;white-space:nowrap}.brand span{display:block;margin-top:5px;color:#d4aa4e;font-size:8px;font-weight:900;letter-spacing:1.8px}.user{color:#7e93a7;font-size:9px;white-space:nowrap}.tabs{display:flex;gap:8px;overflow:auto;padding:13px 0 0}.tab{flex:0 0 auto;padding:10px 15px;border:1px solid #1d3549;border-radius:10px;background:#08121c;color:#8096a9;font-size:8px;font-weight:950;letter-spacing:1.4px;transition:.18s}.tab:hover{border-color:#315775;color:#c8d6e2}.tab.on{color:#f2cd69;border-color:#806326;background:linear-gradient(135deg,#1a180f,#11130f);box-shadow:0 8px 25px #b7862312}.hero{position:relative;overflow:hidden;margin-top:13px;padding:28px;border:1px solid #294965;border-radius:20px;background:linear-gradient(125deg,#102436f5,#09131ef5 58%,#0b1723f5);box-shadow:0 25px 75px #0009,inset 0 0 70px #164b7210}.hero:after{content:"";position:absolute;right:-120px;top:-160px;width:410px;height:410px;border-radius:50%;border:1px solid #4b8bb933;box-shadow:0 0 0 38px #4b8bb90a,0 0 0 78px #4b8bb905}.eyebrow{position:relative;z-index:1;color:#d4aa4e;font-size:8px;font-weight:950;letter-spacing:2.4px}.hero h1{position:relative;z-index:1;margin:8px 0 7px;font-size:34px;letter-spacing:1px}.hero p{position:relative;z-index:1;max-width:760px;margin:0;color:#8196a9;font-size:11px;line-height:1.7}.stats{position:relative;z-index:1;display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:20px}.stat{padding:14px 15px;border:1px solid #1c3449;border-radius:12px;background:#07111b}.stat b{display:block;font-size:22px;color:#e7eef3}.stat span{display:block;margin-top:5px;color:#627b91;font-size:7px;font-weight:900;letter-spacing:1.3px}.stat.gold b{color:#e1bd5b}.stat.blue b{color:#6bb7ee}.stat.green b{color:#68cf9b}.records-head{display:flex;align-items:end;justify-content:space-between;gap:15px;margin-top:18px}.records-head h2{margin:0;font-size:13px;letter-spacing:1.3px}.records-head p{margin:5px 0 0;color:#627b90;font-size:9px}.search{display:flex;gap:9px;margin-top:12px}.search input{flex:1;min-width:0;height:44px;padding:0 14px;border:1px solid #24425a;border-radius:10px;background:#07111b;color:#eef4f7;outline:0;font-size:11px}.search input:focus{border-color:#4a789c;box-shadow:0 0 0 3px #2d608b22}.search button{height:44px;padding:0 18px;border:0;border-radius:10px;background:linear-gradient(135deg,#f0cf70,#9c6e18);color:#080b0d;font-size:8px;font-weight:950;letter-spacing:1px;cursor:pointer}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:13px}.card{position:relative;display:flex;flex-direction:column;min-height:270px;padding:18px;border:1px solid #1d384f;border-radius:16px;background:linear-gradient(150deg,#0b1825,#07101a);box-shadow:0 14px 35px #0005;transition:transform .18s,border-color .18s,box-shadow .18s}.card:hover{transform:translateY(-2px);border-color:#365e7b;box-shadow:0 20px 45px #0008}.card:before{content:"";position:absolute;left:0;top:0;width:4px;height:100%;border-radius:16px 0 0 16px;background:linear-gradient(#d5ab4d,#6c5019);opacity:.9}.card.bo:before{background:linear-gradient(#6fb9ed,#28577f)}.top{display:flex;justify-content:space-between;gap:14px;padding-left:4px}.kind{color:#728ba0;font-size:8px;font-weight:950;letter-spacing:1.7px}.num{margin-top:5px;color:#f0cb64;font-size:25px;font-weight:950;letter-spacing:.5px}.bo .num{color:#74baf0}.status{height:max-content;padding:7px 10px;border:1px solid #2c6d52;border-radius:999px;background:#0d241b;color:#72d4a4;font-size:7px;font-weight:950;letter-spacing:1px}.status.closed{border-color:#684047;background:#241115;color:#e18c98}.preview{margin-top:14px;padding:13px;border:1px solid #172d40;border-radius:11px;background:#07111a;color:#b9c7d2;font-size:10px;line-height:1.7;display:-webkit-box;-webkit-line-clamp:7;-webkit-box-orient:vertical;overflow:hidden}.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:auto;padding:15px 0 0 4px}.chip{padding:6px 8px;border:1px solid #1b3348;border-radius:7px;background:#09141f;color:#71899e;font-size:7px;font-weight:800}.btn-row{display:flex;gap:8px;flex-wrap:wrap;padding-left:4px}.btn{display:inline-flex;align-items:center;justify-content:center;margin-top:10px;padding:10px 13px;border-radius:9px;background:linear-gradient(135deg,#e8c35e,#986b18);color:#080b0d;font-size:8px;font-weight:950;letter-spacing:1px}.btn.secondary{border:1px solid #28475f;background:#0a1723;color:#91b9d9}.detail{margin-top:16px;padding:25px;border:1px solid #26455f;border-radius:18px;background:linear-gradient(145deg,#0a1723,#07101a);box-shadow:0 22px 60px #0008}.detail h2{margin:8px 0 18px;color:#f0cb64;font-size:28px}.detail .row{padding:13px 0;border-bottom:1px solid #172c3e}.detail .label{margin-bottom:6px;color:#657f96;font-size:7px;font-weight:950;letter-spacing:1.5px}.detail .value{color:#d0d9e0;font-size:11px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere}.back{display:inline-flex;margin-top:14px;color:#82add0;font-size:9px;font-weight:900;letter-spacing:.8px}.empty{grid-column:1/-1;padding:55px 20px;text-align:center;border:1px dashed #29445a;border-radius:15px;color:#6d8396;font-size:10px}.foot{text-align:center;margin-top:22px;color:#3f5568;font-size:8px;letter-spacing:1px}@media(max-width:900px){.stats{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}}@media(max-width:600px){.wrap{width:calc(100% - 16px);padding-top:9px}.bar{padding:12px}.brand img{width:40px;height:40px}.brand strong{font-size:9px}.brand span{font-size:7px}.user{display:none}.hero{padding:21px}.hero h1{font-size:27px}.stats{grid-template-columns:1fr 1fr}.search{flex-direction:column}.search button{width:100%}.card{min-height:250px}.records-head{display:block}.records-head p{margin-top:7px}.detail{padding:19px}.detail h2{font-size:23px}}
'''


def esc(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def shell(request: Any, title: str, kind: str, content: str, stats: tuple[str,str,str] = ("—","—","ATIVO")) -> str:
    sess = base.read_session(request)
    qra, passport = sess or ("ACESSO LIVRE", "—")
    nav = "".join([
        f'<a class="tab {"on" if kind=="BOLETINS" else ""}" href="/boletins">BOLETINS</a>',
        f'<a class="tab {"on" if kind=="PERÍCIAS" else ""}" href="/pericias">PERÍCIAS</a>',
        '<a class="tab" href="/procurados">PROCURADOS</a>',
        '<a class="tab" href="/fotos">FOTOS</a>',
    ])
    subtitle = "Consulta e acompanhamento dos registros operacionais." if kind == "BOLETINS" else "Consulta organizada dos registros periciais e evidências vinculadas."
    body = f'''<div class="wrap"><header class="bar"><div class="brand">{base.img(base.DICOR_LOGO,"logo","DICOR")}<div><strong>PCPT — POLÍCIA CAPITAL / POLÍCIA FEDERAL</strong><span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div></div><div class="user">{esc(qra)} • {esc(passport)}</div></header><nav class="tabs">{nav}</nav><section class="hero"><div class="eyebrow">CENTRAL DICOR • PAINEL OPERACIONAL</div><h1>{esc(kind)}</h1><p>{esc(title or subtitle)}</p><div class="stats"><div class="stat gold"><b>{esc(stats[0])}</b><span>REGISTROS ENCONTRADOS</span></div><div class="stat blue"><b>{esc(stats[1])}</b><span>CANAL OFICIAL</span></div><div class="stat green"><b>ONLINE</b><span>MONITORAMENTO</span></div><div class="stat"><b>INTERNO</b><span>ACESSO CENTRAL</span></div></div></section>{content}<div class="foot">DICOR • INTELIGÊNCIA E COMBATE AO CRIME ORGANIZADO</div></div>'''
    return base.page("DICOR • " + kind, body, CSS)


def records_page(request: Any, kind: str):
    # Mantém o coletor e a lógica V627. O middleware continuará chamando esta versão.
    import asyncio
    return _records_page_async(request, kind)


async def _records_page_async(request: Any, kind: str):
    channel_id = v627.BO_CHANNEL_ID if kind == "BOLETINS" else v627.PERICIA_CHANNEL_ID
    rows = await v627.source_rows(channel_id)
    q = str(request.query.get("q", "")).strip().casefold()
    if q:
        rows = [r for r in rows if q in r["text"].casefold() or q in r["number"].casefold()]
    cards = []
    for r in rows:
        closed = v627.is_closed(r["text"])
        label = "BOLETIM DE OCORRÊNCIA" if kind == "BOLETINS" else "REGISTRO DE PERÍCIA"
        classes = "card bo" if kind == "BOLETINS" else "card"
        status_class = "status closed" if closed else "status"
        date = esc(r.get("created") or "Não informado")
        cards.append(f'''<article class="{classes}"><div class="top"><div><div class="kind">{label}</div><div class="num">Nº {esc(r["number"])}</div></div><span class="{status_class}">{"ENCERRADO" if closed else "EM ABERTO"}</span></div><div class="preview">{esc(v627.excerpt(r["text"]))}</div><div class="chips"><span class="chip">AUTOR: {esc(r.get("author"))}</span><span class="chip">RECEBIDO: {date}</span></div><div class="btn-row"><a class="btn" href="/{'boletim' if kind=='BOLETINS' else 'pericia'}/{r['message_id']}">VER REGISTRO COMPLETO →</a></div></article>''')
    content = f'''<div class="records-head"><div><h2>{"BOLETINS ATIVOS" if kind=="BOLETINS" else "PERÍCIAS REGISTRADAS"}</h2><p>Clique em um registro para visualizar o conteúdo completo dentro da Central.</p></div></div><form class="search" method="get"><input name="q" value="{esc(q)}" placeholder="Pesquisar por número, nome ou conteúdo"><button type="submit">PESQUISAR</button></form><div class="grid">{''.join(cards) if cards else '<div class="empty">Nenhum registro encontrado no canal oficial.</div>'}</div>'''
    await v627.log_central(f"consulta {kind.lower()}", request, f"filtro={q or 'nenhum'} registros={len(rows)}")
    return base.web.Response(text=shell(request, "Dados consultados diretamente do canal oficial do Discord.", kind, content, (str(len(rows)), str(channel_id))), content_type="text/html")


async def record_detail(request: Any, kind: str, message_id: int):
    # Reusa integralmente a página detalhada V627, apenas com a nova casca visual.
    channel_id = v627.BO_CHANNEL_ID if kind == "BOLETINS" else v627.PERICIA_CHANNEL_ID
    messages = await v627.channel_history(channel_id, 150)
    target = next((m for m in messages if int(getattr(m, "id", 0)) == int(message_id)), None)
    if target is None:
        raise base.web.HTTPNotFound(text="Registro não encontrado no canal oficial.")
    text = v627.clean_markdown(v627.text_of(target))
    number = v627.number_from(text)
    author = getattr(getattr(target, "author", None), "display_name", "Não informado")
    created = getattr(target, "created_at", None)
    attachments = getattr(target, "attachments", []) or []
    embeds = getattr(target, "embeds", []) or []
    media = ''.join(f'<div class="row"><div class="label">ANEXO</div><div class="value"><a class="btn secondary" href="{esc(getattr(a,"url",""))}" target="_blank" rel="noopener">ABRIR ARQUIVO →</a></div></div>' for a in attachments)
    emb = ''.join(f'<div class="row"><div class="label">EMBED</div><div class="value">{esc((getattr(e,"title","") or "") + "\n" + (getattr(e,"description","") or ""))}</div></div>' for e in embeds)
    content = f'''<div class="detail"><a class="back" href="/{'boletins' if kind=='BOLETINS' else 'pericias'}">← VOLTAR PARA {kind}</a><div class="eyebrow">{'BOLETIM DE OCORRÊNCIA' if kind=='BOLETINS' else 'REGISTRO DE PERÍCIA'}</div><h2>Nº {esc(number)}</h2><div class="row"><div class="label">AUTOR DO REGISTRO</div><div class="value">{esc(author)}</div></div><div class="row"><div class="label">DATA DE RECEBIMENTO</div><div class="value">{esc(created)}</div></div><div class="row"><div class="label">CONTEÚDO COMPLETO</div><div class="value">{esc(text)}</div></div>{emb}{media}</div>'''
    await v627.log_central(f"abriu {kind.lower()}", request, f"numero={number} message_id={message_id}")
    return base.web.Response(text=shell(request, "Registro completo dentro da Central.", kind, content, ("1", str(channel_id))), content_type="text/html")

# O middleware V627 consulta os globais do próprio módulo V627.
v627.CSS = CSS
v627.shell = shell
v627.records_page = records_page
v627.record_detail = record_detail

async def start_server_v629(client: Any):
    return await v628.start_server_v628(client)

base.start_server = start_server_v629

def install(bot_module: Any):
    return base.install(bot_module)
