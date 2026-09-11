# -*- coding: utf-8 -*-
"""DICOR Central V704 - interface final, procurados limpos e perfil administrativo."""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
from urllib.parse import quote

import central_home_v700 as v700

BRAND_LINE = "PCPT POLICIA MORADA - POLICIA FEDERAL"
REAL_DICOR_LOGO = str(os.getenv("DICOR_LOGO_URL") or getattr(getattr(v700, "source", None), "DICOR_LOGO", "") or v700.LOGO).strip()
RECOVERY_MARKERS = ("recuperação assistida","recuperacao assistida","recuperação automática","recuperacao automatica","v112","canal foi encontrado","tarefa pendente","tarefa concluída","tarefa concluida","registre no painel","recuperação órf","recuperacao orf")

CSS_704 = r"""
:root{--bg:#02070c;--panel:#0a1722;--line:#294355;--gold:#e2bd5b;--gold2:#f2d477;--blue:#53a9df;--text:#f4f7f9;--muted:#9babb6}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:radial-gradient(circle at 78% 0,#123b55 0,transparent 29%),radial-gradient(circle at 10% 0,#132638 0,transparent 22%),#02070c;color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}body{overflow-x:hidden}a{text-decoration:none;color:inherit}button,input{font:inherit}
.top{position:sticky;top:0;z-index:50;min-height:86px;border-bottom:1px solid #263f50;background:rgba(2,8,13,.97);backdrop-filter:blur(20px)}.top-inner{width:min(1460px,calc(100% - 48px));min-height:86px;margin:auto;display:flex;align-items:center;gap:28px}.brand{display:flex;align-items:center;gap:14px;min-width:420px}.brand img{width:56px;height:56px;object-fit:contain;filter:drop-shadow(0 8px 18px #000b)}.brand-text b{display:block;font-size:15px;letter-spacing:1.8px;line-height:1.15}.brand-text span{display:block;color:var(--gold2);font-size:9px;font-weight:900;letter-spacing:2.5px;margin-top:6px}.nav{display:flex;align-items:center;gap:20px;margin-left:auto}.nav a{color:#a0b1bd;font-size:10px;font-weight:900;letter-spacing:1.1px;white-space:nowrap}.nav a:hover{color:#fff}.top-actions{display:flex;align-items:center;gap:11px}.user-mini{display:flex;align-items:center;gap:9px}.user-avatar{width:34px;height:34px;border-radius:50%;border:1px solid #3c5e73;object-fit:cover;background:#07131d}.user-mini b{font-size:10px;display:block}.user-mini small{display:block;color:#728899;font-size:8px;margin-top:2px}.logout{border:1px solid #2b4659;background:#081722;color:#b8c5cd;border-radius:8px;padding:8px 11px;font-size:8px;font-weight:900;cursor:pointer}
.wrap{width:min(1160px,calc(100% - 44px));margin:auto;padding:40px 0 70px}.panel{border:1px solid var(--line);border-radius:20px;background:linear-gradient(145deg,rgba(10,23,34,.98),rgba(4,12,18,.99));box-shadow:0 25px 80px #0009}.hero{display:grid;grid-template-columns:1.05fr .95fr;gap:20px}.hero-copy{padding:55px 50px 50px}.kicker{color:var(--blue);font-size:10px;font-weight:900;letter-spacing:2.7px}.hero-copy h1{font-family:Georgia,"Times New Roman",serif;font-size:57px;line-height:1.04;font-weight:500;margin:16px 0 20px}.hero-copy h1 span{color:var(--gold2)}.hero-copy p{color:#a9b5bd;font-size:14px;line-height:1.85;margin:0;max-width:650px}.operator-line{margin-top:26px;color:var(--gold2);font-size:11px;font-weight:900;letter-spacing:1.1px;text-transform:uppercase}.hero-mark{min-height:360px;display:grid;place-items:center;position:relative;overflow:hidden;background:radial-gradient(circle,#15425d 0,#0b2231 42%,#061019 80%)}.hero-mark:before{content:"";position:absolute;width:275px;height:275px;border:1px solid #59b1e259;border-radius:50%;box-shadow:0 0 0 38px #59b1e20b,0 0 0 76px #59b1e205,0 0 60px #2d91c828}.hero-mark img{position:relative;width:220px;height:220px;object-fit:contain;filter:drop-shadow(0 20px 35px #000c)}
.section-head{margin:35px 0 14px}.section-head .kicker{display:block}.section-head h2{font-size:22px;letter-spacing:1.2px;margin:6px 0}.search-panel{padding:18px;margin-bottom:18px}.search-form{display:flex;gap:12px}.search-form input{flex:1;height:50px;border:1px solid #2a475a;border-radius:10px;background:#06121b;color:#eef3f7;padding:0 15px;font-size:14px;outline:none}.search-form input:focus{border-color:var(--gold2);box-shadow:0 0 0 3px #d7b84a22}.btn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 17px;border:1px solid #35576f;border-radius:9px;background:#0a1c2a;color:#dce8ef;font-size:10px;font-weight:950;letter-spacing:.8px}.btn.gold{border:0;background:linear-gradient(135deg,#f2d476,#a77515);color:#090b0c;box-shadow:0 10px 24px #0008}.btn.block{width:100%}
.wanted-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.wanted-card{overflow:hidden;border:1px solid #28475a;border-radius:17px;background:linear-gradient(160deg,#091823,#050e15)}.wanted-photo{height:290px;background:#03090d;display:grid;place-items:center;position:relative;overflow:hidden}.wanted-photo img{width:100%;height:100%;object-fit:cover}.wanted-photo.no-image{background:radial-gradient(circle,#122536,#03090d)}.wanted-photo.no-image:after{content:"DICOR";color:#5b7789;font-size:24px;font-weight:900;letter-spacing:3px}.wanted-tag{position:absolute;left:12px;top:12px;padding:7px 9px;border:1px solid #daba5759;border-radius:7px;background:#030a0fcf;color:#f0d47a;font-size:8px;font-weight:950;letter-spacing:1px}.wanted-body{padding:18px}.wanted-name{font-size:19px;font-weight:950;line-height:1.2}.wanted-id{margin-top:5px;color:var(--gold2);font-size:10px;font-weight:900;letter-spacing:1px}.info-grid{display:grid;gap:9px;margin-top:15px}.info{padding-top:9px;border-top:1px solid #173247}.info label{display:block;color:#648194;font-size:8px;font-weight:900;letter-spacing:1.2px}.info b{display:block;margin-top:4px;color:#e6edf1;font-size:11px;line-height:1.4}.wanted-open{margin-top:14px}.access-card{display:flex;align-items:center;justify-content:space-between;gap:25px;margin-top:20px;padding:22px 24px;border:1px solid #8a6a27;border-radius:16px;background:linear-gradient(105deg,#17150f,#09131c)}.access-card strong{display:block;color:#f0d276;font-size:17px}.access-card small{display:block;color:#948a70;font-size:10px;margin-top:6px}.footer{text-align:center;border-top:1px solid #173043;color:#516b7b;font-size:8px;padding:18px}
.restricted-head{padding:36px 38px}.restricted-head h1{font-size:42px;margin:10px 0 8px}.restricted-head p{color:#9aabb6;font-size:13px}.restricted-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:17px;padding:0 38px 38px}.module-card{padding:22px;border:1px solid #2b485b;border-radius:16px;background:linear-gradient(155deg,#0b1b27,#07111a);min-height:190px;display:flex;flex-direction:column}.module-icon{font-size:22px;color:var(--gold2)}.module-card h3{font-size:19px;margin:15px 0 8px}.module-card p{color:#879ba9;font-size:12px;line-height:1.65;margin:0}.module-card .btn{margin-top:auto}
.page-heading{padding:32px 36px 20px}.page-heading h1{font-size:39px;margin:8px 0}.page-heading p{color:#90a4b1;font-size:13px;margin:0}.records{padding:0 36px 36px;display:grid;gap:16px}.record{border:1px solid #294558;border-radius:16px;background:linear-gradient(155deg,#0a1925,#061019);padding:21px}.record-head{display:flex;justify-content:space-between;align-items:start;gap:15px}.record-head h3{font-size:18px;margin:0}.source-tag{padding:6px 8px;border:1px solid #31566d;border-radius:999px;color:#9bc6df;background:#081722;font-size:8px;font-weight:900}.record-meta{color:#687f8f;font-size:9px;margin-top:7px}.record-fields{display:grid;grid-template-columns:repeat(2,1fr);gap:11px;margin-top:16px}.record-field{padding:11px 12px;border:1px solid #1b3446;border-radius:10px;background:#07131d}.record-field label{display:block;color:#668194;font-size:8px;font-weight:900;letter-spacing:1px}.record-field div{margin-top:5px;color:#dce5ea;font-size:11px;line-height:1.5}.record-actions{display:flex;gap:10px;margin-top:16px}
.detail{padding:34px}.detail-head h1{font-size:38px;margin:5px 0}.detail-sub{color:#728897;font-size:10px}.detail-photo{margin-top:20px;max-width:430px;max-height:400px;border-radius:14px;border:1px solid #274458;object-fit:cover}.detail-fields{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:22px}.detail-field{padding:14px;border:1px solid #213b4d;border-radius:11px;background:#07131d}.detail-field label{color:#648092;font-size:8px;font-weight:900;letter-spacing:1.2px}.detail-field div{margin-top:6px;font-size:12px;line-height:1.6}.full-text{margin-top:18px;padding:17px;border-left:2px solid var(--gold);background:#07121b;color:#aab7bf;font-size:11px;line-height:1.7;white-space:pre-wrap}.detail-actions{display:flex;gap:10px;margin-top:20px}
.photo-page{padding:36px}.photo-page h1{font-size:37px;margin:8px 0}.upload-box{margin-top:20px;padding:24px;border:1px dashed #46667b;border-radius:15px;background:#07141e}.upload-box input[type=file]{width:100%;padding:14px;border:1px solid #29465a;border-radius:10px;background:#06121b;color:#a9b8c2}.result-box{margin-top:18px;padding:18px;border:1px solid #2a475c;border-radius:13px;background:#07151f}.copy-row{display:flex;gap:10px}.copy-row input{flex:1;height:46px;border:1px solid #29475a;background:#06121b;color:#e6edf1;border-radius:9px;padding:0 12px}
.admin-hero{padding:35px 36px 22px}.admin-hero h1{font-size:39px;margin:8px 0}.admin-hero p{color:#93a5b0;font-size:12px}.admin-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:13px;padding:0 36px 20px}.admin-stat{padding:17px;border:1px solid #294559;border-radius:14px;background:#07131d}.admin-stat small{color:#688194;font-size:8px;letter-spacing:1.2px;font-weight:900}.admin-stat b{display:block;color:var(--gold2);font-size:28px;margin-top:7px}.user-list{display:grid;gap:14px;padding:0 36px 36px}.user-card{display:grid;grid-template-columns:auto 1fr 1fr 1.8fr;gap:18px;align-items:center;padding:17px;border:1px solid #294559;border-radius:15px;background:linear-gradient(155deg,#0a1824,#061019)}.profile-photo{width:64px;height:64px;border-radius:50%;border:1px solid #3e6073;object-fit:cover;background:#07141d}.user-card h3{font-size:15px;margin:0}.user-card small{display:block;color:#718799;font-size:8px;margin-top:5px}.status-pill{display:inline-flex;padding:5px 8px;border-radius:999px;font-size:8px;font-weight:900;margin:9px 5px 0 0}.online{background:#113b2e;border:1px solid #2d6a52;color:#9de5c6}.offline{background:#291318;border:1px solid #643139;color:#dca3a6}.authorized{background:#2f2711;border:1px solid #775f20;color:#f2d477}.blocked{background:#1d2931;border:1px solid #334c5c;color:#8fa4b2}.pending{background:#271f10;border:1px solid #6c5520;color:#e6ca73}.admin-form{display:grid;grid-template-columns:1fr 1fr 1.4fr auto;gap:8px;margin-top:10px}.admin-form input{height:40px;border:1px solid #274559;border-radius:8px;background:#06121b;color:#e8eef2;padding:0 10px;font-size:10px}.admin-form button{height:40px;border:0;border-radius:8px;background:linear-gradient(135deg,#eed06f,#a57313);font-size:9px;font-weight:900;color:#0b0d0f;padding:0 15px}
@media(max-width:1050px){.brand{min-width:320px}.hero{grid-template-columns:1fr}.wanted-grid{grid-template-columns:repeat(2,1fr)}.restricted-grid{grid-template-columns:repeat(2,1fr)}.user-card{grid-template-columns:auto 1fr}.admin-form{grid-template-columns:1fr 1fr 1fr}.admin-form button{grid-column:1/-1}}@media(max-width:720px){.top{min-height:75px}.top-inner{min-height:75px;flex-wrap:wrap;padding:10px 0}.brand{min-width:0;flex:1}.brand img{width:44px;height:44px}.brand-text b{font-size:11px}.nav{order:3;width:100%;overflow:auto;padding-bottom:2px;gap:16px}.wrap{width:calc(100% - 20px);padding:24px 0 45px}.hero-copy{padding:34px 25px}.hero-copy h1{font-size:41px}.hero-copy p{font-size:12px}.hero-mark{min-height:285px}.hero-mark img{width:170px;height:170px}.wanted-grid,.restricted-grid{grid-template-columns:1fr}.wanted-photo{height:255px}.search-form{flex-direction:column}.access-card{align-items:stretch;flex-direction:column}.restricted-head,.page-heading,.admin-hero,.photo-page,.detail{padding:27px 22px}.records,.user-list{padding:0 22px 28px}.record-fields,.detail-fields,.admin-stats{grid-template-columns:1fr}.admin-stats{padding:0 22px 20px}.user-card{grid-template-columns:auto 1fr}.admin-form{grid-template-columns:1fr}.admin-form button{grid-column:auto}}
"""

