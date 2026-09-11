# -*- coding: utf-8 -*-
"""Central Visual V626.

Patch visual sem alterar o fluxo do Discord nem a coleta de dados.
Reforça PF/DICOR, brasões sem caixa branca e barra lateral.
"""
from __future__ import annotations

import re
from typing import Any

import central_discord_v613 as base
import central_procurados_v625 as v625

PF_LOGO = base.PF_LOGO
DICOR_LOGO = base.DICOR_LOGO

SIDEBAR_CSS = r'''
/* V626 — barra lateral e brasões */
.side{width:252px!important;padding:18px 14px 15px!important;background:linear-gradient(180deg,#091522 0%,#07101a 48%,#05090f 100%)!important;border-right:1px solid #20384e!important;box-shadow:16px 0 40px #0005;display:flex;flex-direction:column;gap:14px;overflow:hidden}
.side:after{content:"DICOR  •  INTELIGÊNCIA\A PCPT  •  POLÍCIA CAPITAL / POLÍCIA FEDERAL\A\A SISTEMA OPERACIONAL\A ACESSO RESTRITO";white-space:pre-line;display:block;margin-top:auto;padding:14px 12px;border:1px solid #203a53;border-radius:13px;background:linear-gradient(155deg,#0b1928,#07101a);color:#637c93;font-size:7px;line-height:1.85;letter-spacing:1.2px;box-shadow:inset 0 0 24px #0b4e8513}
.side .brand,.sidebar-brand{position:relative;display:flex!important;align-items:center;gap:11px;padding:8px 7px 16px!important;border-bottom:1px solid #1d3348!important}
.brand img,.sidebar-brand img{width:55px!important;height:55px!important;object-fit:contain!important;background:transparent!important;mix-blend-mode:multiply;filter:drop-shadow(0 6px 13px #0009)}
.brand .pf-mark,.sidebar-brand .pf-mark{width:38px!important;height:38px!important;border-radius:9px;object-fit:contain;background:#07101a!important;padding:3px;box-shadow:0 0 0 1px #2a4660}
.brand-text b,.sidebar-brand b{font-size:14px;letter-spacing:2.1px}.brand-text small,.sidebar-brand small{display:block;margin-top:4px;color:#d3aa4c;font-size:7px;letter-spacing:1.8px}
.side-nav{display:flex;flex-direction:column;gap:7px}.side-title{margin:3px 5px 2px;color:#4d6b84;font-size:7px;font-weight:900;letter-spacing:1.8px}.side-link{display:flex;align-items:center;gap:10px;padding:11px 10px;border:1px solid #182d41;border-radius:10px;background:#08131f;color:#849bb0;font-size:8px;font-weight:900;letter-spacing:1px;transition:.16s}.side-link:hover{border-color:#315979;background:#0b1c2c;color:#d7e1e8;transform:translateX(2px)}.side-link.active{border-color:#775b22;background:linear-gradient(105deg,#17140c,#0a121b);color:#e4c66c}.side-ico{width:22px;height:22px;display:grid;place-items:center;border-radius:7px;background:#10283d;color:#79aedd;font-size:10px}.side-link.active .side-ico{background:#624a18;color:#f0cf70}.side-user{padding:10px;border:1px solid #1b3349;border-radius:11px;background:#08131f}.side-user .label{color:#526c84;font-size:6px;letter-spacing:1.6px}.side-user .value{margin-top:4px;color:#dce5ec;font-size:9px;font-weight:800;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.main{padding:22px 30px 48px!important}
.top{background:linear-gradient(180deg,#08121d99,#08121d00);border-bottom-color:#1d3348!important}
.hero{box-shadow:inset 0 0 90px #0e5a9818,0 15px 45px #0003!important}
.hero h1{font-size:38px!important;letter-spacing:1.4px!important}.hero p{max-width:750px}
.wanted{box-shadow:0 18px 45px #0003}.card{box-shadow:0 10px 26px #0003}.card:hover{border-color:#2c5271;transform:translateY(-2px)}
.logo,.brand img,.auth .logo{mix-blend-mode:multiply!important;background:transparent!important}
@media(max-width:900px){.side{width:auto!important;height:auto!important;position:relative!important;box-shadow:none!important}.side:after{display:none}.side-nav{display:grid;grid-template-columns:1fr 1fr}.side-title,.side-user{display:none}.main{padding:14px 13px 30px!important}}
@media(max-width:520px){.side-nav{grid-template-columns:1fr}.side-link:nth-child(n+5){display:none}.brand img{width:47px!important;height:47px!important}.main{padding-left:10px!important;padding-right:10px!important}}
'''


