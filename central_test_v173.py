# -*- coding: utf-8 -*-
"""V173 - recursos experimentais somente na Central DICOR.

Tudo aqui é somente leitura e fica isolado da operação do Discord.
"""
from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List


def install(bot_module):
    web = getattr(bot_module, "web", None)
    if web is None:
        return
    state = getattr(bot_module, "_v172_central_state", {})
    data_dir = Path(str(getattr(bot_module, "DATA_DIR", "/data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    audit = data_dir / "central_test_audit.jsonl"

    def esc(v): return html.escape(str(v or ""), quote=True)
    def norm(v): return re.sub(r"[^a-z0-9áàâãéèêíìîóòôõúùûç ]+", " ", str(v or "").casefold()).strip()
    def records():
        return list(state.get("procurados", [])) + list(state.get("boletins", [])) + list(state.get("pericias", []))
    def audit_log(action, query=""):
        try:
            with audit.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": int(time.time()), "action": action, "query": query}, ensure_ascii=False) + "\n")
        except Exception: pass

    def layout(title, body):
        css='''body{margin:0;background:#050505;color:#eee8d6;font-family:Inter,Arial,sans-serif}.wrap{max-width:1400px;margin:auto;padding:30px 22px 70px}.top{display:flex;justify-content:space-between;gap:20px;align-items:center;border-bottom:1px solid #3d331b;padding-bottom:18px}.brand{font-family:Georgia,serif;letter-spacing:2px}.gold{color:#dfc45b}.nav a{color:#dfc45b;text-decoration:none;margin-left:14px;font-size:13px}.hero{padding:30px 0}.hero h1{font:42px Georgia,serif;margin:8px 0}.muted{color:#9e9887}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{background:#0d0d09;border:1px solid #403519;border-radius:16px;padding:18px}.card h2{font:22px Georgia,serif;margin:8px 0}.pill{display:inline-block;border:1px solid #5a4718;color:#e4c85f;border-radius:20px;padding:4px 8px;font-size:10px;margin:2px}.btn{display:inline-block;margin-top:12px;padding:10px 13px;background:#d9b941;color:#090804;text-decoration:none;border-radius:8px;font-weight:700}.search{box-sizing:border-box;width:100%;padding:14px;border-radius:10px;border:1px solid #4b3d1b;background:#090906;color:white;margin:15px 0 25px}.photo{width:100%;height:190px;object-fit:cover;border-radius:10px;margin-bottom:10px}.metric{font-size:34px;color:#efd775}@media(max-width:900px){.grid{grid-template-columns:1fr}.top{display:block}.nav{margin-top:15px}.nav a{margin:0 12px 0 0}}'''
        return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{css}</style></head><body><main class="wrap"><div class="top"><div class="brand">POLÍCIA FEDERAL — <span class="gold">DICOR</span></div><div class="nav"><a href="/">Central</a><a href="/teste">Laboratório</a><a href="/teste/busca">Busca Global</a><a href="/teste/investigacoes">Investigações</a></div></div>{body}</main></body></html>'

    def card(r, typ):
        nome = r.get("nome") or r.get("suspeito") or r.get("autor") or "Registro"
        rg = r.get("rg") or r.get("passaporte") or "Não informado"
        crime = r.get("crime") or r.get("descricao") or "Não informado"
        local = r.get("local") or "Não informado"
        imgs = r.get("fotos") or []
        img = f'<img class="photo" src="{esc(imgs[0])}">' if imgs else ''
        return f'<article class="card">{img}<span class="pill">{esc(typ.upper())}</span><h2>{esc(nome)}</h2><p><b>RG:</b> {esc(rg)}</p><p><b>Crime/assunto:</b> {esc(crime)}</p><p><b>Local:</b> {esc(local)}</p><a class="btn" href="/teste/ficha/{esc(r.get("mensagem_id") or "0")}">Abrir ficha</a></article>'

    async def lab(request):
        rs=records(); p=state.get("procurados",[]); b=state.get("boletins",[]); pe=state.get("pericias",[])
        body=f'''<section class="hero"><div class="gold">AMBIENTE DE TESTE • SOMENTE CENTRAL</div><h1>Laboratório DICOR</h1><p class="muted">Recursos experimentais. Nada altera ou publica no Discord.</p></section><section class="grid"><article class="card"><div class="metric">{len(rs)}</div><p>Registros indexados</p></article><article class="card"><div class="metric">{len(p)}</div><p>Procurados</p></article><article class="card"><div class="metric">{len(b)}</div><p>Boletins</p></article><article class="card"><div class="metric">{len(pe)}</div><p>Perícias</p></article><article class="card"><h2>🔎 Busca Global</h2><p>Pesquisa nome, RG, crime, local, BO e conteúdo.</p><a class="btn" href="/teste/busca">Testar</a></article><article class="card"><h2>🧠 Correlações</h2><p>Encontra coincidências reais entre registros, sem criar vínculos.</p><a class="btn" href="/teste/correlacoes">Testar</a></article><article class="card"><h2>🗂️ Investigações</h2><p>Organização experimental de registros em casos.</p><a class="btn" href="/teste/investigacoes">Testar</a></article><article class="card"><h2>📈 Dashboard</h2><p>Visão operacional dos dados sincronizados.</p><a class="btn" href="/teste/dashboard">Abrir</a></article><article class="card"><h2>🕐 Timeline</h2><p>Linha do tempo por pessoa ou registro.</p><a class="btn" href="/teste/timeline">Abrir</a></article></section>'''
        return web.Response(text=layout('Laboratório DICOR',body),content_type='text/html',charset='utf-8')

    async def busca(request):
        q=str(request.query.get('q','')).strip(); audit_log('busca_global',q)
        rs=[]
        for r in records():
            blob=norm(json.dumps(r,ensure_ascii=False,default=str))
            if not q or norm(q) in blob: rs.append(r)
        cards=''.join(card(r,r.get('tipo','registro')) for r in rs[:300]) or '<article class="card">Nenhum resultado.</article>'
        body=f'<section class="hero"><div class="gold">TESTE</div><h1>Busca Global</h1><p class="muted">{len(rs)} resultado(s)</p></section><form><input class="search" name="q" value="{esc(q)}" placeholder="Nome, RG, placa, BO, crime, local ou palavra-chave..."></form><section class="grid">{cards}</section>'
        return web.Response(text=layout('Busca Global',body),content_type='text/html',charset='utf-8')

    async def ficha(request):
        mid=str(request.match_info.get('mid','')); r=next((x for x in records() if str(x.get('mensagem_id'))==mid),None)
        if not r: return web.Response(status=404,text='Registro não encontrado')
        body=f'<section class="hero"><div class="gold">FICHA EXPERIMENTAL</div><h1>{esc(r.get("nome") or r.get("autor") or "Registro")}</h1><p class="muted">Tipo: {esc(r.get("tipo"))}</p></section><article class="card"><p><b>RG:</b> {esc(r.get("rg") or r.get("passaporte") or "Não informado")}</p><p><b>Crime:</b> {esc(r.get("crime"))}</p><p><b>Descrição:</b> {esc(r.get("descricao"))}</p><p><b>Local:</b> {esc(r.get("local"))}</p><p><b>Número/BO:</b> {esc(r.get("numero_boletim"))}</p><p><b>Autor:</b> {esc(r.get("autor"))}</p><p><b>Data:</b> {esc(r.get("data"))}</p><p><b>Conteúdo completo:</b></p><p>{esc(r.get("texto_discord"))}</p><div class="grid">{''.join(f'<img class="photo" src="{esc(u)}">' for u in (r.get("fotos") or []))}</div>{f'<a class="btn" target="_blank" href="{esc(r.get("mensagem_url"))}">Abrir publicação original</a>' if r.get('mensagem_url') else ''}</article>'
        return web.Response(text=layout('Ficha',body),content_type='text/html',charset='utf-8')

    async def correlacoes(request):
        rs=records(); groups={}
        for r in rs:
            keys=[]
            for k in ('rg','passaporte','numero_boletim','local'):
                v=str(r.get(k) or '').strip()
                if v and v.lower() not in ('não informado','nao informado'): keys.append((k,norm(v)))
            for k,v in keys: groups.setdefault((k,v),[]).append(r)
        matches=[(k,vs) for k,vs in groups.items() if len(vs)>1]
        cards=[]
        for (k,v),vs in matches:
            cards.append(f'<article class="card"><span class="pill">CORRELAÇÃO REAL</span><h2>{esc(k)}: {esc(v)}</h2><p>{len(vs)} registros compartilham este dado.</p><p>{" • ".join(esc(x.get("nome") or x.get("autor") or "Registro") for x in vs[:10])}</p></article>')
        body=f'<section class="hero"><div class="gold">TESTE</div><h1>Correlações</h1><p class="muted">Somente coincidências objetivas dos dados disponíveis.</p></section><section class="grid">{"".join(cards) or "<article class=card>Nenhuma correlação encontrada.</article>"}</section>'
        return web.Response(text=layout('Correlações',body),content_type='text/html',charset='utf-8')

    async def dashboard(request):
        body=f'<section class="hero"><div class="gold">TESTE</div><h1>Dashboard Operacional</h1><p class="muted">Atualizado a partir da sincronização da Central.</p></section><section class="grid"><article class="card"><div class="metric">{len(state.get("procurados",[]))}</div><p>Procurados ativos</p></article><article class="card"><div class="metric">{len(state.get("boletins",[]))}</div><p>Boletins</p></article><article class="card"><div class="metric">{len(state.get("pericias",[]))}</div><p>Perícias</p></article><article class="card"><div class="metric">{len(records())}</div><p>Total indexado</p></article></section>'
        return web.Response(text=layout('Dashboard',body),content_type='text/html',charset='utf-8')

    async def timeline(request):
        rs=sorted(records(),key=lambda x:str(x.get('data') or ''),reverse=True)
        cards=''.join(f'<article class="card"><span class="pill">{esc(x.get("tipo"))}</span><h2>{esc(x.get("nome") or x.get("autor") or "Registro")}</h2><p>{esc(x.get("data") or "Data não informada")}</p><p>{esc(x.get("descricao") or x.get("crime") or x.get("texto_discord") or "")}</p></article>' for x in rs[:100])
        body=f'<section class="hero"><div class="gold">TESTE</div><h1>Timeline</h1><p class="muted">Ordenação experimental por data dos registros disponíveis.</p></section><section class="grid">{cards or "<article class=card>Nenhum registro.</article>"}</section>'
        return web.Response(text=layout('Timeline',body),content_type='text/html',charset='utf-8')

    async def invest(request):
        body='''<section class="hero"><div class="gold">TESTE • SOMENTE LEITURA</div><h1>Investigações</h1><p class="muted">Área experimental. Nesta primeira versão, os casos são montados visualmente sem alterar o Discord.</p></section><article class="card"><h2>Nova investigação</h2><p>O próximo estágio pode permitir selecionar registros, adicionar observações e gerar um dossiê experimental.</p><a class="btn" href="/teste/busca">Selecionar registros</a></article>'''
        return web.Response(text=layout('Investigações',body),content_type='text/html',charset='utf-8')

    async def health(request):
        return web.json_response({'modo':'teste','central':True,'procurados':len(state.get('procurados',[])),'boletins':len(state.get('boletins',[])),'pericias':len(state.get('pericias',[]))})

    for path, handler in [('/teste',lab),('/teste/busca',busca),('/teste/ficha/{mid}',ficha),('/teste/correlacoes',correlacoes),('/teste/dashboard',dashboard),('/teste/timeline',timeline),('/teste/investigacoes',invest),('/teste/health',health)]:
        try: bot_module.web_routes_test_v173.append((path,handler))
        except AttributeError: bot_module.web_routes_test_v173=[(path,handler)]
    bot_module.central_test_v173_installed=True
    print('✅ V173 Laboratório da Central instalado (Discord inalterado).',flush=True)