def _safe_logo():
    return REAL_DICOR_LOGO or v700.LOGO

def _shell(title,body,u=None,admin=False):
    profile=str((u or {}).get("foto_url") or _safe_logo())
    who=""
    if u:
        who=f'<div class="user-mini"><img class="user-avatar" src="{v700.esc(profile)}" alt="Perfil"><div><b>{v700.esc(u.get("nome") or u.get("qra"))}</b><small>PASSAPORTE {v700.esc(u.get("passaporte"))}</small></div></div><form method="post" action="/logout"><input type="hidden" name="csrf" value="{v700.esc(v700.csrf(u))}"><button class="logout">SAIR</button></form>'
    nav='<nav class="nav"><a href="/">CENTRAL</a><a href="/procurados">PROCURADOS</a><a href="/fotos">FOTOS</a></nav>'
    return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-store"><title>{v700.esc(title)}</title><style>{CSS_704}</style></head><body><header class="top"><div class="top-inner"><a class="brand" href="/"><img src="{v700.esc(_safe_logo())}" alt="DICOR"><div class="brand-text"><b>{BRAND_LINE}</b><span>DICOR</span></div></a>{nav}<div class="top-actions">{who}</div></div></header><main class="wrap">{body}</main><footer class="footer">{BRAND_LINE} • DICOR • CENTRAL DE INTELIGÊNCIA</footer><script>function cp(v,b){{if(navigator.clipboard){{navigator.clipboard.writeText(v).then(function(){{var t=b.innerText;b.innerText="COPIADO";setTimeout(function(){{b.innerText=t}},1000)}})}}}}</script></body></html>'