def enhanced_sidebar(kind: str = "CENTRAL") -> str:
    return f'''<aside class="side"><div class="brand sidebar-brand"><img src="{base.esc(DICOR_LOGO)}" alt="DICOR"><img class="pf-mark" src="{base.esc(PF_LOGO)}" alt="Polícia Federal"><div class="brand-text"><b>DICOR</b><small>INTELIGÊNCIA</small></div></div><div class="side-title">PAINEL OPERACIONAL</div><nav class="side-nav"><a class="side-link {"active" if kind=="CENTRAL" else ""}" href="/"><span class="side-ico">⌂</span>CENTRAL</a><a class="side-link {"active" if kind=="PROCURADOS" else ""}" href="/procurados"><span class="side-ico">⚠</span>PROCURADOS</a><a class="side-link {"active" if kind=="BOLETINS" else ""}" href="/boletins"><span class="side-ico">▣</span>BOLETINS</a><a class="side-link {"active" if kind=="PERÍCIAS" else ""}" href="/pericias"><span class="side-ico">⌕</span>PERÍCIAS</a><a class="side-link {"active" if kind=="FOTOS" else ""}" href="/fotos"><span class="side-ico">▧</span>FOTOS</a><a class="side-link" href="/funcionalidades"><span class="side-ico">≡</span>FUNCIONALIDADES</a></nav><div class="side-user"><div class="label">ÁREA DE ACESSO</div><div class="value">PCPT / POLÍCIA FEDERAL</div></div></aside>'''


def patch_page(html: str, kind: str) -> str:
    if '<aside class="side">' in html:
        html = re.sub(r'<aside class="side">.*?</aside>', enhanced_sidebar(kind), html, count=1, flags=re.S)
    else:
        # Páginas como Procurados/Fotos da V625/V622 eram somente main.
        html = html.replace('<div class="app"><main class="main">', '<div class="app">'+enhanced_sidebar(kind)+'<main class="main">', 1)
    return html


_ORIG_DASHBOARD = base.dashboard
_ORIG_FUNCTIONALITIES = base.functionalities
_ORIG_LISTING = base.listing


def dashboard(*args: Any, **kwargs: Any) -> str:
    return patch_page(_ORIG_DASHBOARD(*args, **kwargs), "CENTRAL")


def functionalities(*args: Any, **kwargs: Any) -> str:
    return patch_page(_ORIG_FUNCTIONALITIES(*args, **kwargs), "CENTRAL")


def listing(title: str, subtitle: str, rows: list[dict[str, Any]], qra: str, kind: str) -> str:
    active = "BOLETINS" if kind == "bo" else "PERÍCIAS" if kind == "pe" else "CENTRAL"
    return patch_page(_ORIG_LISTING(title, subtitle, rows, qra, kind), active)

base.dashboard = dashboard
base.functionalities = functionalities
base.listing = listing
base.APP_CSS += SIDEBAR_CSS

# Procurados completos da V625 usam sua própria página.
_orig_all_procurados = v625.all_procurados
async def all_procurados(req: Any):
    response = await _orig_all_procurados(req)
    if hasattr(response, "text"):
        response.text = patch_page(response.text, "PROCURADOS")
    return response
v625.all_procurados = all_procurados
v625.ApplicationPatch.__init__

# Intercepta a criação das rotas V625 para usar o handler visual novo.
_old_init = v625.ApplicationPatch.__init__
def _init(self, *args: Any, **kwargs: Any):
    _old_init(self, *args, **kwargs)
    try:
        # A rota já existe; substituí-la por uma nova rota com o mesmo caminho não é seguro.
        pass
    except Exception:
        pass
v625.ApplicationPatch.__init__ = _init

async def start_server_v626(client: Any):
    # O servidor V625 permanece responsável pelo upload, fotos e limite de body.
    return await v625.start_server_v625(client)

base.start_server = start_server_v626

def install(bot_module: Any):
    return base.install(bot_module)
