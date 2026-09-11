# -*- coding: utf-8 -*-
"""DICOR Central V630 — identidade visual final para Boletins e Perícias.

Usa a V629 como base funcional e aplica somente acabamento visual inspirado
no modelo exato DICOR arquivado: fundo escuro, linhas douradas, brasão no topo,
marca de documento reservado e cartões operacionais mais limpos.
"""
from __future__ import annotations

import central_v629 as v629

base = v629.base

VISUAL = r'''
body{background:#03070b!important}
.wrap{width:min(1340px,calc(100% - 24px));padding-top:14px}
.bar{border-color:#5d4920;background:linear-gradient(135deg,#090f16f7,#050a0ff7);box-shadow:0 25px 75px #000b,inset 0 0 45px #b7892408}
.brand img{background:transparent!important;mix-blend-mode:multiply!important;filter:drop-shadow(0 7px 15px #000a)!important}
.brand strong{font-size:12px;letter-spacing:2px}.brand span{color:#dbb458;font-size:8px;letter-spacing:2px}
.tabs{padding-top:11px}.tab{border-color:#3b4a57;background:#07101a}.tab.on{border-color:#a07b2d;background:linear-gradient(135deg,#19160d,#0c1116);color:#f1ca67}
.hero{border-color:#806326;background:linear-gradient(135deg,#111b24f7,#080f16f7 64%,#0a1016f7);box-shadow:0 25px 80px #000a,inset 0 0 90px #b8862410}
.hero:before{content:"DOCUMENTO RESERVADO • DICOR";position:absolute;right:26px;bottom:18px;color:#d4aa4e17;font-size:9px;font-weight:900;letter-spacing:2px;z-index:0}
.eyebrow{color:#e0b958!important}
.stat{border-color:#25394a;background:linear-gradient(145deg,#09121c,#060d14)}
.stat.gold b{color:#e4bd59}.stat.blue b{color:#69b8ef}.stat.green b{color:#67d49d}
.card{border-color:#273d51;background:linear-gradient(150deg,#0c1722,#050c13);box-shadow:0 18px 42px #0008}
.card:before{background:linear-gradient(#e1b954,#604915)}.card.bo:before{background:linear-gradient(#77b9e9,#28577f)}
.num{color:#f1cb67}.bo .num{color:#76bced}
.status{background:#0b2118;border-color:#377152}.preview{border-color:#20364a;background:#050c13}
.btn{background:linear-gradient(135deg,#edca65,#916619);box-shadow:0 8px 20px #8e691d18}.btn.secondary{border-color:#315471}
.detail{border-color:#725923;background:linear-gradient(145deg,#0b1620,#050c12);box-shadow:0 22px 70px #000a}
.detail h2{color:#efc965}.detail .row{border-bottom-color:#26394a}
.search input{border-color:#31516b;background:#050c13}.search button{background:linear-gradient(135deg,#efcc68,#936817)}
.foot{color:#5c543f}
@media(max-width:600px){.brand img{width:44px;height:44px}.brand strong{font-size:9px;letter-spacing:1.4px}.brand span{font-size:6.8px}.hero:before{display:none}}
'''

v629.CSS += VISUAL
v629.base.DICOR_LOGO = getattr(v629.base, "DICOR_LOGO", "")


def install(bot_module):
    return v629.install(bot_module)