def _clean_name(name,fallback="Indivíduo não identificado"):
    n=v700.clean_source(name); low=n.casefold()
    if not n or any(m in low for m in RECOVERY_MARKERS): return fallback
    return n[:100]

def _valid_wanted(r):
    if not isinstance(r,dict): return False
    full=v700.clean_source(r.get("full_text") or r.get("preview") or r.get("content")); low=full.casefold()
    if any(x in low for x in RECOVERY_MARKERS): return False
    name=_clean_name(r.get("name") or "")
    return not (name=="Indivíduo não identificado" and not (r.get("image") or r.get("rg") or r.get("crime")))

def _wanted_row(r):
    full=v700.clean_source(r.get("full_text") or r.get("preview") or r.get("content")); name=_clean_name(r.get("name") or "")
    if name=="Indivíduo não identificado": name=v700.field(full,("nome","indivíduo","individuo","procurado","envolvido")) or name
    fs={"RG / Passaporte":r.get("rg") or v700.field(full,("rg","passaporte","rg/passaporte")),"Crimes":r.get("crime") or v700.field(full,("crime","crimes","acusação","acusacao")),"Localização":r.get("location") or r.get("last_seen") or v700.field(full,("localização","localizacao","local","último avistamento","ultimo avistamento")),"Situação":r.get("status") or v700.field(full,("status","situação","situacao"))}
    return {"id":str(r.get("id") or r.get("source_id") or hashlib.sha256(full.encode()).hexdigest()[:20]),"name":name,"number":v700.clean(r.get("number")) or v700.number(full),"image":str(r.get("image") or v700.img_url(full)),"url":str(r.get("url") or ""),"fields":{k:v700.clean_source(val) or "Não informado" for k,val in fs.items()},"full_text":full or "Sem informações adicionais.","source":str(r.get("source") or "DISCORD"),"date":str(r.get("created") or r.get("date") or "")}

