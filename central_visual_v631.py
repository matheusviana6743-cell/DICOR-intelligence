# -*- coding: utf-8 -*-
"""Central Visual V631 — interface oficial para PC.

Aplica o visual V630/V629/V628 já aprovado, mantendo a home PCPT/PF,
Boletins, Perícias, Procurados e Fotos. A apresentação é deliberadamente
somente desktop: não existem breakpoints responsivos nem navegação móvel.
"""
from __future__ import annotations

from typing import Any
import re

import central_visual_v630 as v630
import central_visual_v629 as v629
import central_visual_v628 as v628


def strip_media(css: str) -> str:
    """Remove blocos @media do CSS sem alterar regras normais."""
    out = []
    i = 0
    n = len(css)
    while i < n:
        m = re.search(r"@media\s*\([^{}]+\)\s*\{", css[i:], flags=re.I)
        if not m:
            out.append(css[i:])
            break
        start = i + m.start()
        open_pos = i + m.end() - 1
        out.append(css[i:start])
        depth = 0
        j = open_pos
        while j < n:
            ch = css[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        i = j
    return "".join(out)


# V630 já contém a home aprovada e os módulos. V628 contém os painéis
# operacionais de Boletins/Perícias. Removemos apenas os breakpoints móveis.
desktop_base_css = strip_media(v629.NEW_CSS)
desktop_panel_css = strip_media(v628.PANEL_CSS)

# Mantém uma largura de trabalho de desktop. Em telas estreitas o navegador
# pode rolar horizontalmente; a interface não se transforma em versão mobile.
DESKTOP_ONLY_CSS = r'''
html,body{min-width:1280px;overflow-x:auto}
body{min-height:100vh}
.app{min-width:1280px}
.central-shell{min-width:1280px}
.central-main{min-width:1100px}
/* acabamento PC */
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:#05080b}
::-webkit-scrollbar-thumb{background:#3b3017;border-radius:8px;border:2px solid #05080b}
::-webkit-scrollbar-thumb:hover{background:#67521f}
'''

# Faz a V630 trabalhar com o CSS sem qualquer regra responsiva.
v629.NEW_CSS = desktop_base_css + DESKTOP_ONLY_CSS
v628.PANEL_CSS = desktop_panel_css + DESKTOP_ONLY_CSS

# O painel de login também herda o mesmo CSS desktop.
try:
    v630.base.APP_CSS = v629.NEW_CSS
except Exception:
    pass


def install(bot_module: Any):
    return v630.install(bot_module)
