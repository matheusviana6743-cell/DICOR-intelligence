# -*- coding: utf-8 -*-
"""Central Visual V632 — home azul/PCPT restaurada.

Mantém Boletins, Perícias, Procurados e Fotos das versões atuais, mas
substitui somente a tela inicial pela identidade azul PCPT/PF aprovada,
com três Procurados em destaque e fotos clicáveis.
"""
from __future__ import annotations

from typing import Any
import html

import central_visual_v631 as v631
import central_visual_v630 as v630
import central_discord_v613 as base


def esc(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def wanted_card(row: dict[str, Any]) -> str:
    name = esc(row.get("name") or "Indivíduo não identificado")
    number = esc(row.get("number") or "S/N")
    crime = esc(row.get("crime") or "Não informado")
    image = str(row.get("image") or "").strip()
    if image:
        media = f'<button class="wanted-photo" type="button" data-photo="{esc(image)}" onclick="openPhoto(this.dataset.photo)"><img src="{esc(image)}" alt="Foto de {name}" loading="lazy"><span class="photo-zoom">ABRIR FOTO</span></button>'
    else:
        media = '<div class="wanted-photo no-photo"><span>SEM FOTO</span></div>'
    return f'''<article class="wanted-card">{media}<div class="wanted-body"><div class="wanted-tag">PROCURADO ATIVO</div><h3>{name}</h3><div class="wanted-line"><span>REGISTRO</span><b>Nº {number}</b></div><div class="wanted-line"><span>CRIME</span><b>{crime}</b></div><a class="wanted-open" href="/procurados">VER REGISTRO COMPLETO <span>→</span></a></div></article>'''


def dashboard_blue(rows: list[dict[str, Any]], qra: str, passport: str) -> str:
    wanted = list(rows or [])
    # A home mostra exatamente três destaques; a página Procurados continua com todos.
    cards = "".join(wanted_card(r) for r in wanted[:3])
    if not cards:
        cards = '<div class="empty-blue">Nenhum Procurado ativo encontrado no momento.</div>'
    bo = list(base.CACHE.get("bo", []) or [])
    pe = list(base.CACHE.get("pericia", []) or [])
    total = len(wanted)
    body = f'''<div class="blue-shell">
<header class="blue-header">
  <div class="blue-brand"><img src="{esc(base.PF_LOGO)}" alt="Polícia Federal"><div><strong>PCPT</strong><span>POLÍCIA CAPITAL / POLÍCIA FEDERAL</span></div></div>
  <nav class="blue-nav"><a class="active" href="/">CENTRAL</a><a href="/boletins">BOLETINS</a><a href="/procurados">PROCURADOS</a><a href="/pericias">PERÍCIAS</a><a href="/fotos">FOTOS</a></nav>
  <div class="blue-user"><i></i>{esc(qra)} <b>•</b> {esc(passport)}</div>
</header>
<main class="blue-main">
  <section class="blue-hero">
    <div class="hero-copy"><div class="blue-kicker">PCPT • SISTEMA INTEGRADO DE INTELIGÊNCIA</div><h1>CENTRAL DE<br><span>INTELIGÊNCIA</span></h1><p>Ambiente interno da Polícia Federal para consulta e acompanhamento de registros operacionais.</p><div class="hero-actions"><a href="/boletins">BOLETINS ATIVOS <b>{len(bo)}</b></a><a href="/pericias">PERÍCIAS PENDENTES <b>{len(pe)}</b></a></div></div>
    <div class="hero-mark"><div class="mark-ring"></div><img src="{esc(base.PF_LOGO)}" alt="Polícia Federal"></div>
  </section>
  <div class="blue-section-head"><div><span>MONITORAMENTO</span><h2>PROCURADOS EM DESTAQUE</h2></div><a href="/procurados">VER TODOS OS {total} →</a></div>
  <section class="wanted-grid-blue">{cards}</section>
  <section class="blue-bottom">
    <a href="/boletins" class="quick"><div class="quick-icon">▤</div><div><span>MÓDULO</span><strong>BOLETINS</strong><small>Consultar ocorrências e atendimentos</small></div><b>→</b></a>
    <a href="/pericias" class="quick"><div class="quick-icon">⚗</div><div><span>MÓDULO</span><strong>PERÍCIAS</strong><small>Acompanhar registros periciais</small></div><b>→</b></a>
    <a href="/fotos" class="quick"><div class="quick-icon">▱</div><div><span>MÓDULO</span><strong>FOTOS</strong><small>Banco visual e links diretos</small></div><b>→</b></a>
  </section>
  <footer class="blue-footer">PCPT • POLÍCIA CAPITAL / POLÍCIA FEDERAL &nbsp;|&nbsp; DICOR • CENTRAL DE INTELIGÊNCIA</footer>
</main>
<div id="photoViewer" class="photo-viewer" onclick="closePhoto(event)"><button type="button" onclick="closePhoto(event)">×</button><img id="photoViewerImg" alt="Foto ampliada"></div>
<script>function openPhoto(u){{document.getElementById('photoViewerImg').src=u;document.getElementById('photoViewer').classList.add('open')}}function closePhoto(e){{if(e)e.stopPropagation();document.getElementById('photoViewer').classList.remove('open');document.getElementById('photoViewerImg').src=''}}</script>
</div>'''
    css = '''
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;background:#06111d;color:#eaf2f8}body{overflow-x:hidden}a{text-decoration:none;color:inherit}.blue-shell{min-height:100vh;background:radial-gradient(circle at 85% 0,#174d79 0,#0b2135 25%,#06111d 62%,#040a10 100%)}.blue-header{height:82px;display:flex;align-items:center;gap:28px;padding:0 34px;border-bottom:1px solid #214664;background:rgba(5,15,25,.94);backdrop-filter:blur(14px);position:sticky;top:0;z-index:20}.blue-brand{display:flex;align-items:center;gap:12px;min-width:310px}.blue-brand img{width:47px;height:47px;object-fit:contain}.blue-brand strong{display:block;font-size:18px;letter-spacing:2px}.blue-brand span{display:block;color:#7292ad;font-size:7px;letter-spacing:1.7px;margin-top:4px}.blue-nav{display:flex;align-items:center;gap:25px;margin-left:auto}.blue-nav a{position:relative;color:#8da6ba;font-size:9px;font-weight:900;letter-spacing:1.2px;padding:31px 0}.blue-nav a:hover,.blue-nav a.active{color:#dceeff}.blue-nav a.active:after{content:'';position:absolute;left:0;right:0;bottom:20px;height:2px;background:#4d9ddd}.blue-user{font-size:8px;color:#8299ac;white-space:nowrap}.blue-user i{display:inline-block;width:7px;height:7px;border-radius:50%;background:#3fd38d;box-shadow:0 0 10px #3fd38d;margin-right:6px}.blue-user b{color:#40566b}.blue-main{max-width:1480px;margin:0 auto;padding:0 34px 36px}.blue-hero{min-height:390px;display:grid;grid-template-columns:1.25fr .75fr;align-items:center;border-bottom:1px solid #18364e}.hero-copy{padding:58px 20px 58px 18px}.blue-kicker{font-size:8px;font-weight:900;letter-spacing:2.5px;color:#58a6df;margin-bottom:16px}.hero-copy h1{font-size:48px;line-height:1.02;letter-spacing:1px;margin:0;font-weight:900}.hero-copy h1 span{color:#65b4ee}.hero-copy p{max-width:570px;color:#7890a5;font-size:11px;line-height:1.7;margin:18px 0 22px}.hero-actions{display:flex;gap:10px}.hero-actions a{display:flex;align-items:center;gap:14px;padding:11px 14px;border:1px solid #244a67;border-radius:9px;background:#0a1c2d;color:#8fb6d7;font-size:7px;font-weight:900;letter-spacing:1px}.hero-actions b{font-size:14px;color:#dcecf8}.hero-mark{position:relative;height:270px;display:grid;place-items:center;border:1px solid #204967;border-radius:22px;background:radial-gradient(circle at 50% 45%,#123b5d,#091b2b 48%,#07111b 78%);overflow:hidden;box-shadow:inset 0 0 80px #17639c25}.hero-mark img{width:150px;height:150px;object-fit:contain;position:relative;z-index:2;filter:drop-shadow(0 15px 25px #000b)}.mark-ring{position:absolute;width:225px;height:225px;border:1px solid #397eb033;border-radius:50%;box-shadow:0 0 0 35px #397eb010,0 0 0 70px #397eb006}.blue-section-head{display:flex;justify-content:space-between;align-items:end;padding:28px 3px 13px}.blue-section-head span{display:block;color:#4d9ddd;font-size:7px;font-weight:900;letter-spacing:2.3px;margin-bottom:5px}.blue-section-head h2{font-size:15px;letter-spacing:1.7px;margin:0}.blue-section-head>a{color:#72afe0;font-size:7px;font-weight:900;letter-spacing:1px}.wanted-grid-blue{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.wanted-card{border:1px solid #1b3b55;border-radius:14px;overflow:hidden;background:linear-gradient(150deg,#0b1b2a,#07111b);box-shadow:0 14px 35px #0005;transition:.18s}.wanted-card:hover{transform:translateY(-3px);border-color:#3976a1}.wanted-photo{position:relative;width:100%;height:235px;border:0;padding:0;background:#050c13;display:block;overflow:hidden;cursor:pointer}.wanted-photo img{width:100%;height:100%;object-fit:cover;display:block;filter:saturate(.82) contrast(1.04);transition:.2s}.wanted-card:hover .wanted-photo img{transform:scale(1.025)}.photo-zoom{position:absolute;right:10px;bottom:10px;padding:6px 8px;border:1px solid #7ab3db55;border-radius:6px;background:#06111dcc;color:#a9d5f2;font-size:6px;font-weight:900;letter-spacing:1px}.no-photo{display:grid;place-items:center;color:#526e84;font-size:8px;font-weight:900;letter-spacing:1px}.wanted-body{padding:15px}.wanted-tag{display:inline-block;padding:4px 7px;border-radius:5px;background:#103c62;color:#77b9e9;font-size:6px;font-weight:900;letter-spacing:1px}.wanted-body h3{font-size:17px;margin:11px 0 13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.wanted-line{display:flex;justify-content:space-between;gap:15px;padding:7px 0;border-top:1px solid #142d41}.wanted-line span{font-size:6px;color:#607d94;font-weight:900;letter-spacing:1px}.wanted-line b{font-size:8px;color:#b8cbd9;text-align:right;max-width:65%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.wanted-open{display:block;text-align:center;margin-top:12px;padding:10px;border:1px solid #255476;border-radius:8px;color:#83b9e4;font-size:7px;font-weight:900;letter-spacing:1px}.wanted-open:hover{background:#0b263d}.wanted-open span{margin-left:5px}.blue-bottom{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:18px}.quick{display:flex;align-items:center;gap:12px;padding:15px;border:1px solid #19374e;border-radius:12px;background:#07131f}.quick:hover{border-color:#32698f}.quick-icon{width:38px;height:38px;display:grid;place-items:center;border:1px solid #2a5878;border-radius:9px;color:#63ace2;background:#0a2031;font-size:18px}.quick span{display:block;color:#52718a;font-size:6px;letter-spacing:1.5px}.quick strong{display:block;font-size:10px;margin-top:4px}.quick small{display:block;color:#71889a;font-size:7px;margin-top:4px}.quick>b{margin-left:auto;color:#619fd0}.blue-footer{text-align:center;margin-top:24px;padding-top:18px;border-top:1px solid #173249;color:#4f687c;font-size:7px;letter-spacing:1px}.photo-viewer{position:fixed;inset:0;background:#02070ddd;display:none;align-items:center;justify-content:center;padding:30px;z-index:100}.photo-viewer.open{display:flex}.photo-viewer img{max-width:92vw;max-height:90vh;object-fit:contain;border-radius:10px;box-shadow:0 20px 70px #000}.photo-viewer button{position:absolute;right:25px;top:18px;border:0;background:transparent;color:#dce8f0;font-size:38px;cursor:pointer}.empty-blue{grid-column:1/-1;padding:50px;text-align:center;border:1px dashed #244b67;border-radius:14px;color:#71899d;background:#07131f}@media(max-width:1000px){.blue-header{padding:0 18px;gap:16px}.blue-brand{min-width:240px}.blue-nav{gap:14px}.blue-main{padding:0 18px 30px}.wanted-grid-blue{grid-template-columns:repeat(2,1fr)}.blue-hero{grid-template-columns:1fr}.hero-mark{max-width:520px;width:100%;margin:0 auto 35px}.hero-copy{padding-bottom:30px}.blue-bottom{grid-template-columns:1fr}}@media(max-width:700px){.blue-header{height:auto;min-height:74px;flex-wrap:wrap;padding:12px 14px}.blue-brand{min-width:0}.blue-nav{order:3;width:100%;overflow:auto;gap:20px}.blue-nav a{padding:10px 0}.blue-nav a.active:after{bottom:2px}.blue-user{margin-left:auto}.blue-main{padding:0 12px 25px}.hero-copy h1{font-size:34px}.wanted-grid-blue{grid-template-columns:1fr}.blue-section-head{align-items:start;gap:12px;flex-direction:column}.wanted-photo{height:260px}}
'''
    return base.page("PCPT • Central de Inteligência", body, css)


# O V631 instala todos os módulos atuais; trocamos apenas a função da home.
def install(bot_module: Any):
    central = v631.install(bot_module)
    v630.base.dashboard = dashboard_blue
    return central