def _merge_rows(primary,secondary):
    out=[]; by_key={}
    for row in list(primary or [])+list(secondary or []):
        if not isinstance(row,dict): continue
        key=v700.clean(row.get("id")) or (v700.clean(row.get("number"))+"|"+v700.clean(row.get("name"))).casefold(); old=by_key.get(key)
        if old is None:
            cp=dict(row); cp["fields"]=dict(row.get("fields") or {}); out.append(cp); by_key[key]=cp
        else:
            for k,val in (row.get("fields") or {}).items():
                if val and val!="Não informado": old.setdefault("fields",{})[k]=val
            for k in ("image","url","full_text","date","subject","number","name"):
                if not old.get(k) and row.get(k): old[k]=row.get(k)
    return out

async def _refresh_data():
    if v700.C["refreshing"]: return
    v700.C["refreshing"]=True
    try:
        client=v700.CLIENT
        if client and getattr(client,"is_ready",lambda:False)():
            try: await v700.source.refresh(client)
            except Exception: pass
        dw=[_wanted_row(r) for r in v700.source.CACHE.get("procurados",[]) if _valid_wanted(r)]
        db=[v700.discord_row("boletins",r) for r in v700.source.CACHE.get("bo",[]) if isinstance(r,dict)]
        dp=[v700.discord_row("pericias",r) for r in v700.source.CACHE.get("pericia",[]) if isinstance(r,dict)]
        try: dop=await v700.ops_discord()
        except Exception: dop=[]
        try: mail=await v700.poll_mail()
        except Exception: mail={x:[] for x in ("procurados","boletins","pericias","operacoes")}
        mw=[r for r in mail.get("procurados",[]) if isinstance(r,dict) and _valid_wanted(r)]
        v700.C["procurados"]=_merge_rows(dw,mw); v700.C["boletins"]=_merge_rows(db,mail.get("boletins",[])); v700.C["pericias"]=_merge_rows(dp,mail.get("pericias",[])); v700.C["operacoes"]=_merge_rows(dop,mail.get("operacoes",[])); v700.C["updated"]=__import__("time").time()
    except Exception as e: print(f"⚠️ [CENTRAL V704] refresh: {type(e).__name__}",flush=True)
    finally: v700.C["refreshing"]=False

