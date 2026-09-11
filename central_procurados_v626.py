# -*- coding: utf-8 -*-
"""Central DICOR V626 - Procurados reconstruído."""
from __future__ import annotations
import html
from typing import Any
import central_discord_v613 as base
import central_procurados_v625 as v625

_CLIENT: Any = None
collect_procurados = v625.collect_procurados

CSS = r'''
:root{--bg:#04080d;--panel:#09131f;--line:#1b344b;--line2:#294b68;--gold:#d7ae4e;--gold2:#f0d37a;--text:#eef3f7;--muted:#7e93a7}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;background:radial-gradient(circle at 50% -10%,#173c60 0,#091522 34%,#04080d 75%);color:var(--text)}a{text-decoration:none;color:inherit}button,input{font:inherit}
.app{min-height:100vh}.main{width:min(1380px,calc(100% - 34px));margin:auto;padding:22px 0 50px}.top{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:15px 18px;border:1px solid var(--line);border-radius:16px;background:#07111cf2;box-shadow:0 18px 55px #0008;position:sticky;top:12px;z-index:5;backdrop-filter:blur(12px)}.pcpt-title{font-size:12px;font-weight:950;letter-spacing:1.6px}.pcpt-title span{display:block;color:var(--gold);font-size:9px;letter-spacing:2px;margin-top:5px}.operator{font-size:9px;color:#91a6ba;white-space:nowrap}.online{display:inline-block;width:7px;height:7px;border-radius:50%;background:#55c27a;box-shadow:0 0 10px #55c27a}
.tabs{display:flex;gap:8px;margin:18px 0 0}.tab{padding:11px 18px;border:1px solid var(--line);border-radius:10px;background:#08131f;color:#8298ab;font-size:9px;font-weight:950;letter-spacing:1.3px}.tab.active{border-color:#8b6d2e;background:linear-gradient(135deg,#1a2e40,#0b1724);color:var(--gold2)}
.hero{margin-top:14px;padding:32px;border:1px solid var(--line);border-radius:20px;background:linear-gradient(135deg,#0c1b2a,#07111b);box-shadow:0 25px 70px #0006}.eyebrow{font-size:9px;color:var(--gold);font-weight:950;letter-spacing:2px}.hero h1{font-size:36px;margin:8px 0}.hero p{max-width:800px;color:var(--muted);font-size:12px;line-height:1.7;margin:0}.search{display:flex;gap:10px;margin-top:23px}.search input{height:48px;flex:1;min-width:0;background:#050c14;border:1px solid var(--line2);border-radius:11px;color:var(--text);padding:0 15px;outline:none}.search button{height:48px;border:0;border-radius:11px;padding:0 23px;background:linear-gradient(135deg,#f0d06c,#a8791c);color:#080b0e;font-weight:950;font-size:9px;letter-spacing:1px;cursor:pointer}
.section-head{display:flex;justify-content:space-between;align-items:center;margin:25px 2px 12px}.section-head b{font-size:11px;letter-spacing:1.5px}.count{font-size:9px;color:#748ba0}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.card{display:flex;flex-direction:column;border:1px solid var(--line);border-radius:18px;overflow:hidden;background:linear-gradient(160deg,#0a1622,#06101a);box-shadow:0 15px 45px #0006;transition:.18s}.card:hover{transform:translateY(-3px);border-color:#3d6482}.photo{height:265px;background:#03070b;display:grid;place-items:center;position:relative;overflow:hidden}.photo img{width:100%;height:100%;object-fit:cover}.tag{position:absolute;left:12px;top:12px;padding:7px 9px;border-radius:8px;background:#05090dcc;border:1px solid #d7ae4e55;color:var(--gold2);font-size:8px;font-weight:950;letter-spacing:1px}.no-photo{font-size:9px;font-weight:950;color:#536b80;letter-spacing:1px}.card-body{padding:18px}.name{font-size:20px;font-weight:950;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.subid{font-size:9px;color:var(--gold);margin-top:4px;font-weight:850;letter-spacing:.8px}.data{margin-top:17px;display:grid;gap:12px}.data-item label{display:block;color:#607a91;font-size:8px;font-weight:950;letter-spacing:1.2px;margin-bottom:4px}.data-item span{display:block;color:#c7d2dc;font-size:11px;line-height:1.45;overflow-wrap:anywhere}.status{display:inline-flex;padding:5px 8px;border:1px solid #3b6d4d;background:#102319;color:#86d49a;border-radius:7px;font-size:8px;font-weight:950}.open{margin-top:18px;padding:12px;border-radius:10px;background:#10283c;border:1px solid #234b69;color:#d5e1ea;text-align:center;font-size:8px;font-weight:950;letter-spacing:1.1px}.empty{padding:40px;text-align:center;border:1px dashed #29445c;border-radius:15px;color:#71869b;font-size:11px}
.detail{margin-top:18px;display:grid;grid-template-columns:420px 1fr;gap:18px}.detail-photo{min-height:560px;border:1px solid var(--line);border-radius:20px;overflow:hidden;background:#03070b;display:grid;place-items:center}.detail-photo img{width:100%;height:100%;min-height:560px;object-fit:cover;cursor:zoom-in}.detail-panel{border:1px solid var(--line);border-radius:20px;background:linear-gradient(155deg,#0b1825,#07101a);padding:28px}.detail-panel h1{font-size:32px;margin:5px 0 8px}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:25px}.box{padding:15px;border:1px solid var(--line);border-radius:12px;background:#07111b}.box.full{grid-column:1/-1}.box label{display:block;color:#668199;font-size:8px;font-weight:950;letter-spacing:1.1px;margin-bottom:6px}.box div{font-size:12px;color:#d2dbe3;line-height:1.55;overflow-wrap:anywhere}.actions{display:flex;gap:10px;margin-top:22px}.action{flex:1;padding:13px;border-radius:10px;text-align:center;border:1px solid var(--line2);background:#10283c;color:#d7e4ed;font-size:8px;font-weight:950;letter-spacing:1px}.action.gold{background:linear-gradient(135deg,#efd06d,#a97a20);border:0;color:#090b0d}
@media(max-width:1050px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.detail{grid-template-columns:330px 1fr}}@media(max-width:760px){.main{width:min(100% - 20px,680px);padding-top:10px}.top{position:relative;top:0}.operator{display:none}.hero{padding:23px}.hero h1{font-size:28px}.grid{grid-template-columns:1fr}.photo{height:290px}.detail{grid-template-columns:1fr}.detail-photo{min-height:420px}.detail-photo img{min-height:420px}.detail-grid{grid-template-columns:1fr}.box.full{grid-column:auto}.actions,.search{flex-direction:column}.search button{width:100%}}
'''

