# -*- coding: utf-8 -*-
"""V174 - laboratório visual da Central DICOR.
Tudo é experimental, somente leitura e sem publicar/alterar nada no Discord."""
from __future__ import annotations
import html, json, re
from pathlib import Path
from typing import Any, Dict, List


def install(bot_module):
    web = getattr(bot_module, 'web', None)
    state = getattr(bot_module, '_v172_central_state', None)
    if web is None or not isinstance(state, dict): return

    def esc(v): return html.escape(str(v or ''), quote=True)
    def norm(v): return re.sub(r'[^a-z0-9áàâãéèêíìîóòôõúùûç ]+', ' ', str(v or '').casefold()).strip()
    def all_records(): return list(state.get('procurados', []))+list(state.get('boletins', []))+list(state.get('pericias', []))
    def field(r, *names):
        for n in names:
            v=r.get(n)
            if v not in (None,'',[],'Não informado','Nao informado'): return str(v)
        return 'Não informado'
    def shell(body):
        css='''body{margin:0;background:#050505;color:#eee8d6;font-family:Inter,Arial,sans-serif}.wrap{max-width:1450px;margin:auto;padding:26px 22px 70px}.top{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #3f351d;padding:16px 0}.brand{font:700 18px Georgia,serif;letter-spacing:2px}.gold{color:#dec35b}.nav a{color:#dec35b;text-decoration:none;margin-left:14px;font-size:12px}.hero{padding:35px 0 22px}.hero h1{font:44px Georgia,serif;margin:7px 0}.muted{color:#9d9685}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card{background:linear-gradient(145deg,#11110d,#090907);border:1px solid #403519;border-radius:15px;padding:18px}.card h2{font:21px Georgia,serif;margin:8px 0}.metric{font-size:32px;color:#efd879}.small{font-size:11px;color:#918a78}.search{width:100%;box-sizing:border-box;padding:14px;border:1px solid #4b3d1b;background:#090906;color:#fff;border-radius:10px;margin:12px 0 22px}.btn{display:inline-block;background:#d9b941;color:#080704;text-decoration:none;padding:10px 13px;border-radius:8px;font-weight:700;margin-top:8px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.result{margin-top:8px;padding:12px;border:1px solid #302817;border-radius:10px;background:#0a0a07}.pill{display:inline-block;border:1px solid #5a4718;color:#e4c85f;border-radius:99px;padding:4px 7px;font-size:9px;margin:2px}@media(max-width:1000px){.grid{grid-template-columns:repeat(2,1fr)}.row{grid-template-columns:1fr}}@media(max-width:600px){.grid{grid-template-columns:1fr}.top{display:block}.nav{margin-top:12px}.nav a{margin:0 10px 0 0}.hero h1{font-size:35px}}'''
        return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Laboratório DICOR</title><style>{css}</style></head><body><main class="wrap"><div class="top"><div class="brand">POLÍCIA FEDERAL — <span class="gold">DICOR</span></div><div class="nav"><a href="/">Central</a><a href="/catalogo">Procurados</a><a href="/boletins">Boletins</a><a href="/pericias">Perícias</a><a href="/fichas">Banco</a><a href="/arvore">Árvore</a></div></div>{body}</main></body></html>'

    def card(r, typ):
        nome=field(r,'nome','nome_completo','suspeito','autor')
        rg=field(r,'rg','passaporte')
        assunto=field(r,'crime','descricao','texto_discord')
        local=field(r,'local','localizacao','último avistamento')
        blob=norm(json.dumps(r,ensure_ascii=False,default=str))
        return f'<article class="result" data-search="{esc(blob)}"><span class="pill">{esc(typ.upper())}</span><b>{esc(nome)}</b><div class="small">RG: {esc(rg)} • Local: {esc(local)}</div><div>{esc(assunto)[:350]}</div></article>'

    async def portal(request):
        p,b,pe=[len(state.get(x,[])) for x in ('procurados','boletins','pericias')]
        rs=all_records()
        names={norm(field(r,'nome','nome_completo','suspeito','autor')) for r in rs if field(r,'nome','nome_completo','suspeito','autor')!='Não informado'}
        # Correlações objetivas, sem inferência.
        corr={}
        for r in rs:
            for k in ('rg','passaporte','local','numero_boletim'):
                v=norm(r.get(k,''))
                if v and v not in ('não informado','nao informado'): corr.setdefault((k,v),[]).append(r)
        corr=[(k,v) for k,v in corr.items() if len(v)>1]
        recent=sorted(rs,key=lambda x:str(x.get('data') or x.get('created_at') or ''),reverse=True)[:8]
        results=''.join(card(r,r.get('tipo','registro')) for r in rs[:120])
        corr_html=''.join(f'<div class="result"><span class="pill">CORRELAÇÃO</span><b>{esc(k[0])}: {esc(k[1])}</b><div class="small">{len(v)} registros relacionados objetivamente.</div></div>' for k,v in corr[:12]) or '<div class="result">Nenhuma correlação objetiva encontrada.</div>'
        timeline=''.join(f'<div class="result"><span class="pill">{esc(r.get("tipo","registro"))}</span><b>{esc(field(r,"nome","nome_completo","suspeito","autor"))}</b><div class="small">{esc(r.get("data") or "Data não informada")}</div><div>{esc(field(r,"descricao","crime","texto_discord"))[:300]}</div></div>' for r in recent) or '<div class="result">Sem eventos.</div>'
        body=f'''<section class="hero"><div class="gold">AMBIENTE DE TESTE • V174</div><h1>Central de Inteligência</h1><p class="muted">Novas funções em avaliação. Nada desta área altera ou publica no Discord.</p></section><section class="grid"><article class="card"><div class="small">PROCURADOS</div><div class="metric">{p}</div><a class="btn" href="/catalogo">Abrir</a></article><article class="card"><div class="small">BOLETINS</div><div class="metric">{b}</div><a class="btn" href="/boletins">Abrir</a></article><article class="card"><div class="small">PERÍCIAS</div><div class="metric">{pe}</div><a class="btn" href="/pericias">Abrir</a></article><article class="card"><div class="small">BANCO UNIFICADO</div><div class="metric">{len(rs)}</div><a class="btn" href="/fichas">Abrir</a></article><article class="card"><div class="small">PESSOAS INDEXADAS</div><div class="metric">{len(names)}</div><p class="small">Contagem sem duplicar nomes normalizados.</p></article><article class="card"><div class="small">CORRELAÇÕES OBJETIVAS</div><div class="metric">{len(corr)}</div><p class="small">Somente dados iguais encontrados nos registros.</p></article><article class="card"><div class="small">LINHA DO TEMPO</div><div class="metric">{len(recent)}</div><p class="small">Eventos recentes disponíveis.</p></article><article class="card"><div class="small">FASE DE TESTE</div><div class="metric">ON</div><p class="small">Discord permanece intacto.</p></article></section><section class="hero"><h2>🔎 Busca Global</h2><p class="muted">Pesquise nome, RG, BO, crime, local ou qualquer texto já sincronizado.</p><input id="global" class="search" placeholder="Digite para pesquisar..."><div id="results">{results or '<div class="result">Banco vazio.</div>'}</div></section><section class="row"><article class="card"><h2>🧠 Correlações</h2><p class="muted">{len(corr)} coincidências objetivas encontradas.</p>{corr_html}</article><article class="card"><h2>🕐 Timeline</h2><p class="muted">Últimos registros sincronizados.</p>{timeline}</article></section><section class="hero"><h2>🗂️ Módulos em teste</h2><div class="grid"><article class="card"><h2>🚗 Veículos</h2><p class="muted">Estrutura pronta para cruzar placa, modelo, cor e proprietário quando esses dados existirem nos registros.</p></article><article class="card"><h2>📑 Dossiê 360°</h2><p class="muted">Preparação para reunir registros relacionados em um único dossiê, sem criar informações.</p></article><article class="card"><h2>🕵️ Investigação</h2><p class="muted">Área de montagem experimental. Não publica nada no Discord.</p></article><article class="card"><h2>🔐 Auditoria</h2><p class="muted">Consultas desta fase podem ser registradas localmente no volume para avaliação.</p></article></div></section><script>const q=document.getElementById('global');q.oninput=()=>{{const v=q.value.toLowerCase();document.querySelectorAll('#results [data-search]').forEach(x=>x.style.display=x.dataset.search.includes(v)?'block':'none')}};</script>'''
        return web.Response(text=shell(body),content_type='text/html',charset='utf-8')

    bot_module.central_portal_http=portal
    bot_module.pagina_inicial=portal
    bot_module.central_lab_v174=True
    print('✅ V174 Laboratório Central ativo: busca global, dashboard, correlações e timeline em modo teste.',flush=True)