def _home(u):
    wanted=[r for r in (v700.C.get("procurados") or []) if _valid_wanted(r)]; cards=[]
    for r in wanted[:3]:
        image=str(r.get("image") or ""); photo=f'<div class="wanted-photo"><img src="{v700.esc(image)}" alt="Foto do procurado" loading="lazy"></div>' if image else '<div class="wanted-photo no-image"></div>'; fs=r.get("fields") or {}
        cards.append(f'<article class="wanted-card">{photo}<div class="wanted-body"><span class="wanted-tag">PROCURADO ATIVO</span><div class="wanted-name">{v700.esc(r.get("name") or "Indivíduo não identificado")}</div><div class="wanted-id">REGISTRO {v700.esc(r.get("number") or "S/N")}</div><div class="info-grid"><div class="info"><label>CRIMES</label><b>{v700.esc(fs.get("Crimes","Não informado"))}</b></div><div class="info"><label>LOCALIZAÇÃO</label><b>{v700.esc(fs.get("Localização","Não informado"))}</b></div></div><div class="wanted-open"><a class="btn gold block" href="/registro/procurados/{quote(str(r.get("id")))}">ABRIR FICHA COMPLETA →</a></div></div></article>')
    auth=bool(u.get("authorized")); pending=bool(u.get("access_request_pending"));
    access='<a class="btn gold" href="/central">ABRIR CENTRAL COMPLETA →</a>' if auth else ('<span class="btn">SOLICITAÇÃO ENVIADA</span>' if pending else f'<form method="post" action="/abrir-central"><input type="hidden" name="csrf" value="{v700.esc(v700.csrf(u))}"><button class="btn gold">ABRIR CENTRAL COMPLETA →</button></form>')
    access_text="Acesso operacional autorizado." if auth else ("Seu pedido de autorização está aguardando análise." if pending else "Boletins e Perícias são liberados após aprovação.")
    body='<section class="hero"><article class="panel hero-copy"><div class="kicker">CENTRAL OPERACIONAL</div><h1>Toda operação começa com <span>informação.</span></h1><p>Consulte Procurados, acompanhe registros e concentre informações operacionais em um único ambiente. A Central mantém a consulta limpa e objetiva, sem mensagens internas do Discord.</p><div class="operator-line">OPERADOR: '+v700.esc(u.get("nome") or u.get("qra"))+' • PASSAPORTE '+v700.esc(u.get("passaporte"))+'</div></article><article class="panel hero-mark"><img src="'+v700.esc(_safe_logo())+'" alt="Brasão DICOR"></article></section><div class="section-head"><span class="kicker">MONITORAMENTO</span><h2>PROCURADOS EM DESTAQUE</h2></div><section class="wanted-grid">'+("".join(cards) if cards else '<div class="panel" style="padding:30px;color:#7891a0">Nenhum procurado ativo encontrado.</div>')+'</section><section class="access-card"><div><strong>ACESSO À CENTRAL COMPLETA</strong><small>'+v700.esc(access_text)+'</small></div><div>'+access+'</div></section><div class="section-head" style="margin-top:32px"><span class="kicker">FERRAMENTA</span><h2>FOTO → FIVE M</h2></div><section class="panel" style="padding:20px"><a class="btn gold" href="/fotos">ABRIR FERRAMENTA →</a><p style="color:#8498a6;font-size:11px;margin:9px 0 0">Envie uma imagem e receba o link direto para usar no FiveM.</p></section>'
    return _shell("DICOR • Central",body,u,v700.is_admin(u))