def esc(v:Any)->str:return html.escape(str(v or ""),quote=True)
def clean(v:Any, fallback="Não informado")->str:
    x=str(v or "").strip(); return x if x else fallback

def header(qra,passport):
    return f'<header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i> {esc(qra)} • PASSAPORTE {esc(passport)}</div></header>'

def nav(active):
    return f'<nav class="tabs"><a class="tab {"active" if active=="procurados" else ""}" href="/procurados">PROCURADOS</a><a class="tab {"active" if active=="fotos" else ""}" href="/fotos">BANCO DE FOTOS</a><a class="tab" href="/">CENTRAL</a></nav>'

def card(r):
    name=clean(r.get("name"),"Indivíduo não identificado"); rg=clean(r.get("rg")); crime=clean(r.get("crime")); seen=clean(r.get("last_seen")); status=clean(r.get("status"),"ATIVO").upper(); sid=esc(r.get("source_id")); image=r.get("image") or ""
    visual=f'<img src="{esc(image)}" alt="Foto de {esc(name)}" loading="lazy">' if image else '<div class="no-photo">SEM FOTO DISPONÍVEL</div>'
    return f'<a class="card" href="/procurado/{sid}"><div class="photo">{visual}<span class="tag">PROCURADO</span></div><div class="card-body"><div class="name" title="{esc(name)}">{esc(name)}</div><div class="subid">RG / PASSAPORTE: {esc(rg)}</div><div class="data"><div class="data-item"><label>CRIMES</label><span>{esc(crime)}</span></div><div class="data-item"><label>ÚLTIMO AVISTAMENTO</label><span>{esc(seen)}</span></div><div class="data-item"><label>SITUAÇÃO</label><span class="status">{esc(status)}</span></div></div><div class="open">ABRIR REGISTRO COMPLETO →</div></div></a>'

async def procurados_page(req):
    session=base.read_session(req)
    if not session: raise base.web.HTTPFound('/cadastro-operador?next=/procurados')
    qra,passport=session; rows=await collect_procurados(_CLIENT); query=str(req.query.get('q','')).strip().casefold()
    if query: rows=[r for r in rows if query in str(r.get('name','')).casefold() or query in str(r.get('rg','')).casefold() or query in str(r.get('crime','')).casefold()]
    cards=''.join(card(r) for r in rows) or '<div class="empty">Nenhum procurado encontrado para esta pesquisa.</div>'
    body=f'<div class="app"><main class="main">{header(qra,passport)}{nav("procurados")}<section class="hero"><div class="eyebrow">DICOR • BANCO OPERACIONAL</div><h1>PROCURADOS</h1><p>Todos os registros ativos em uma única consulta. Pesquise por nome, RG ou crime e abra qualquer ficha para visualizar os dados completos.</p><form class="search" method="get" action="/procurados"><input name="q" value="{esc(req.query.get("q",""))}" placeholder="Pesquisar por nome, RG ou crime"><button type="submit">PESQUISAR</button></form></section><div class="section-head"><b>REGISTROS ATIVOS</b><span class="count">{len(rows)} REGISTRO(S) ENCONTRADO(S)</span></div><section class="grid">{cards}</section></main></div>'
    return base.web.Response(text=base.page('DICOR • Procurados',body,CSS),content_type='text/html')

