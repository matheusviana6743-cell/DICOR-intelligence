# -*- coding: utf-8 -*-
"""Central DICOR V626 — novo layout completo.

Apenas apresentação/rotas web são alteradas. A lógica do bot, Procurados,
Fivemanage e permissões existentes permanecem nas versões já funcionais.
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Any

import central_discord_v613 as base
import central_procurados_v625 as v625
import central_procurados_v622 as v622


def esc(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


CSS = r'''
:root{--bg:#050a10;--panel:#0a131e;--panel2:#0d1925;--line:#1d3247;--blue:#2f78b8;--blue2:#68b5f2;--gold:#d8b35b;--text:#eaf1f6;--muted:#71869a;--danger:#f16b72;--ok:#4bd49a}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;background:radial-gradient(circle at 80% -10%,#133357 0,#07111c 35%,#04080d 72%);color:var(--text)}body{overflow-x:hidden}a{text-decoration:none;color:inherit}.shell{min-height:100vh;display:flex}.sidebar{width:250px;flex:none;border-right:1px solid var(--line);background:linear-gradient(180deg,#09131e,#050a10);padding:18px 14px;position:sticky;top:0;height:100vh}.brand{display:flex;align-items:center;gap:11px;padding:4px 8px 18px;border-bottom:1px solid var(--line)}.brand img{width:48px;height:48px;object-fit:contain;background:transparent;filter:drop-shadow(0 8px 18px #0008)}.brand b{font-size:15px;letter-spacing:2.2px}.brand small{display:block;color:var(--gold);font-size:8px;letter-spacing:2px;margin-top:4px}.nav{display:grid;gap:7px;margin-top:18px}.nav a{padding:12px 12px;border:1px solid transparent;border-radius:11px;color:#8095a8;font-size:9px;font-weight:900;letter-spacing:1px;transition:.18s}.nav a:hover,.nav a.active{background:#102337;border-color:#244764;color:#e6c46b;transform:translateX(2px)}.sidebar-foot{position:absolute;left:14px;right:14px;bottom:16px;border:1px solid var(--line);background:#07101a;border-radius:11px;padding:12px;color:#61758a;font-size:8px;line-height:1.7}.content{flex:1;min-width:0;padding:20px 24px 42px}.topbar{display:flex;justify-content:space-between;align-items:center;gap:16px;padding-bottom:15px;border-bottom:1px solid var(--line)}.system-title{font-size:11px;font-weight:900;letter-spacing:1.7px}.system-title span{display:block;color:#658098;font-size:8px;letter-spacing:1.2px;margin-top:4px}.operator{display:flex;align-items:center;gap:7px;color:#7f94a8;font-size:8px}.dot{width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 11px #4bd49a}.hero{margin-top:18px;padding:27px;border:1px solid #244765;border-radius:18px;background:linear-gradient(130deg,#0c1a28,#09131e 58%,#07111b);box-shadow:inset 0 0 70px #0d47761b;position:relative;overflow:hidden}.hero:after{content:'';position:absolute;right:-130px;top:-160px;width:420px;height:420px;border-radius:50%;border:1px solid #367eb744;box-shadow:0 0 0 42px #3277aa10,0 0 0 84px #3277aa07}.eyebrow{font-size:8px;letter-spacing:2.2px;color:var(--blue2);font-weight:900}.hero h1{font-size:38px;line-height:1;margin:9px 0 8px;letter-spacing:1.4px}.hero p{margin:0;color:#74899d;font-size:10px;max-width:720px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px}.stat{padding:14px;border:1px solid var(--line);border-radius:12px;background:#07111b}.stat span{display:block;color:#61788e;font-size:7px;letter-spacing:1.2px}.stat b{display:block;margin-top:7px;font-size:25px}.stat.blue b{color:#62b0ef}.stat.gold b{color:var(--gold)}.stat.red b{color:var(--danger)}.section{margin-top:14px;border:1px solid var(--line);border-radius:15px;background:#060d15;overflow:hidden}.section-head{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid #172a3c}.section-head b{font-size:10px;letter-spacing:1.2px}.section-head span{font-size:8px;color:#62788c}.toolbar{display:flex;gap:9px;margin-top:14px}.search{flex:1;height:44px;border:1px solid #23425e;background:#08131f;color:#edf3f8;border-radius:10px;padding:0 13px;outline:none}.search:focus{border-color:var(--blue2);box-shadow:0 0 0 3px #2a73b624}.btn{height:44px;border:0;border-radius:10px;padding:0 17px;font-weight:900;font-size:8px;letter-spacing:.5px;cursor:pointer}.btn.blue{background:linear-gradient(135deg,#2e78b8,#174b78);color:#fff}.btn.gold{background:linear-gradient(135deg,#edd179,#a87517);color:#080b0e}.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;padding:12px}.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;padding:12px}.card{border:1px solid #1a3044;border-radius:12px;background:linear-gradient(155deg,#0c1825,#07101a);overflow:hidden}.photo{height:165px;background:#05090e}.photo img{width:100%;height:100%;object-fit:cover}.body{padding:12px}.tag{display:inline-block;padding:4px 7px;border-radius:5px;background:#174b79;color:#b8dcfa;font-size:7px;font-weight:900;letter-spacing:1px}.name{font-size:13px;font-weight:900;margin:9px 0 5px}.meta{font-size:8px;color:#74889a;line-height:1.7}.linkbtn{display:block;margin-top:11px;padding:9px;border:1px solid #294c67;border-radius:8px;text-align:center;color:#81b8e7;font-size:8px;font-weight:900}.list{display:grid;gap:8px;padding:12px}.listitem{display:grid;grid-template-columns:100px 1fr auto;gap:12px;align-items:center;padding:12px;border:1px solid #1b3044;border-radius:10px;background:#08131e}.listitem .num{font-size:8px;color:var(--gold);font-weight:900}.listitem .title{font-size:11px;font-weight:900}.listitem .sub{display:block;color:#6e8397;font-size:8px;margin-top:4px}.pill{padding:5px 8px;border-radius:6px;font-size:7px;font-weight:900;background:#153b2e;color:#79ddb1}.pill.pending{background:#3c2e12;color:#e7c86e}.module-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px}.module{padding:18px;border:1px solid var(--line);border-radius:14px;background:linear-gradient(145deg,#0b1622,#07101a)}.module .icon{font-size:20px}.module h3{margin:10px 0 6px;font-size:12px}.module p{margin:0;color:#70869b;font-size:9px;line-height:1.6}.module a{display:block;margin-top:14px;padding:10px;border-radius:8px;background:#10243a;color:#d8bc66;text-align:center;font-size:8px;font-weight:900}.detail{display:grid;grid-template-columns:minmax(250px,360px) 1fr;gap:16px;margin-top:15px}.detail-photo{border:1px solid var(--line);border-radius:15px;background:#05090e;overflow:hidden;min-height:420px}.detail-photo img{width:100%;height:100%;object-fit:cover}.detail-panel{border:1px solid var(--line);border-radius:15px;background:#07111a;padding:20px}.detail-panel h2{margin:0 0 18px;font-size:24px}.detail-row{padding:11px 0;border-bottom:1px solid #17293a}.detail-row:last-child{border-bottom:0}.detail-row b{display:block;color:#607b92;font-size:8px;letter-spacing:1px;margin-bottom:4px}.detail-row span{font-size:11px;color:#d5dfe6;line-height:1.5}.photo-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;padding:12px}.photo-card{border:1px solid var(--line);border-radius:11px;overflow:hidden;background:#07101a}.photo-card img{width:100%;height:165px;object-fit:cover;display:block}.photo-card .pbody{padding:10px}.stable{font-size:7px;color:#6f879d;word-break:break-all;margin-top:6px}.upload{padding:14px;border:1px dashed #365674;border-radius:12px;background:#091520;margin-top:12px}.upload input{width:100%;color:#b7c5d0;font-size:10px}.footer{text-align:center;color:#41566a;font-size:7px;margin-top:18px}.mobile-nav{display:none}
@media(max-width:1150px){.sidebar{width:215px}.grid4{grid-template-columns:repeat(3,1fr)}.photo-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:850px){.shell{display:block}.sidebar{display:none}.mobile-nav{display:flex;position:sticky;top:0;z-index:20;background:#07111b;border-bottom:1px solid var(--line);padding:10px;gap:7px;overflow:auto}.mobile-nav a{white-space:nowrap;padding:9px 11px;border:1px solid #1b3348;border-radius:9px;font-size:8px;font-weight:900;color:#8194a6}.content{padding:12px}.grid4,.photo-grid{grid-template-columns:repeat(2,1fr)}.stats{grid-template-columns:repeat(2,1fr)}.module-grid{grid-template-columns:repeat(2,1fr)}.detail{grid-template-columns:1fr}.detail-photo{min-height:330px}.topbar{align-items:flex-start}.operator{font-size:7px}}
@media(max-width:520px){.grid4,.grid2,.photo-grid,.module-grid{grid-template-columns:1fr}.hero{padding:20px}.hero h1{font-size:29px}.toolbar{flex-direction:column}.btn{width:100%}.listitem{grid-template-columns:1fr}.detail-panel h2{font-size:20px}}
'''


def shell(title: str, qra: str, passport: str, active: str, inner: str) -> str:
    links = [("/", "PAINEL", "home"), ("/procurados", "PROCURADOS", "wanted"), ("/boletins", "BOLETINS", "bo"), ("/pericias", "PERÍCIAS", "pe"), ("/fotos", "FOTOS", "photos"), ("/fichas", "BANCO DE DADOS", "db")]
    nav = "".join(f'<a class="{\'active\' if active==key else \'\'}" href="{url}">{label}</a>' for url,label,key in links)
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{CSS}</style></head><body><div class="mobile-nav">{nav}</div><div class="shell"><aside class="sidebar"><div class="brand">{base.img(base.DICOR_LOGO,"","DICOR")}<div><b>DICOR</b><small>INTELLIGENCE</small></div></div><nav class="nav">{nav}</nav><div class="sidebar-foot">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<br><br>SISTEMA INTERNO DE INTELIGÊNCIA<br>CONEXÃO DISCORD ATIVA</div></aside><main class="content"><header class="topbar"><div class="system-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="dot"></i>{esc(qra)} • {esc(passport)}</div></header>{inner}<div class="footer">DICOR • CENTRAL DE INTELIGÊNCIA • SISTEMA OPERACIONAL</div></main></div></body></html>'''


def rows_cards(rows: list[dict[str,Any]], limit: int | None = None) -> str:
    subset = rows[:limit] if limit else rows
    out=[]
    for r in subset:
        image=esc(r.get("image") or "")
        photo=f'<img src="{image}" alt="" loading="lazy">' if image else '<div style="display:grid;place-items:center;height:100%;color:#51697e;font-size:10px">SEM FOTO</div>'
        out.append(f'''<article class="card"><div class="photo">{photo}</div><div class="body"><span class="tag">PROCURADO</span><div class="name">{esc(r.get("name"))}</div><div class="meta">RG/PASSAPORTE: {esc(r.get("rg"))}<br>CRIMES: {esc(r.get("crime"))}<br>ÚLTIMO AVISTAMENTO: {esc(r.get("last_seen"))}</div><a class="linkbtn" href="/procurado/{esc(r.get("source_id"))}">ABRIR FICHA COMPLETA →</a></div></article>''')
    return "".join(out) or '<div class="empty">Nenhum registro ativo encontrado.</div>'


def dashboard(rows, qra, passport):
    total=len(rows); featured=sorted(rows,key=lambda r:r.get("penalty_months",0),reverse=True)[:2]
    body=f'''<section class="hero"><div class="eyebrow">CENTRAL DICOR • MONITORAMENTO PRINCIPAL</div><h1>PROCURADOS</h1><p>Monitoramento prioritário e consulta rápida dos registros ativos integrados ao Discord.</p><div class="toolbar"><input class="search" placeholder="Pesquisar por nome, RG ou passaporte..." disabled><a class="btn blue" style="display:grid;place-items:center" href="/procurados">CONSULTAR BASE COMPLETA</a></div></section><section class="stats"><div class="stat blue"><span>PROCURADOS ATIVOS</span><b>{total}</b></div><div class="stat red"><span>EM DESTAQUE</span><b>{len(featured)}</b></div><div class="stat gold"><span>INTEGRAÇÃO</span><b>ONLINE</b></div><div class="stat"><span>ATUALIZAÇÃO</span><b style="font-size:14px">{datetime.now().strftime("%H:%M")}</b></div></section><section class="section"><div class="section-head"><b>MAIORES PENAS • DESTAQUE</b><span>2 REGISTROS PRIORITÁRIOS</span></div><div class="grid2">{rows_cards(featured)}</div></section><section class="section"><div class="section-head"><b>ACESSO RÁPIDO</b><span>MODULOS DA CENTRAL</span></div><div class="module-grid" style="padding:12px"><article class="module"><div class="icon">👤</div><h3>Procurados</h3><p>Consulta completa, pesquisa e fichas individuais.</p><a href="/procurados">ABRIR</a></article><article class="module"><div class="icon">📋</div><h3>Boletins</h3><p>Acompanhe os atendimentos recebidos do Discord.</p><a href="/boletins">ABRIR</a></article><article class="module"><div class="icon">🧪</div><h3>Perícias</h3><p>Visualize as perícias externas em andamento.</p><a href="/pericias">ABRIR</a></article><article class="module"><div class="icon">📸</div><h3>Fotos</h3><p>Envio e hospedagem de imagens com link direto.</p><a href="/fotos">ABRIR</a></article></div></section>'''
    return shell("DICOR • Painel",qra,passport,"home",body)


def list_page(title, subtitle, items, qra, passport, active, kind):
    content=[]
    for r in items:
        status="EM ABERTO" if kind=="bo" else "PENDENTE"
        href="#"
        # BO/Perícia: mantém consulta no painel, sem navegação automática para o Discord.
        content.append(f'''<article class="listitem"><div class="num">Nº {esc(r.get("number"))}</div><div><div class="title">{esc(r.get("name"))}</div><span class="sub">Criado em {esc(r.get("created"))}</span></div><span class="pill {'pending' if kind=="pe" else ''}">{status}</span></article>''')
    inner=f'''<section class="hero"><div class="eyebrow">CENTRAL DICOR • {active.upper()}</div><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></section><section class="section"><div class="section-head"><b>REGISTROS DISPONÍVEIS</b><span>{len(items)} REGISTRO(S)</span></div><div class="list">{"".join(content) or '<div class="empty">Nenhum registro disponível no momento.</div>'}</div></section>'''
    return shell("DICOR • "+title,qra,passport,active,inner)


def funcs(qra, passport):
    inner='''<section class="hero"><div class="eyebrow">CENTRAL DICOR • AMBIENTE OPERACIONAL</div><h1>FUNCIONALIDADES</h1><p>Todos os módulos da Central organizados em um único painel.</p></section><div class="module-grid">'''
    mods=[("👤","Procurados","Pesquisa, fichas e monitoramento.","/procurados"),("📋","Boletins","Acompanhamento de atendimentos.","/boletins"),("🧪","Perícias","Controle das perícias externas.","/pericias"),("📸","Fotos","Arquivos e links diretos.","/fotos"),("🗄️","Banco de dados","Módulos de consulta.","/fichas"),("🌐","Painel principal","Voltar ao monitoramento.","/")]
    for i,n,d,u in mods: inner+=f'<article class="module"><div class="icon">{i}</div><h3>{n}</h3><p>{d}</p><a href="{u}">ACESSAR MÓDULO →</a></article>'
    inner+='</div>'
    return shell("DICOR • Funcionalidades",qra,passport,"db",inner)


def detail(row,qra,passport):
    image=esc(row.get("image") or "")
    photo=f'<img src="{image}" alt="Foto do procurado">' if image else '<div style="height:100%;display:grid;place-items:center;color:#536a7e">SEM FOTO DISPONÍVEL</div>'
    inner=f'''<section class="hero"><div class="eyebrow">CENTRAL DICOR • REGISTRO INDIVIDUAL</div><h1>FICHA DO PROCURADO</h1><p>Consulta interna do registro selecionado.</p></section><section class="detail"><div class="detail-photo">{photo}</div><div class="detail-panel"><span class="tag">PROCURADO ATIVO</span><h2>{esc(row.get("name"))}</h2><div class="detail-row"><b>RG / PASSAPORTE</b><span>{esc(row.get("rg"))}</span></div><div class="detail-row"><b>CRIMES</b><span>{esc(row.get("crime"))}</span></div><div class="detail-row"><b>ÚLTIMO AVISTAMENTO</b><span>{esc(row.get("last_seen"))}</span></div><div class="detail-row"><b>PENA</b><span>{esc(row.get("penalty_months",0))} meses</span></div><div class="detail-row"><b>REGISTRO</b><span>Nº {esc(row.get("number"))}</span></div><a class="btn blue" style="display:inline-grid;place-items:center;margin-top:17px" href="/procurados">← VOLTAR PARA PROCURADOS</a></div></section>'''
    return shell("DICOR • Ficha",qra,passport,"wanted",inner)


def install(bot_module: Any):
    # V625 preserva toda a lógica funcional. Apenas substituímos os renderers.
    base.dashboard = dashboard
    base.functionalities = funcs
    original_listing = base.listing
    def listing_626(title, subtitle, rows, qra, kind):
        passport = ""
        return list_page(title, subtitle, rows, qra, passport, "bo" if kind=="bo" else "pe", kind)
    base.listing = listing_626

    # As rotas extras continuam sendo instaladas pela V625.
    # Para a listagem completa de Procurados, reaproveitamos sua função existente,
    # mas com o layout atual da Central.
    original_all = v625.all_procurados
    async def all_procurados_626(req):
        session = base.read_session(req)
        if not session:
            raise base.web.HTTPFound("/cadastro-operador?next=/procurados")
        qra, passport = session
        rows = await v625.collect_procurados(v625._CLIENT)
        q = str(req.query.get("q","")).strip().casefold()
        if q:
            rows=[r for r in rows if q in str(r.get("name","")).casefold() or q in str(r.get("rg","")).casefold() or q in str(r.get("crime","")).casefold()]
        cards=rows_cards(sorted(rows,key=lambda r:r.get("penalty_months",0),reverse=True))
        inner=f'''<section class="hero"><div class="eyebrow">CENTRAL DICOR • BASE COMPLETA</div><h1>PROCURADOS</h1><p>Todos os registros ativos em uma única tela.</p><form class="toolbar" method="get" action="/procurados"><input class="search" name="q" value="{esc(req.query.get("q",""))}" placeholder="Pesquisar por nome, RG ou passaporte"><button class="btn blue" type="submit">PESQUISAR</button></form></section><section class="section"><div class="section-head"><b>TODOS OS PROCURADOS</b><span>{len(rows)} REGISTRO(S)</span></div><div class="grid2">{cards}</div></section>'''
        return base.web.Response(text=shell("DICOR • Procurados",qra,passport,"wanted",inner),content_type="text/html")
    v625.all_procurados = all_procurados_626

    # Detail interno segue a mesma identidade visual.
    async def detail_626(req):
        session=base.read_session(req)
        if not session: raise base.web.HTTPFound("/cadastro-operador?next="+req.path)
        qra,passport=session; rid=str(req.match_info.get("source_id","")); rows=base.CACHE.get("procurados",[])
        row=next((r for r in rows if str(r.get("source_id"))==rid),None)
        if row is None:
            fresh=await v625.collect_procurados(v625._CLIENT); row=next((r for r in fresh if str(r.get("source_id"))==rid),None)
        if row is None: raise base.web.HTTPNotFound(text="Registro não encontrado.")
        return base.web.Response(text=detail(row,qra,passport),content_type="text/html")
    v622.detail_route = detail_626
    v625.v624.v622.detail_route = detail_626
    return v625.install(bot_module)