def _restricted(u):
    if not u.get("authorized"):
        pending=bool(u.get("access_request_pending")); msg="Solicitação enviada. Aguarde a aprovação do administrador." if pending else "Solicite autorização pelo botão da Central para liberar o ambiente."; body=f'<section class="panel restricted-head"><div class="kicker">DICOR • CONTROLE DE ACESSO</div><h1>ÁREA <span style="color:var(--gold2)">RESTRITA</span></h1><p>{v700.esc(msg)}</p><div style="margin-top:20px"><a class="btn" href="/">← VOLTAR</a></div></section>'; return _shell("DICOR • Área restrita",body,u,v700.is_admin(u))
    modules=[("BOLETINS","Registros completos recebidos pela Central.","/boletins","CONSULTAR"),("PERÍCIAS","Laudos, coletas e atendimentos disponíveis.","/pericias","CONSULTAR"),("PROCURADOS","Catálogo completo de indivíduos procurados.","/procurados","ABRIR"),("FOTO → FIVE M","Envie uma imagem e gere o link direto.","/fotos","ABRIR")]
    cards=[f'<a class="module-card" href="{v700.esc(href)}"><div class="module-icon">▣</div><h3>{v700.esc(title)}</h3><p>{v700.esc(desc)}</p><span class="btn gold">{v700.esc(button)} →</span></a>' for title,desc,href,button in modules]
    body='<section class="panel"><div class="restricted-head"><div class="kicker">DICOR • ACESSO OPERACIONAL</div><h1>TODA A CENTRAL</h1><p>Usuário autorizado: '+v700.esc(u.get("nome") or u.get("qra"))+' • Passaporte '+v700.esc(u.get("passaporte"))+'</p></div><section class="restricted-grid">'+''.join(cards)+'</section></section>'
    return _shell("DICOR • Central completa",body,u,v700.is_admin(u))

def _record_card(r,href):
    fs=r.get("fields") or {}; vals=list(fs.items())[:8]; fields=''.join(f'<div class="record-field"><label>{v700.esc(a)}</label><div>{v700.esc(b)}</div></div>' for a,b in vals)
    return f'<article class="record"><div class="record-head"><div><h3>{v700.esc(r.get("name") or r.get("subject") or "Registro")}</h3><div class="record-meta">Nº {v700.esc(r.get("number") or "S/N")} • {v700.esc(r.get("date") or "")}</div></div><span class="source-tag">{v700.esc(r.get("source") or "CENTRAL")}</span></div><section class="record-fields">{fields}</section><div class="record-actions"><a class="btn gold" href="{v700.esc(href)}">ABRIR FICHA COMPLETA →</a></div></article>'

def _list_page(u,kind,title,desc):
    rs=list(v700.C.get(kind,[]) or []); rs=[r for r in rs if _valid_wanted(r)] if kind=="procurados" else rs; cards=[_record_card(r,f"/registro/{kind}/{quote(str(r.get('id')))}") for r in rs]
    body=f'<section class="panel"><div class="page-heading"><div class="kicker">DICOR • CONSULTA</div><h1>{v700.esc(title)}</h1><p>{v700.esc(desc)} • {len(rs)} registro(s).</p></div><section class="records">'+("".join(cards) if cards else '<div style="padding:25px;color:#778d9b">Nenhum registro disponível.</div>')+'</section></section>'
    return _shell("DICOR • "+title,body,u,v700.is_admin(u))