async def detail_page(req):
    session=base.read_session(req)
    if not session: raise base.web.HTTPFound('/cadastro-operador?next='+req.path)
    qra,passport=session
    try: sid=int(req.match_info.get('source_id','0'))
    except Exception: raise base.web.HTTPNotFound()
    rows=await collect_procurados(_CLIENT); row=next((r for r in rows if int(r.get('source_id') or 0)==sid),None)
    if not row:
        body=f'<div class="app"><main class="main">{header(qra,passport)}{nav("procurados")}<section class="hero"><div class="eyebrow">REGISTRO NÃO LOCALIZADO</div><h1>PROCURADO NÃO ENCONTRADO</h1><p>O registro não está disponível na consulta atual.</p><div class="actions"><a class="action gold" href="/procurados">VOLTAR A PROCURADOS</a></div></section></main></div>'
        return base.web.Response(text=base.page('DICOR • Registro',body,CSS),status=404,content_type='text/html')
    name=clean(row.get('name'),'Indivíduo não identificado'); image=row.get('image') or ''; visual=f'<img id="mainPhoto" src="{esc(image)}" alt="Foto de {esc(name)}" onclick="this.classList.toggle(\'zoom\')">' if image else '<div class="no-photo">SEM FOTO DISPONÍVEL</div>'
    body=f'<div class="app"><main class="main">{header(qra,passport)}{nav("procurados")}<div class="detail"><div class="detail-photo">{visual}</div><section class="detail-panel"><div class="eyebrow">DICOR • REGISTRO INDIVIDUAL</div><h1>{esc(name)}</h1><div class="status">{esc(clean(row.get("status"),"ATIVO").upper())}</div><div class="detail-grid"><div class="box"><label>RG / PASSAPORTE</label><div>{esc(clean(row.get("rg")))}</div></div><div class="box"><label>NÚMERO DO REGISTRO</label><div>{esc(clean(row.get("number")))}</div></div><div class="box full"><label>CRIMES</label><div>{esc(clean(row.get("crime")))}</div></div><div class="box full"><label>ÚLTIMO AVISTAMENTO / LOCALIZAÇÃO</label><div>{esc(clean(row.get("last_seen")))}</div></div><div class="box full"><label>INFORMAÇÕES DO REGISTRO</label><div>{esc(clean(row.get("preview"),"Sem informações adicionais."))}</div></div></div><div class="actions"><a class="action gold" href="/procurados">← VOLTAR</a><a class="action" href="{esc(row.get("url","#"))}" target="_blank" rel="noopener">ABRIR ORIGEM</a></div></section></div></main></div><style>.zoom{position:fixed!important;z-index:100;inset:4vh 4vw;width:92vw!important;height:92vh!important;object-fit:contain!important;background:#000!important;cursor:zoom-out!important;border:1px solid #d7ae4e55}</style>'
    return base.web.Response(text=base.page('DICOR • '+name,body,CSS),content_type='text/html')

class ApplicationPatch(base.web.Application):
    def __init__(self,*args,**kwargs):
        kwargs['client_max_size']=12*1024*1024; super().__init__(*args,**kwargs)
        self.router.add_get('/procurados',procurados_page,name='v626_procurados')
        self.router.add_get('/procurado/{source_id}',detail_page,name='v626_detail')
        self.router.add_get('/imagem-procurado/{message_id}',v625.v624.v622.procurado_photo,name='v626_wanted_photo')
        self.router.add_get('/fotos',v625.v624.v622.photos_page,name='v626_photos')
        self.router.add_get('/foto/{message_id}',v625.v624.v622.stable_photo,name='v626_stable_photo')
        self.router.add_post('/fotos/upload',v625.upload_photo,name='v626_upload')

async def start_server_v626(client):
    global _CLIENT
    _CLIENT=client; v625._CLIENT=client; v625.v624.v622._CLIENT=client
    original=base.web.Application; base.web.Application=ApplicationPatch
    try:return await v625._ORIGINAL_START(client)
    finally:base.web.Application=original

def install(bot_module):return base.install(bot_module)
