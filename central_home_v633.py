# -*- coding: utf-8 -*-
import central_gate_v633 as gate
import central_discord_v613 as base

def esc(v): return gate.esc(v)

def dashboard(rows,qra,passport):
    user=gate.accounts().get(base.account_key(qra,passport),{})
    cards=''.join(f'<article class="module"><h3>{esc(r.get("name"))}</h3><p>RG: {esc(r.get("rg"))}<br>Localização: {esc(r.get("last_seen"))}<br>Crimes: {esc(r.get("crime"))}</p><a href="/procurados">VER REGISTRO</a></article>' for r in rows[:3]) or '<div class="module"><h3>Nenhum procurado ativo</h3><p>Não há registros em destaque.</p></div>'
    access='<a class="primary gold" href="/funcionalidades">ABRIR FUNCIONALIDADES</a>' if user.get('authorized') else '<a class="primary gold" href="/solicitar-acesso">SOLICITAR AUTORIZAÇÃO</a>'
    body=f'''<main class="auth" style="width:min(1180px,calc(100% - 28px));text-align:left"><div class="pcpt" style="text-align:center">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL</div><h1 style="text-align:center">DICOR</h1><p class="sub" style="text-align:center">CENTRAL DE INTELIGÊNCIA • {esc(qra)} • PASSAPORTE {esc(passport)}</p><div class="module-grid">{cards}</div><div style="margin-top:18px;text-align:center">{access}</div></main>'''
    return base.page('DICOR • Central',body,base.AUTH_CSS+''' .module-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.module{padding:18px;border:1px solid #29445b;border-radius:14px;background:#08131f}.module h3{margin:0 0 8px;color:#e8edf2}.module p{color:#71869b;font-size:9px;line-height:1.7}.module a{display:block;margin-top:12px;padding:10px;text-align:center;border-radius:8px;background:#10283d;color:#c8e2f3;font-size:8px;font-weight:900}@media(max-width:800px){.module-grid{grid-template-columns:1fr}}''')

def install(bot_module):
    central=gate.install(bot_module)
    base.dashboard=dashboard
    return central