def _detail(u,kind,rid):
    r=next((x for x in list(v700.C.get(kind,[]) or []) if str(x.get("id"))==rid),None)
    if kind=="procurados" and r and not _valid_wanted(r): r=None
    if kind!="procurados" and not u.get("authorized"): return _restricted(u)
    if not r:return _shell("DICOR • Registro",'<section class="panel page-heading"><div class="kicker">DICOR</div><h1>REGISTRO NÃO ENCONTRADO</h1></section>',u,v700.is_admin(u))
    fs=r.get("fields") or {}; fields=''.join(f'<div class="detail-field"><label>{v700.esc(a)}</label><div>{v700.esc(b)}</div></div>' for a,b in fs.items()); image=f'<img class="detail-photo" src="{v700.esc(r.get("image"))}" alt="Registro">' if r.get("image") else ''; origin=f'<a class="btn" href="{v700.esc(r.get("url"))}" target="_blank" rel="noopener">ABRIR ORIGEM →</a>' if r.get("url") else ''
    body=f'<section class="panel detail"><div class="kicker">DICOR • FICHA COMPLETA</div><div class="detail-head"><div><h1>{v700.esc(r.get("name") or r.get("subject") or "Registro")}</h1><div class="detail-sub">{v700.esc(kind.upper())} • {v700.esc(r.get("source") or "CENTRAL")} • Nº {v700.esc(r.get("number") or "S/N")}</div></div></div>{image}<section class="detail-fields">{fields}</section><div class="full-text">{v700.esc(r.get("full_text") or "Sem informações adicionais.")}</div><div class="detail-actions"><a class="btn" href="/{v700.esc(kind)}">← VOLTAR</a>{origin}</div></section>'
    return _shell("DICOR • Ficha",body,u,v700.is_admin(u))

def _photos(u,result="",error=""):
    result_html=f'<section class="result-box"><div class="kicker">LINK GERADO</div><h2 style="margin:8px 0 12px">Link direto para FiveM</h2><div class="copy-row"><input id="five" readonly value="{v700.esc(result)}"><button class="btn gold" onclick="cp(document.getElementById(\'five\').value,this)">COPIAR</button></div></section>' if result else ''; error_html=f'<div class="result-box" style="border-color:#6a3e45;color:#e8b5b8">{v700.esc(error)}</div>' if error else ''
    body=f'<section class="panel photo-page"><div class="kicker">DICOR • ARQUIVO VISUAL</div><h1>FOTO → FIVE M</h1><p style="color:#91a2ae;font-size:13px">PNG, JPG, WEBP ou GIF • até 10 MB.</p>{error_html}<form class="upload-box" method="post" action="/fotos/upload" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{v700.esc(v700.csrf(u))}"><input type="file" name="foto" accept="image/png,image/jpeg,image/webp,image/gif" required><div style="margin-top:14px"><button class="btn gold">ENVIAR FOTO E GERAR LINK →</button></div></form>{result_html}</section>'
    return _shell("DICOR • Foto",body,u,v700.is_admin(u))

def _admin_page(u):
    rs=sorted(v700.users().values(),key=lambda x:str(x.get("updated_at","")),reverse=True); online_n=sum(1 for x in rs if v700.online(x)); auth_n=sum(1 for x in rs if x.get("authorized")); items=[]
    for r in rs:
        key=v700.k(r.get("qra"),r.get("passaporte")); photo=str(r.get("foto_url") or _safe_logo()); status='<span class="status-pill online">ONLINE</span>' if v700.online(r) else '<span class="status-pill offline">OFFLINE</span>'; access='<span class="status-pill authorized">AUTORIZADO</span>' if r.get("authorized") else '<span class="status-pill blocked">BLOQUEADO</span>'; pend='<span class="status-pill pending">PENDENTE</span>' if r.get("access_request_pending") else ''
        items.append(f'<article class="user-card"><img class="profile-photo" src="{v700.esc(photo)}" alt="Perfil"><div><h3>{v700.esc(r.get("nome") or r.get("qra"))}</h3><small>QRA {v700.esc(r.get("qra"))} • PASSAPORTE {v700.esc(r.get("passaporte"))}</small><div>{status}{access}{pend}</div></div><div><small style="color:#6e8596;font-size:8px">CARGO</small><div style="margin-top:5px;font-size:12px">{v700.esc(r.get("cargo") or "Não definido")}</div><small style="display:block;color:#6e8596;font-size:8px;margin-top:10px">ÚLTIMO ACESSO</small><div style="margin-top:4px;font-size:9px;color:#a2b0b9">{v700.esc(r.get("last_seen") or "Nunca")}</div></div><div><form class="admin-form" method="post" action="/admin/user"><input type="hidden" name="csrf" value="{v700.esc(v700.csrf(u))}"><input type="hidden" name="key" value="{v700.esc(key)}"><input name="nome" maxlength="100" value="{v700.esc(r.get("nome") or "")}" placeholder="Nome"><input name="cargo" maxlength="100" value="{v700.esc(r.get("cargo") or "")}" placeholder="Cargo"><input name="foto_url" maxlength="500" value="{v700.esc(r.get("foto_url") or "")}" placeholder="URL da foto de perfil"><button>SALVAR</button></form></div></article>')
    body=f'<section class="panel"><div class="admin-hero"><div class="kicker">DICOR • ADMINISTRAÇÃO</div><h1>GESTÃO DE USUÁRIOS</h1><p>Área administrativa protegida. Usuários, presença, autorização, cargo e perfil.</p></div><section class="admin-stats"><div class="admin-stat"><small>TODOS OS USUÁRIOS</small><b>{len(rs)}</b></div><div class="admin-stat"><small>ONLINE</small><b>{online_n}</b></div><div class="admin-stat"><small>AUTORIZADOS</small><b>{auth_n}</b></div></section><section class="user-list">{("".join(items) if items else '<div style="padding:24px;color:#718798">Nenhum usuário cadastrado.</div>')}</section></section>'
    return _shell("DICOR • Usuários",body,u,True)

