# -*- coding: utf-8 -*-
"""Central Visual V630 — restauração fiel do dashboard DICOR aprovado.

A V629 já cuidava do visual geral. A V630 corrige a estrutura da home para
corresponder ao layout aprovado: sidebar, cabeçalho, painel de apresentação,
resumo e módulos.
"""
from __future__ import annotations

import html
from typing import Any

import central_visual_v629 as v629
import central_discord_v613 as base


def esc(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def icon(symbol: str) -> str:
    return f'<span class="side-icon">{symbol}</span>'


def module_card(title: str, description: str, symbol: str, href: str, restricted: bool = False) -> str:
    badge = '<span class="restricted">ACESSO RESTRITO</span>' if restricted else ''
    return f'''<article class="module-card">{badge}<div class="module-icon">{symbol}</div><div class="module-content"><h3>{esc(title)}</h3><p>{esc(description)}</p><a class="module-btn" href="{esc(href)}">Abrir módulo <span>→</span></a></div></article>'''


def dashboard_exact(rows: list[dict[str, Any]], qra: str, passport: str) -> str:
    bo = list(base.CACHE.get("bo", []) or [])
    pe = list(base.CACHE.get("pericia", []) or [])
    wanted = list(rows or [])
    body = f'''\
<div class="central-shell">
  <aside class="central-sidebar">
    <div class="sidebar-logo">{base.img(base.DICOR_LOGO, "dicor-brand", "DICOR")}</div>
    <nav class="sidebar-nav">
      <a class="side-link active" href="/">{icon('⌂')}<span>Central</span></a>
      <a class="side-link" href="/boletins">{icon('▤')}<span>Boletins</span></a>
      <a class="side-link" href="/procurados">{icon('♙')}<span>Procurados</span></a>
      <a class="side-link" href="/pericias">{icon('⚗')}<span>Perícias</span></a>
      <a class="side-link" href="/fichas">{icon('◉')}<span>Banco de Dados</span></a>
      <a class="side-link" href="/arvore">{icon('⌘')}<span>Árvore</span></a>
      <a class="side-link" href="/fotos">{icon('▱')}<span>Fotos</span></a>
      <a class="side-link" href="/funcionalidades">{icon('⚙')}<span>Configurações</span></a>
    </nav>
    <a class="side-link sidebar-exit" href="/cadastro-operador">{icon('⇥')}<span>Sair</span></a>
  </aside>

  <main class="central-main">
    <header class="central-header">
      <div class="header-brand">
        {base.img(base.DICOR_LOGO, "header-logo", "DICOR")}
        <div>
          <div class="header-title">DICOR • CENTRAL DE INTELIGÊNCIA</div>
          <div class="header-subtitle">CONSULTA INTERNA • SISTEMA INTEGRADO</div>
        </div>
      </div>
      <nav class="top-nav">
        <a class="top-link active" href="/">Central</a>
        <a class="top-link" href="/boletins">Boletins</a>
        <a class="top-link" href="/procurados">Procurados</a>
        <a class="top-link" href="/pericias">Perícias</a>
        <a class="top-link" href="/fichas">Banco de Dados</a>
        <a class="top-link" href="/arvore">Árvore</a>
      </nav>
      <div class="header-user"><span class="status-dot"></span><span>{esc(qra)}</span><span class="sep">•</span><span>{esc(passport)}</span><a href="/cadastro-operador" title="Sair">⇥</a></div>
    </header>

    <section class="intro-grid">
      <div class="intro-copy">
        <div class="kicker">DASHBOARD OPERACIONAL</div>
        <h1>Inteligência centralizada<br>com identidade <span>DICOR.</span></h1>
        <p>Dashboard inicial com os módulos operacionais e investigativos<br>em abas separadas. O painel da live permanece sem alterações.</p>
      </div>
      <div class="intro-emblem">{base.img(base.DICOR_LOGO, "emblem-logo", "DICOR")}</div>
    </section>

    <section class="section-title">RESUMO OPERACIONAL</section>
    <section class="summary-grid">
      <a class="summary-card" href="/boletins"><div><span>BOLETINS ATIVOS</span><strong>{len(bo)}</strong></div><i>▤</i></a>
      <a class="summary-card" href="/procurados"><div><span>PROCURADOS ATIVOS</span><strong>{len(wanted)}</strong></div><i>♙</i></a>
      <a class="summary-card" href="/pericias"><div><span>PERÍCIAS PENDENTES</span><strong>{len(pe)}</strong></div><i>⚗</i></a>
    </section>

    <section class="section-title">MÓDULOS DA CENTRAL</section>
    <section class="module-grid-v630">
      {module_card('Boletins Ativos','Ocorrências ainda em aberto ou atendimento.','▤','/boletins')}
      {module_card('Procurados Ativos','Lista oficial do canal de procurados ativos.','◉','/procurados')}
      {module_card('Perícias Pendentes','Perícias que ainda exigem conclusão.','⚗','/pericias')}
      {module_card('Banco de Dados','Fichas, evidências, pesquisas e inteligência investigativa.','▣','/fichas',True)}
      {module_card('Árvore de Inteligência','Vínculos entre pessoas, veículos e organizações.','⌘','/arvore',True)}
    </section>

    <footer class="central-footer">DICOR • POLÍCIA FEDERAL • AMBIENTE PROTEGIDO DE GTA RP</footer>
  </main>
</div>'''

    css = v629.NEW_CSS + r'''
.central-shell{min-height:100vh;display:grid;grid-template-columns:74px minmax(0,1fr);background:#030507;color:#f0f3f6}.central-sidebar{position:sticky;top:0;height:100vh;border-right:1px solid #27200d;background:linear-gradient(180deg,#050607,#080808);display:flex;flex-direction:column;align-items:center;padding:10px 0 14px;z-index:20}.sidebar-logo{width:100%;display:flex;justify-content:center;padding:4px 0 18px;border-bottom:1px solid #1a160d}.dicor-brand{width:46px;height:46px;object-fit:contain;background:transparent;filter:drop-shadow(0 7px 16px #000b)}.sidebar-nav{width:100%;display:flex;flex-direction:column;gap:5px;padding-top:9px}.side-link{display:flex;align-items:center;justify-content:center;gap:9px;min-height:46px;margin:0 7px;border:1px solid transparent;border-radius:10px;color:#89929b;font-size:8px;text-decoration:none}.side-link span:not(.side-icon){display:none}.side-link:hover,.side-link.active{color:#efca67;background:#171308;border-color:#4a3814;box-shadow:inset 3px 0 0 #d4ae4f}.side-icon{font-size:17px;line-height:1}.sidebar-exit{margin-top:auto}.central-main{min-width:0;padding:0 30px 30px}.central-header{position:sticky;top:0;z-index:15;min-height:104px;display:flex;align-items:center;gap:28px;border-bottom:1px solid #5e4716;background:rgba(3,5,7,.97);backdrop-filter:blur(14px)}.header-brand{display:flex;align-items:center;gap:12px;min-width:0}.header-logo{width:56px;height:56px;object-fit:contain;background:transparent;filter:drop-shadow(0 8px 20px #000b)}.header-title{font-size:19px;font-weight:900;letter-spacing:.4px;white-space:nowrap}.header-subtitle{font-size:9px;letter-spacing:2.3px;color:#d9b85c;margin-top:5px}.top-nav{display:flex;align-items:center;gap:24px;margin-left:auto}.top-link{position:relative;font-size:10px;color:#bcc2c7;padding:14px 0}.top-link.active,.top-link:hover{color:#e6bf59}.top-link.active:after{content:'';position:absolute;left:0;right:0;bottom:4px;height:2px;background:#d8b450;border-radius:2px}.header-user{display:flex;align-items:center;gap:7px;font-size:8px;color:#84919b;white-space:nowrap}.header-user a{color:#d6ae4a;font-size:18px;margin-left:7px}.status-dot{width:7px;height:7px;border-radius:50%;background:#43d28b;box-shadow:0 0 10px #43d28b}.sep{color:#47515a}.intro-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(320px,.85fr);align-items:center;gap:40px;padding:50px 0 42px;border-bottom:1px solid #453613}.intro-copy{padding-left:12px}.kicker{font-size:9px;font-weight:900;letter-spacing:2.3px;color:#dbb750;margin-bottom:14px}.intro-copy h1{font-family:Georgia,'Times New Roman',serif;font-weight:500;font-size:42px;line-height:1.07;letter-spacing:-.5px;margin:0;color:#f0f1f2}.intro-copy h1 span{color:#dcb552}.intro-copy p{font-size:12px;line-height:1.55;color:#9ca5ac;margin:20px 0 0}.intro-emblem{min-height:260px;border:1px solid #5a4519;border-radius:20px;background:radial-gradient(circle at 50% 40%,#20190b 0,#0c0e0f 45%,#070808 72%);display:grid;place-items:center;box-shadow:inset 0 0 55px #c8993020}.emblem-logo{width:155px;height:155px;object-fit:contain;filter:drop-shadow(0 16px 30px #000c)}.section-title{font-size:10px;font-weight:900;letter-spacing:2px;color:#dbb750;padding:24px 0 13px}.summary-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.summary-card{border:1px solid #2d2617;border-radius:14px;background:linear-gradient(145deg,#0e0e0e,#080909);display:flex;justify-content:space-between;align-items:center;padding:18px 20px;min-height:94px;box-shadow:0 8px 24px #0007}.summary-card:hover{border-color:#584717}.summary-card span{display:block;color:#7d8891;font-size:8px;letter-spacing:1.4px;font-weight:900}.summary-card strong{display:block;margin-top:8px;color:#e7ebee;font-size:30px}.summary-card i{font-style:normal;color:#d8b457;font-size:31px}.module-grid-v630{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:14px}.module-card{grid-column:span 2;position:relative;min-height:200px;padding:20px;border:1px solid #302718;border-radius:15px;background:linear-gradient(145deg,#101010,#080909);display:grid;grid-template-columns:58px 1fr;gap:16px;align-items:start;box-shadow:0 10px 28px #0007}.module-card:nth-child(4),.module-card:nth-child(5){grid-column:span 3;max-width:none}.module-card:hover{border-color:#5c4818;transform:translateY(-2px);transition:.16s}.module-icon{width:58px;height:58px;border:1px solid #7a5e1b;border-radius:11px;display:grid;place-items:center;color:#e4bd55;background:#0b0c0d;font-size:28px}.module-content h3{font-size:16px;margin:3px 0 8px;color:#f2f3f3}.module-content p{font-size:10px;line-height:1.55;color:#818b94;margin:0;max-width:270px}.module-btn{display:inline-flex;align-items:center;gap:7px;margin-top:18px;padding:10px 15px;border-radius:8px;background:linear-gradient(135deg,#e4bf58,#9a6f18);color:#080909;font-size:9px;font-weight:900}.restricted{position:absolute;right:14px;top:12px;padding:4px 7px;border:1px solid #7c5f1b;color:#d3ad4f;border-radius:99px;font-size:6px;letter-spacing:1px;font-weight:900}.central-footer{text-align:center;color:#5f686f;font-size:8px;letter-spacing:.8px;padding:26px 0 0;margin-top:25px;border-top:1px solid #332812}@media(max-width:1050px){.central-main{padding:0 20px 26px}.top-nav{gap:14px}.header-title{font-size:15px}.module-grid-v630{grid-template-columns:repeat(2,1fr)}.module-card,.module-card:nth-child(4),.module-card:nth-child(5){grid-column:span 1}}@media(max-width:780px){.central-shell{display:block}.central-sidebar{position:fixed;left:0;right:0;bottom:0;top:auto;height:62px;width:100%;border-right:0;border-top:1px solid #4c3a15;flex-direction:row;padding:0 8px}.sidebar-logo,.sidebar-exit{display:none}.sidebar-nav{display:flex;flex-direction:row;justify-content:space-around;align-items:center;gap:4px;padding:0}.side-link{min-height:48px;min-width:48px;margin:0}.central-main{padding:0 12px 78px}.central-header{position:relative;min-height:78px;gap:9px;flex-wrap:wrap;padding:9px 0}.header-logo{width:42px;height:42px}.header-title{font-size:12px}.header-subtitle{font-size:6px;letter-spacing:1.5px}.top-nav{order:3;width:100%;overflow-x:auto;gap:18px;scrollbar-width:none}.top-nav::-webkit-scrollbar{display:none}.top-link{font-size:8px;white-space:nowrap}.header-user{margin-left:auto;font-size:6px}.intro-grid{grid-template-columns:1fr;padding:28px 0}.intro-copy{padding-left:0}.intro-copy h1{font-size:30px}.intro-copy p{font-size:10px}.intro-emblem{min-height:190px}.emblem-logo{width:120px;height:120px}.summary-grid{grid-template-columns:1fr 1fr}.summary-card:last-child{grid-column:1/-1}.module-grid-v630{grid-template-columns:1fr}.module-card,.module-card:nth-child(4),.module-card:nth-child(5){grid-column:1/-1}.module-card{min-height:175px}}@media(max-width:500px){.summary-grid{grid-template-columns:1fr}.summary-card:last-child{grid-column:auto}.header-user{display:none}.intro-copy h1{font-size:27px}.intro-emblem{min-height:165px}.module-card{grid-template-columns:48px 1fr;gap:12px;padding:15px}.module-icon{width:48px;height:48px;font-size:22px}.module-content h3{font-size:14px}.module-content p{font-size:9px}.module-btn{font-size:8px;padding:9px 12px}}
'''
    return base.page("DICOR • Central de Inteligência", body, css)


base.dashboard = dashboard_exact


def install(bot_module: Any):
    return v629.install(bot_module)
