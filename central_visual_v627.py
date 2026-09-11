# -*- coding: utf-8 -*-
"""Central Visual V627 — identidade visual PF/DICOR."""
from __future__ import annotations
import re
from typing import Any
import central_discord_v613 as base
import central_procurados_v625 as v625

SIDEBAR_CSS = r'''
.side{width:260px!important;padding:18px 14px 16px!important;background:linear-gradient(180deg,#091522,#07101a 55%,#05090f)!important;border-right:1px solid #223b54!important;box-shadow:16px 0 45px #0005;display:flex;flex-direction:column;gap:13px;overflow:hidden}
.brand img{background:transparent!important;mix-blend-mode:multiply;filter:drop-shadow(0 7px 15px #0009)}
.v627-brand{display:flex;align-items:center;gap:9px;padding:5px 4px 16px;border-bottom:1px solid #1e3448}
.v627-brand .dicor-logo{width:54px;height:54px;object-fit:contain}
.v627-brand .pf-logo{width:38px;height:38px;object-fit:contain;padding:3px;border:1px solid #29435b;border-radius:9px;background:#07101a!important}
.v627-brand strong{display:block;font-size:14px;letter-spacing:2px}.v627-brand small{display:block;margin-top:4px;color:#d4aa4e;font-size:7px;letter-spacing:1.5px}
.v627-title{color:#4f6e87;font-size:7px;font-weight:900;letter-spacing:1.8px;padding:4px 5px 0}
.v627-nav{display:flex;flex-direction:column;gap:7px}.v627-nav a{display:flex;align-items:center;gap:10px;padding:11px 10px;border:1px solid #193047;border-radius:10px;background:#08131f;color:#8298ad;font-size:8px;font-weight:900;letter-spacing:1px;transition:.16s}.v627-nav a:hover{border-color:#345b7c;background:#0b1d2d;color:#e5edf3;transform:translateX(2px)}.v627-nav a.active{border-color:#82631f;background:linear-gradient(105deg,#17140c,#0b1219);color:#e9c86d}.v627-ico{width:23px;height:23px;display:grid;place-items:center;border-radius:7px;background:#102a40;color:#78addc;font-size:10px}.active .v627-ico{background:#624a18;color:#f2d071}
.v627-status{margin-top:auto;padding:12px;border:1px solid #20384f;border-radius:12px;background:linear-gradient(145deg,#0b1928,#07101a);box-shadow:inset 0 0 24px #0e4d7d16}.v627-status .label{color:#4f6a82;font-size:6px;letter-spacing:1.5px}.v627-status b{display:block;margin-top:5px;color:#d9e3ea;font-size:9px}.v627-status span{display:block;margin-top:4px;color:#5d7a92;font-size:7px;line-height:1.5}
.main{padding:22px 30px 48px!important}.top{border-bottom-color:#1e3448!important}.hero{box-shadow:inset 0 0 90px #0e5a9818,0 16px 42px #0003!important}.wanted{box-shadow:0 18px 45px #0003}.card{box-shadow:0 9px 26px #0003}.card:hover{transform:translateY(-2px);border-color:#315878}
@media(max-width:900px){.side{width:auto!important;height:auto!important;position:relative!important;box-shadow:none!important}.v627-status{display:none}.v627-nav{display:grid;grid-template-columns:repeat(2,1fr)}.main{padding:14px 13px 30px!important}}
@media(max-width:520px){.v627-nav{grid-template-columns:1fr}.v627-nav a:nth-child(n+5){display:none}.v627-brand .dicor-logo{width:47px;height:47px}.main{padding-left:10px!important;padding-right:10px!important}}
'''

def sidebar(kind: str) -> str:
    def a(v: str): return ' active' if kind == v else ''
    return f'''<aside class="side"><div class="v627-brand"><img class="dicor-logo" src="{base.esc(base.DICOR_LOGO)}" alt="DICOR"><img class="pf-logo" src="{base.esc(base.PF_LOGO)}" alt="Polícia Federal"><div><strong>DICOR</strong><small>INTELIGÊNCIA</small></div></div><div class="v627-title">PAINEL OPERACIONAL</div><nav class="v627-nav"><a class="{a("CENTRAL")}" href="/"><span class="v627-ico">⌂</span>CENTRAL</a><a class="{a("PROCURADOS")}" href="/procurados"><span class="v627-ico">⚠</span>PROCURADOS</a><a class="{a("BOLETINS")}" href="/boletins"><span class="v627-ico">▣</span>BOLETINS</a><a class="{a("PERÍCIAS")}" href="/pericias"><span class="v627-ico">⌕</span>PERÍCIAS</a><a class="{a("FOTOS")}" href="/fotos"><span class="v627-ico">▧</span>FOTOS</a><a href="/funcionalidades"><span class="v627-ico">≡</span>FUNCIONALIDADES</a></nav><div class="v627-status"><div class="label">SISTEMA</div><b>PCPT / POLÍCIA FEDERAL</b><span>DICOR • CENTRAL DE INTELIGÊNCIA<br>ACESSO RESTRITO • MODO OPERACIONAL</span></div></aside>'''

def patch(text: str, kind: str) -> str:
    if '<aside class="side">' in text:
        return re.sub(r'<aside class="side">.*?</aside>', sidebar(kind), text, count=1, flags=re.S)
    return text

_orig_dashboard = base.dashboard
_orig_functions = base.functionalities
_orig_listing = base.listing
base.APP_CSS += SIDEBAR_CSS
base.dashboard = lambda *a, **k: patch(_orig_dashboard(*a, **k), 'CENTRAL')
base.functionalities = lambda *a, **k: patch(_orig_functions(*a, **k), 'CENTRAL')

def listing(title: str, subtitle: str, rows: list[dict[str, Any]], qra: str, kind: str) -> str:
    active = 'BOLETINS' if kind == 'bo' else 'PERÍCIAS' if kind == 'pe' else 'CENTRAL'
    return patch(_orig_listing(title, subtitle, rows, qra, kind), active)
base.listing = listing

async def start_server_v627(client: Any):
    return await v625.start_server_v625(client)

base.start_server = start_server_v627

def install(bot_module: Any):
    return base.install(bot_module)