async def _admin_save(req):
    u=v700.current(req)
    if not u or not v700.is_admin(u): raise v700.web.HTTPForbidden(text="Acesso administrativo restrito.")
    p=await req.post()
    if not __import__("hmac").compare_digest(str(p.get("csrf","")),v700.csrf(u)): raise v700.web.HTTPForbidden(text="Token de segurança inválido.")
    x=v700.users(); key=str(p.get("key","")); z=x.get(key)
    if not isinstance(z,dict): raise v700.web.HTTPNotFound(text="Usuário não encontrado.")
    z["nome"]=v700.clean(p.get("nome",""))[:100] or z.get("qra",""); z["cargo"]=v700.clean(p.get("cargo",""))[:100]; photo=v700.clean(p.get("foto_url",""))[:500]
    if photo.startswith("https://") or photo.startswith("http://"): z["foto_url"]=photo
    elif not photo: z["foto_url"]=""
    z["updated_at"]=v700.iso(); x[key]=z; v700.save_users(x); v700.audit("ATUALIZOU_USUARIO",u,key); return v700.web.HTTPFound("/admin")

class CentralV704(v700.CentralV700):
    async def start(self):
        if v700.STARTED:return self
        v700.CLIENT=self.client
        if v700.discord and not v700.VIEW:
            try:self.client.add_view(v700.ApprovalView());v700.VIEW=True
            except Exception:pass
        app=v700.web.Application(client_max_size=12*1024*1024,middlewares=[v700.security])
        app.router.add_get("/health",v700.health);app.router.add_get("/",v700.home_route);app.router.add_get("/cadastro-operador",v700.login_route);app.router.add_post("/cadastro-operador",v700.login_route);app.router.add_post("/abrir-central",v700.open_route);app.router.add_get("/central",v700.central_route);app.router.add_get("/procurados",v700.procurados_route);app.router.add_get("/boletins",lambda r:v700.module_route(r,"boletins","Boletins","Registros completos da fonte configurada."));app.router.add_get("/pericias",lambda r:v700.module_route(r,"pericias","Perícias","Registros completos de perícias."));app.router.add_get("/operacoes",lambda r:v700.module_route(r,"operacoes","Operações","Registros operacionais disponíveis."));app.router.add_get("/registro/{kind}/{rid}",v700.record_handler);app.router.add_get("/fotos",v700.fotos_handler);app.router.add_post("/fotos/upload",v700.upload_route);app.router.add_get("/admin",v700.admin_route);app.router.add_post("/admin/user",_admin_save);app.router.add_post("/api/heartbeat",v700.heartbeat);app.router.add_post("/logout",v700.logout)
        self.runner=v700.web.AppRunner(app,access_log=None);await self.runner.setup();await v700.web.TCPSite(self.runner,"0.0.0.0",v700.PORT).start();v700.STARTED=True
        if v700.TASK is None or v700.TASK.done():v700.TASK=asyncio.create_task(v700.loop(),name="dicor-central-v704")
        print(f"✅ [CENTRAL V704] ativa na porta {v700.PORT} | refresh={v700.REFRESH}s",flush=True);return self

def install(bot_module):
    c=getattr(bot_module,"bot",None)
    if c is None:raise RuntimeError("cliente Discord não encontrado")
    v700.LOGO=_safe_logo();v700.shell=_shell;v700.home=_home;v700.restricted=_restricted;v700.record_card=_record_card;v700.list_page=_list_page;v700.detail=_detail;v700.photos=_photos;v700.admin_page=_admin_page;v700.admin_save=_admin_save;v700.refresh_data=_refresh_data
    return CentralV704(c)
