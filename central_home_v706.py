# -*- coding: utf-8 -*-
"""DICOR Central V706.

Interface limpa e operacional em cima do núcleo V700.
- Home focada em Procurados, busca, fotos e acesso à Central completa.
- Área completa inclui Boletins, Perícias, Operações, Procurados e Foto -> FiveM.
- Dados continuam vindo do núcleo Discord/Gmail existente.
- Admin fica oculto do menu comum e ganha perfil/foto/cargo.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
from datetime import datetime
from urllib.parse import quote

import aiohttp
from aiohttp import web

import central_home_v700 as v700

BRAND = "PCPT POLICIA MORADA - POLICIA FEDERAL"
LOGO = str(os.getenv("DICOR_LOGO_URL") or getattr(getattr(v700, "source", None), "DICOR_LOGO", "") or "").strip()
if not LOGO:
    LOGO = "https://media.discordapp.net/attachments/1426821172237963375/1547778833866817596/image.png?format=webp&quality=lossless"

BAD_PROCURADO_MARKERS = (
    "recuperação assistida", "recuperacao assistida", "recuperação automática", "recuperacao automatica",
    "v112", "canal foi encontrado", "tarefa pendente", "tarefa concluída", "tarefa concluida",
    "registre no painel", "recuperação órf", "recuperacao orf", "sistema de procurados",
    "gerenciamento dos procurados", "painel de procurados"
)

CSS = r"""
:root{--bg:#02070c;--bg2:#071520;--panel:#091823;--panel2:#0d1e2b;--line:#29475a;--line2:#193345;--gold:#e4c25d;--gold2:#f3d87d;--blue:#5aaee4;--text:#f5f8fa;--muted:#91a4b1;--dim:#657b8b;--green:#67d5a4;--red:#e17c83}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:radial-gradient(circle at 75% 0,#123b55 0,transparent 30%),radial-gradient(circle at 10% 10%,#10283a 0,transparent 25%),#02070c;color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}body{overflow-x:hidden}a{text-decoration:none;color:inherit}button,input{font:inherit}
.top{position:sticky;top:0;z-index:60;min-height:82px;border-bottom:1px solid #233d4e;background:rgba(2,8,13,.97);backdrop-filter:blur(18px)}.top-inner{width:min(1320px,calc(100% - 44px));min-height:82px;margin:auto;display:flex;align-items:center;gap:24px}.brand{display:flex;align-items:center;gap:13px;min-width:360px}.brand img{width:54px;height:54px;object-fit:contain;filter:drop-shadow(0 8px 15px #000b)}.brand b{display:block;font-size:15px;letter-spacing:1.8px}.brand span{display:block;color:var(--gold2);font-size:9px;font-weight:900;letter-spacing:2.8px;margin-top:5px}.nav{display:flex;align-items:center;gap:24px;margin-left:auto}.nav a{color:#a7b6c0;font-size:10px;font-weight:900;letter-spacing:1px}.nav a:hover{color:#fff}.top-actions{display:flex;align-items:center;gap:12px}.user-mini{display:flex;align-items:center;gap:9px}.user-avatar{width:34px;height:34px;border:1px solid #36596d;border-radius:50%;object-fit:cover;background:#07131c}.user-mini b{font-size:10px;display:block}.user-mini small{display:block;color:#708595;font-size:8px;margin-top:2px}.logout{border:1px solid #2b4659;background:#07141d;color:#bfccd3;border-radius:8px;padding:8px 11px;font-size:8px;font-weight:900;cursor:pointer}
.wrap{width:min(1160px,calc(100% - 44px));margin:auto;padding:34px 0 70px}.panel{border:1px solid var(--line);border-radius:20px;background:linear-gradient(145deg,rgba(9,24,35,.98),rgba(4,12,18,.99));box-shadow:0 24px 70px #0008}
.home-title{display:flex;align-items:end;justify-content:space-between;gap:20px;margin-bottom:16px}.home-title .k{color:var(--blue);font-size:10px;font-weight:900;letter-spacing:2.5px}.home-title h1{font-size:31px;margin:6px 0 0;letter-spacing:1px}.home-title p{margin:4px 0 0;color:var(--muted);font-size:13px}.compact-brand{padding:25px 28px;margin-bottom:18px;display:flex;align-items:center;justify-content:space-between;gap:25px}.compact-brand .big{font-size:17px;font-weight:900;letter-spacing:1.5px}.compact-brand small{display:block;color:var(--dim);font-size:10px;margin-top:6px}.compact-brand img{width:82px;height:82px;object-fit:contain;filter:drop-shadow(0 10px 20px #000a)}
.search{display:flex;gap:10px;margin-bottom:20px}.search input{flex:1;height:54px;border:1px solid #2b495c;border-radius:11px;background:#06121b;color:#f2f5f7;padding:0 16px;font-size:15px;outline:none}.search input:focus{border-color:var(--gold2);box-shadow:0 0 0 3px #d7b84a22}.btn{display:inline-flex;align-items:center;justify-content:center;min-height:45px;padding:0 17px;border:1px solid #355972;border-radius:9px;background:#0a1c29;color:#dce7ee;font-size:10px;font-weight:950;letter-spacing:.9px;cursor:pointer}.btn.gold{border:0;background:linear-gradient(135deg,#f2d477,#a77514);color:#090b0c;box-shadow:0 10px 25px #0008}.btn.wide{width:100%}
.section-k{color:var(--blue);font-size:9px;font-weight:900;letter-spacing:2.5px}.section-h{display:flex;align-items:end;justify-content:space-between;margin:0 2px 12px}.section-h h2{font-size:22px;margin:5px 0 0}.section-h a{font-size:9px;color:#8dbbe0;font-weight:900}.wanted-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:17px}.wanted-card{overflow:hidden;border:1px solid #29485b;border-radius:17px;background:linear-gradient(160deg,#0a1a26,#050e15)}.wanted-photo{height:300px;background:#03090e;display:grid;place-items:center;overflow:hidden;position:relative}.wanted-photo img{width:100%;height:100%;object-fit:cover}.wanted-placeholder{font-size:24px;color:#4e6e82;font-weight:900;letter-spacing:3px}.tag{position:absolute;left:12px;top:12px;padding:7px 9px;background:#030a0edb;border:1px solid #d7b75866;color:#f1d57c;border-radius:7px;font-size:8px;font-weight:950;letter-spacing:1px}.wanted-body{padding:18px}.wanted-name{font-size:19px;font-weight:950}.wanted-id{margin-top:5px;color:var(--gold2);font-size:10px;font-weight:900;letter-spacing:1px}.info-grid{display:grid;gap:9px;margin-top:15px}.info{padding-top:9px;border-top:1px solid var(--line2)}.info label{display:block;color:#678294;font-size:8px;font-weight:900;letter-spacing:1.2px}.info b{display:block;margin-top:4px;color:#e9eef1;font-size:11px;line-height:1.45}.wanted-body .btn{margin-top:14px}.empty{padding:40px;border:1px dashed #294559;border-radius:15px;text-align:center;color:#708493;font-size:12px}
.action-row{display:grid;grid-template-columns:1fr 1fr;gap:17px;margin-top:18px}.action-card{padding:23px;border:1px solid #29485b;border-radius:16px;background:linear-gradient(155deg,#091a26,#061018);display:flex;align-items:center;justify-content:space-between;gap:20px}.action-card strong{font-size:16px}.action-card p{margin:6px 0 0;color:#8397a5;font-size:11px;line-height:1.55}.access-card{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-top:18px;padding:23px 25px;border:1px solid #806321;border-radius:16px;background:linear-gradient(105deg,#17150e,#08131c)}.access-card strong{font-size:17px;color:#f0d477}.access-card small{display:block;color:#948b73;font-size:10px;margin-top:5px}.footer{text-align:center;border-top:1px solid #173142;color:#526b7b;font-size:8px;padding:17px}
.restricted{overflow:hidden}.restricted-head{padding:31px 34px;border-bottom:1px solid #1c3546}.restricted-head h1{font-size:38px;margin:7px 0}.restricted-head p{margin:0;color:#8ea1ae;font-size:12px}.restricted-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;padding:22px 24px 26px}.module{padding:20px;border:1px solid #2a485a;border-radius:14px;background:linear-gradient(155deg,#0b1a25,#061018);min-height:205px;display:flex;flex-direction:column}.module .num{font-size:10px;color:var(--gold2);font-weight:900;letter-spacing:1.5px}.module h3{font-size:17px;margin:12px 0 7px}.module p{color:#879aa6;font-size:11px;line-height:1.6;margin:0}.module .btn{margin-top:auto}.module.operations{border-color:#6e5c28}.module.five{border-color:#2d5870}
.page{overflow:hidden}.page-head{padding:30px 34px 19px}.page-head h1{font-size:36px;margin:6px 0}.page-head p{font-size:12px;color:#91a3af;margin:0}.records{padding:0 25px 30px;display:grid;gap:13px}.record{border:1px solid #29485a;border-radius:15px;background:linear-gradient(155deg,#0a1823,#061019);padding:19px}.record-head{display:flex;align-items:start;justify-content:space-between;gap:14px}.record-head h3{font-size:17px;margin:0}.source{padding:6px 8px;border:1px solid #31576d;border-radius:999px;color:#9dc9e2;font-size:8px;font-weight:900}.record-meta{color:#6d8290;font-size:9px;margin-top:6px}.record-fields{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:14px}.record-field{padding:11px;border:1px solid #193346;border-radius:10px;background:#07131d}.record-field label{display:block;color:#648092;font-size:8px;font-weight:900;letter-spacing:1px}.record-field div{margin-top:5px;color:#e5ebef;font-size:11px;line-height:1.5}.record-actions{display:flex;gap:9px;margin-top:14px}.full{margin-top:14px;padding:14px 15px;border-left:2px solid var(--gold);background:#07131d;color:#aebbc2;white-space:pre-wrap;font-size:11px;line-height:1.65}
.photo-page{padding:34px}.photo-page h1{font-size:35px;margin:7px 0}.upload-box{margin-top:20px;padding:25px;border:1px dashed #3c5d70;border-radius:15px;background:#07151f}.upload-box input[type=file]{width:100%;padding:14px;border:1px solid #29475a;border-radius:10px;background:#06121a;color:#b7c5cc}.result{margin-top:18px;padding:18px;border:1px solid #2d4d61;border-radius:13px;background:#07141e}.copy-row{display:flex;gap:10px}.copy-row input{flex:1;height:47px;border:1px solid #29465a;border-radius:9px;background:#06121b;color:#e9eef1;padding:0 12px}
.admin-head{padding:31px 34px 20px}.admin-head h1{font-size:37px;margin:6px 0}.admin-head p{color:#8fa2ae;font-size:12px}.admin-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:13px;padding:0 34px 20px}.admin-stat{padding:16px;border:1px solid #29485b;border-radius:14px;background:#07131d}.admin-stat small{color:#688193;font-size:8px;font-weight:900;letter-spacing:1.2px}.admin-stat b{display:block;color:var(--gold2);font-size:28px;margin-top:7px}.users{display:grid;gap:14px;padding:0 34px 34px}.user-card{display:grid;grid-template-columns:auto 1.2fr .8fr 1.7fr;gap:18px;align-items:center;padding:18px;border:1px solid #29485b;border-radius:15px;background:linear-gradient(155deg,#0a1824,#061019)}.user-card .avatar{width:76px;height:76px;border-radius:50%;border:1px solid #3e6074;background:#07141d;object-fit:cover}.user-card h3{font-size:16px;margin:0}.user-card small{display:block;color:#708696;font-size:8px;margin-top:5px}.pill{display:inline-flex;padding:5px 8px;border-radius:999px;font-size:8px;font-weight:900;margin:8px 5px 0 0}.pill.online{background:#113a2d;border:1px solid #2c6c52;color:#9de6c5}.pill.offline{background:#291318;border:1px solid #65333a;color:#dda1a5}.pill.auth{background:#2d260f;border:1px solid #735c1f;color:#efd474}.pill.block{background:#1d2930;border:1px solid #334c59;color:#91a3ad}.admin-form{display:grid;grid-template-columns:1fr 1fr 1.3fr 1.3fr auto;gap:8px;margin-top:10px}.admin-form input{height:40px;border:1px solid #28465a;border-radius:8px;background:#06121b;color:#e9eef1;padding:0 10px;font-size:10px}.admin-form input[type=file]{padding:10px}.admin-form button{height:40px;border:0;border-radius:8px;background:linear-gradient(135deg,#efd16f,#a57413);color:#090c0d;font-size:9px;font-weight:950;padding:0 14px;cursor:pointer}
@media(max-width:1050px){.restricted-grid{grid-template-columns:repeat(3,1fr)}.wanted-grid{grid-template-columns:repeat(2,1fr)}.user-card{grid-template-columns:auto 1fr}.admin-form{grid-template-columns:1fr 1fr 1fr}.admin-form button{grid-column:1/-1}.nav{gap:14px}.brand{min-width:310px}}
@media(max-width:720px){.top{min-height:72px}.top-inner{min-height:72px;flex-wrap:wrap;padding:9px 0}.brand{min-width:0;flex:1}.brand img{width:44px;height:44px}.brand b{font-size:11px}.brand span{font-size:8px}.nav{order:3;width:100%;overflow:auto;padding-bottom:1px}.top-actions{display:none}.wrap{width:calc(100% - 20px);padding:23px 0 45px}.compact-brand{padding:20px}.compact-brand img{width:68px;height:68px}.home-title{display:block}.search{flex-direction:column}.wanted-grid,.action-row,.restricted-grid{grid-template-columns:1fr}.wanted-photo{height:260px}.access-card,.action-card{align-items:stretch;flex-direction:column}.access-card .btn,.action-card .btn{width:100%}.page-head,.photo-page,.admin-head,.restricted-head{padding:24px 21px}.records,.users{padding:0 21px 24px}.record-fields,.admin-stats{grid-template-columns:1fr}.admin-stats{padding:0 21px 18px}.admin-form{grid-template-columns:1fr}.admin-form button{grid-column:auto}.user-card{grid-template-columns:auto 1fr}.user-card>div:nth-child(3),.user-card>div:nth-child(4){grid-column:1/-1}.hero-mark img{max-width:160px}}
"""


def e(v):
    return html.escape(str(v or ""), quote=True)


def clean_text(v):
    return " ".join(str(v or "").split())


def valid_wanted(r):
    text = clean_text((r or {}).get("full_text") or (r or {}).get("name") or "").casefold()
    name = clean_text((r or {}).get("name") or "").casefold()
    if any(x in text for x in BAD_PROCURADO_MARKERS):
        return False
    if name in ("indivíduo não identificado", "individuo nao identificado", "não informado", "nao informado", "registro"):
        return False
    return True


def wanted_rows():
    rows = [r for r in (v700.C.get("procurados", []) or []) if isinstance(r, dict) and valid_wanted(r)]
    return rows[:100]


def avatar_for(u):
    return str((u or {}).get("foto") or LOGO).strip()


def shell(title, body, u=None, admin=False):
    name = clean_text((u or {}).get("nome") or (u or {}).get("qra") or "")
    passport = clean_text((u or {}).get("passaporte") or "")
    avatar = avatar_for(u) if u else LOGO
    profile = f'<div class="user-mini"><img class="user-avatar" src="{e(avatar)}" alt="Perfil"><div><b>{e(name)}</b><small>PASSAPORTE {e(passport)}</small></div></div>' if u else ''
    # Admin remains hidden from normal navigation. Only the admin user can use the small profile avatar/name link.
    if admin:
        profile = f'<a href="/admin" class="user-mini">{profile}</a>'
    nav = '<nav class="nav"><a href="/">CENTRAL</a><a href="/procurados">PROCURADOS</a><a href="/fotos">FOTOS</a></nav>'
    logout = ''
    if u:
        logout = f'<form method="post" action="/logout"><input type="hidden" name="csrf" value="{e(v700.csrf(u))}"><button class="logout">SAIR</button></form>'
    csp = "default-src 'self';img-src 'self' data: https:;connect-src 'self';style-src 'self' 'unsafe-inline';script-src 'self' 'unsafe-inline';frame-ancestors 'none';base-uri 'self';form-action 'self';object-src 'none'"
    return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{e(csp)}"><title>{e(title)}</title><style>{CSS}</style></head><body><header class="top"><div class="top-inner"><a class="brand" href="/"><img src="{e(LOGO)}" alt="Brasão DICOR"><div><b>{BRAND}</b><span>DICOR</span></div></a>{nav}<div class="top-actions">{profile}{logout}</div></div></header><main class="wrap">{body}</main><footer class="footer">{BRAND} • DICOR • CENTRAL DE INTELIGÊNCIA</footer></body></html>'


def wanted_card(r, detailed=True):
    fs = r.get("fields") or {}
    image = e(r.get("image"))
    photo = f'<img src="{image}" alt="Foto do procurado" loading="lazy">' if image else '<div class="wanted-placeholder">DICOR</div>'
    infos = ''
    for label in ("RG / Passaporte", "Crimes", "Localização", "Situação"):
        if label in fs:
            infos += f'<div class="info"><label>{e(label)}</label><b>{e(fs.get(label))}</b></div>'
    href = f'/registro/procurados/{quote(str(r.get("id") or ""))}'
    return f'<article class="wanted-card"><div class="wanted-photo">{photo}<span class="tag">PROCURADO ATIVO</span></div><div class="wanted-body"><div class="wanted-name">{e(r.get("name") or "Indivíduo não identificado")}</div><div class="wanted-id">REGISTRO {e(r.get("number") or "S/N")}</div><div class="info-grid">{infos}</div>{("<a class=\"btn gold wide\" href=\"" + e(href) + "\">ABRIR FICHA COMPLETA →</a>") if detailed else ""}</div></article>'


def home(u):
    rows = wanted_rows()
    cards = ''.join(wanted_card(r) for r in rows[:3]) or '<div class="empty">Nenhum Procurado válido disponível no momento.</div>'
    auth = bool(u.get("authorized"))
    pending = bool(u.get("access_request_pending"))
    if auth:
        access = '<a class="btn gold" href="/central">ABRIR CENTRAL COMPLETA →</a>'
        access_note = 'Acesso operacional liberado.'
    elif pending:
        access = '<span class="btn">SOLICITAÇÃO EM ANÁLISE</span>'
        access_note = 'Seu pedido já foi enviado para aprovação.'
    else:
        access = f'<form method="post" action="/abrir-central"><input type="hidden" name="csrf" value="{e(v700.csrf(u))}"><button class="btn gold" type="submit">ABRIR CENTRAL COMPLETA →</button></form>'
        access_note = 'Boletins, Perícias e Operações exigem aprovação.'
    body = f'''<section class="panel compact-brand"><div><div class="big">CENTRAL DICOR</div><small>{BRAND} • CONSULTA OPERACIONAL</small></div><img src="{e(LOGO)}" alt="Brasão DICOR"></section><div class="home-title"><div><div class="k">CENTRAL DE INTELIGÊNCIA</div><h1>PROCURADOS</h1><p>Consulte rapidamente indivíduos ativos e abra a ficha completa.</p></div></div><form class="search" method="get" action="/procurados"><input name="q" maxlength="120" placeholder="Pesquisar por nome, RG, passaporte ou crime"><button class="btn gold">PESQUISAR →</button></form><div class="section-h"><div><div class="section-k">MONITORAMENTO</div><h2>PROCURADOS EM DESTAQUE</h2></div><a href="/procurados">VER TODOS →</a></div><section class="wanted-grid">{cards}</section><section class="action-row"><a class="action-card" href="/fotos"><div><strong>FOTO → FIVE M</strong><p>Envie uma imagem e gere um link direto para uso no FiveM.</p></div><span class="btn">ABRIR FERRAMENTA →</span></a><a class="action-card" href="/procurados"><div><strong>CONSULTA DE PROCURADOS</strong><p>Pesquise por nome, RG, passaporte, crime ou registro.</p></div><span class="btn">CONSULTAR →</span></a></section><section class="access-card"><div><strong>ACESSO À CENTRAL COMPLETA</strong><small>{e(access_note)}</small></div><div>{access}</div></section>'''
    return shell("DICOR • Central", body, u, v700.is_admin(u))


def restricted(u):
    if not u.get("authorized"):
        pending = 'Seu pedido de autorização já foi enviado. Aguarde a aprovação.' if u.get("access_request_pending") else 'Use o botão da Central para solicitar autorização.'
        body = f'<section class="panel restricted"><div class="restricted-head"><div class="section-k">DICOR • CONTROLE DE ACESSO</div><h1>ÁREA RESTRITA</h1><p>{e(pending)}</p><a class="btn" href="/">← VOLTAR</a></div></section>'
        return shell("DICOR • Área Restrita", body, u, v700.is_admin(u))
    modules = [
        ("01","BOLETINS","Registros completos recebidos do Discord e do Gmail.","/boletins","CONSULTAR →",""),
        ("02","PERÍCIAS","Laudos, coletas e atendimentos periciais.","/pericias","CONSULTAR →",""),
        ("03","OPERAÇÕES","Registros e informações operacionais do DICOR.","/operacoes","ABRIR →","operations"),
        ("04","PROCURADOS","Catálogo completo de indivíduos procurados.","/procurados","ABRIR →",""),
        ("05","FOTO → FIVE M","Envie uma imagem e copie o link direto.","/fotos","ABRIR →","five"),
    ]
    cards = ''.join(f'<article class="module {cls}"><div class="num">MÓDULO {n}</div><h3>{e(t)}</h3><p>{e(d)}</p><a class="btn gold" href="{e(h)}">{e(b)}</a></article>' for n,t,d,h,b,cls in modules)
    body = f'<section class="panel restricted"><div class="restricted-head"><div class="section-k">DICOR • ACESSO OPERACIONAL</div><h1>TODA A CENTRAL</h1><p>Usuário: {e(u.get("nome") or u.get("qra"))} • Passaporte {e(u.get("passaporte"))}</p></div><section class="restricted-grid">{cards}</section></section>'
    return shell("DICOR • Central Completa", body, u, v700.is_admin(u))


def filtered_rows(kind):
    rows = [r for r in (v700.C.get(kind,[]) or []) if isinstance(r,dict)]
    if kind == "procurados": rows = [r for r in rows if valid_wanted(r)]
    return rows


def list_page(u, kind, title, desc, query=""):
    rows = filtered_rows(kind)
    q = clean_text(query).casefold()
    if q:
        rows = [r for r in rows if q in json.dumps(r,ensure_ascii=False).casefold()]
    cards=[]
    for r in rows:
        fs=r.get("fields") or {}
        vals=[]
        for key,val in fs.items():
            vals.append(f'<div class="record-field"><label>{e(key)}</label><div>{e(val)}</div></div>')
        href=f'/registro/{e(kind)}/{quote(str(r.get("id") or ""))}'
        cards.append(f'<article class="record"><div class="record-head"><h3>{e(r.get("name") or r.get("subject") or "Registro")}</h3><span class="source">{e(r.get("source") or "DICOR")}</span></div><div class="record-meta">Nº {e(r.get("number") or "S/N")} • {e(r.get("date") or "")}</div><div class="record-fields">{"".join(vals)}</div><div class="record-actions"><a class="btn gold" href="{href}">ABRIR FICHA COMPLETA →</a></div></article>')
    body=f'<section class="panel page"><header class="page-head"><div class="section-k">DICOR • {e(title).upper()}</div><h1>{e(title)}</h1><p>{e(desc)}</p></header><form class="search" style="padding:0 25px" method="get"><input name="q" value="{e(query)}" placeholder="Pesquisar neste módulo"><button class="btn gold">PESQUISAR →</button></form><section class="records">'+(''.join(cards) or '<div class="empty">Nenhum registro encontrado.</div>')+'</section></section>'
    return shell("DICOR • "+title,body,u,v700.is_admin(u))


def detail_page(u, kind, rid):
    rows = filtered_rows(kind)
    r = next((x for x in rows if str(x.get("id")) == str(rid)), None)
    if not r:
        return shell("DICOR • Registro",'<section class="panel page"><div class="page-head"><h1>REGISTRO NÃO ENCONTRADO</h1></div></section>',u,v700.is_admin(u))
    image=f'<img class="detail-photo" src="{e(r.get("image"))}" alt="Foto" style="max-width:460px;max-height:420px;border-radius:14px;border:1px solid #29485b;object-fit:cover;margin:0 34px 20px">' if r.get("image") else ''
    fields=''.join(f'<div class="record-field"><label>{e(a)}</label><div>{e(b)}</div></div>' for a,b in (r.get("fields") or {}).items())
    full=e(r.get("full_text") or "Sem informações adicionais.")
    body=f'<section class="panel page"><header class="page-head"><div class="section-k">DICOR • REGISTRO COMPLETO</div><h1>{e(r.get("name") or "Registro")}</h1><p>{e(kind.upper())} • Nº {e(r.get("number") or "S/N")} • {e(r.get("source") or "")}</p></header>{image}<section class="records"><div class="record-fields">{fields}</div><div class="full">{full}</div><div class="record-actions"><a class="btn" href="/{e(kind)}">← VOLTAR</a>{f'<a class="btn" href="{e(r.get("url"))}" target="_blank" rel="noopener">ABRIR ORIGEM →</a>' if r.get("url") else ''}</div></section></section>'
    return shell("DICOR • Registro",body,u,v700.is_admin(u))


def photos_page(u, result="", error=""):
    result_html = f'<section class="result"><div class="section-k">LINK GERADO</div><div class="copy-row"><input id="five" readonly value="{e(result)}"><button class="btn gold" onclick="navigator.clipboard.writeText(document.getElementById(\'five\').value);this.innerText=\'COPIADO\'">COPIAR</button></div></section>' if result else ''
    error_html = f'<div class="empty" style="margin-top:15px;border-color:#63363b;color:#e0a4a8">{e(error)}</div>' if error else ''
    body=f'<section class="panel photo-page"><div class="section-k">DICOR • FERRAMENTA VISUAL</div><h1>FOTO → FIVE M</h1><p>Envie uma imagem e receba um link direto pronto para o FiveM.</p>{error_html}<div class="upload-box"><form method="post" action="/fotos/upload" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{e(v700.csrf(u))}"><input type="file" name="foto" accept="image/png,image/jpeg,image/webp,image/gif" required><button class="btn gold" style="margin-top:14px">ENVIAR FOTO E GERAR LINK →</button></form></div>{result_html}</section>'
    return shell("DICOR • Foto → FiveM",body,u,v700.is_admin(u))


def admin_page(u):
    rows=sorted(v700.users().values(),key=lambda x:str(x.get("updated_at","")),reverse=True)
    items=[]
    for r in rows:
        status='<span class="pill online">ONLINE</span>' if v700.online(r) else '<span class="pill offline">OFFLINE</span>'
        access='<span class="pill auth">AUTORIZADO</span>' if r.get("authorized") else '<span class="pill block">BLOQUEADO</span>'
        if r.get("access_request_pending"): access += '<span class="pill pending">PENDENTE</span>'
        key=v700.k(r.get("qra"),r.get("passaporte"))
        avatar=avatar_for(r)
        items.append(f'<article class="user-card"><img class="avatar" src="{e(avatar)}" alt="Perfil"><div><h3>{e(r.get("nome") or r.get("qra"))}</h3><small>QRA {e(r.get("qra"))} • PASSAPORTE {e(r.get("passaporte"))}</small>{status}{access}</div><div><small>CARGO</small><div style="margin-top:5px;font-size:13px">{e(r.get("cargo") or "Não definido")}</div><small style="margin-top:8px">ÚLTIMO ACESSO</small><div style="margin-top:4px;font-size:10px;color:#a8b7bf">{e(r.get("last_seen") or "Nunca")}</div></div><form class="admin-form" method="post" action="/admin/user" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{e(v700.csrf(u))}"><input type="hidden" name="key" value="{e(key)}"><input name="nome" maxlength="100" value="{e(r.get("nome") or "")}" placeholder="Nome"><input name="cargo" maxlength="100" value="{e(r.get("cargo") or "")}" placeholder="Cargo"><input name="foto_url" maxlength="500" value="{e(r.get("foto") or "")}" placeholder="URL da foto (opcional)"><input name="foto" type="file" accept="image/png,image/jpeg,image/webp,image/gif"><button>SALVAR</button></form></article>')
    body=f'<section class="panel"><header class="admin-head"><div class="section-k">DICOR • ADMINISTRAÇÃO</div><h1>USUÁRIOS</h1><p>Cadastros persistentes, presença, autorização, cargo e perfil.</p></header><div class="admin-stats"><div class="admin-stat"><small>TODOS</small><b>{len(rows)}</b></div><div class="admin-stat"><small>ONLINE</small><b>{sum(1 for x in rows if v700.online(x))}</b></div><div class="admin-stat"><small>AUTORIZADOS</small><b>{sum(1 for x in rows if x.get("authorized"))}</b></div></div><section class="users">{"".join(items) or '<div class="empty">Nenhum usuário cadastrado.</div>'}</section></section>'
    return shell("DICOR • Usuários",body,u,True)


async def operations_scan(client):
    """Varre canais do Discord relacionados a operação/mesas sem exigir ID manual."""
    if not client or not getattr(client,"is_ready",lambda:False)(): return []
    out=[]; seen=set()
    try:
        for guild in getattr(client,"guilds",[]) or []:
            for ch in getattr(guild,"text_channels",[]) or []:
                nm=clean_text(getattr(ch,"name","")).casefold()
                if not any(x in nm for x in ("operacao","operação","mesa","inteligencia","inteligência")): continue
                if getattr(ch,"id",0) in seen: continue
                seen.add(getattr(ch,"id",0))
                try:
                    msgs=[m async for m in ch.history(limit=100)]
                except Exception:
                    continue
                for m in msgs:
                    text=clean_text(getattr(m,"content","") or "")
                    if not text: continue
                    embeds=getattr(m,"embeds",[]) or []
                    for emb in embeds:
                        text=clean_text(text+" "+str(getattr(emb,"title","") or "")+" "+str(getattr(emb,"description","") or ""))
                    if len(text)<8: continue
                    out.append({"id":str(getattr(m,"id","")),"number":"S/N","name":clean_text(text[:90]),"kind":"operacoes","source":"DISCORD","subject":"","date":str(getattr(m,"created_at","")),"image":"","url":str(getattr(m,"jump_url","")),"fields":{"Canal":str(getattr(ch,"name","")+""),"Número do registro":"S/N"},"full_text":text})
    except Exception:
        return []
    uniq={x["id"]:x for x in out if x.get("id")}
    return list(uniq.values())[:150]


_ORIG_REFRESH = v700.refresh_data
async def refresh_data_v706():
    await _ORIG_REFRESH()
    try:
        extra=await operations_scan(v700.CLIENT)
        if extra:
            v700.C["operacoes"]=extra
        # Remove only presentation-noise records; never alter persistent source data.
        v700.C["procurados"]=[r for r in (v700.C.get("procurados",[]) or []) if valid_wanted(r)]
    except Exception:
        pass


def _patch_handlers():
    v700.home = home
    v700.restricted = restricted
    v700.list_page = lambda u,kind,title,desc: list_page(u,kind,title,desc,"")
    v700.detail = detail_page
    v700.photos = photos_page
    v700.admin_page = admin_page
    v700.refresh_data = refresh_data_v706

    async def procurados_route(req):
        u=v700.current(req)
        if not u: return web.HTTPFound("/cadastro-operador")
        u=v700.touch(u)
        return web.Response(text=list_page(u,"procurados","Procurados","Catálogo de indivíduos procurados.",req.query.get("q","")),content_type="text/html")
    v700.procurados_route=procurados_route

    async def admin_save(req):
        u=v700.current(req)
        if not u or not v700.is_admin(u): raise web.HTTPForbidden(text="Acesso administrativo restrito.")
        form=await req.post()
        if not v700.hmac.compare_digest(str(form.get("csrf","")),v700.csrf(u)): raise web.HTTPForbidden(text="Token de segurança inválido.")
        data=v700.users(); z=data.get(str(form.get("key","")))
        if not isinstance(z,dict): raise web.HTTPNotFound(text="Usuário não encontrado.")
        z["nome"]=clean_text(form.get("nome",""))[:100] or z.get("qra","")
        z["cargo"]=clean_text(form.get("cargo",""))[:100]
        url=clean_text(form.get("foto_url",""))[:500]
        file_part=form.get("foto")
        if url: z["foto"]=url
        elif hasattr(file_part,"file"):
            try:
                raw=file_part.file.read()
                if raw and len(raw)<=5*1024*1024:
                    keyname=re.sub(r"[^A-Za-z0-9._-]+","_",str(getattr(file_part,"filename","perfil.png")))[:80]
                    api=str(os.getenv("FIVEMANAGE_API_KEY","")).strip()
                    if api:
                        fd=aiohttp.FormData();fd.add_field("file",raw,filename=keyname,content_type=getattr(file_part,"content_type",None) or "application/octet-stream");fd.add_field("path","dicor-perfis");fd.add_field("retentionExempt","true")
                        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45)) as s:
                            async with s.post("https://api.fivemanage.com/api/v3/file",headers={"Authorization":api},data=fd) as rr:
                                payload=await rr.json(content_type=None)
                                obj=payload.get("data") if isinstance(payload,dict) else {}
                                got=str((obj or {}).get("url") or (obj or {}).get("originalUrl") or "").strip()
                                if 200<=rr.status<300 and got: z["foto"]=got
            except Exception:
                pass
        z["updated_at"]=v700.iso(); data[str(form.get("key"))]=z; v700.save_users(data); v700.audit("ATUALIZOU_USUARIO",u,str(form.get("key")))
        return web.HTTPFound("/admin")
    v700.admin_save=admin_save


def install(bot_module):
    _patch_handlers()
    return v700.install(bot_module)
