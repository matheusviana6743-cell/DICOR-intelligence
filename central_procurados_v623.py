# -*- coding: utf-8 -*-
"""Central DICOR V623.

Restaura a home completa da Central V613/PCPT e mantém os recursos
novos de Procurados e Banco de Fotos da V622.
"""
from __future__ import annotations

import importlib
from urllib.parse import quote

import central_discord_v613 as base
import central_procurados_v622 as v622

# V622 substituiu a home da Central pela tela focada em Procurados.
# Recarregamos apenas o módulo-base para recuperar a home completa,
# preservando login, funcionalidades, BO, Perícias e o visual PCPT/DICOR.
importlib.reload(base)
base.web.URLEncode = quote

# Reaplica a coleta robusta de Procurados da V622 depois do reload do módulo-base.
base.collect_procurados = v622.collect_procurados
v622.base = base
v622.v621.base = base
v622.v621.collect_procurados = v622.collect_procurados
v622.v621.v620.collect_procurados = v622.collect_procurados
v622.v621.v620.v616.collect_procurados = v622.collect_procurados

# O servidor V616 continua sendo usado para preservar todas as rotas da
# Central, mas sua home passa a usar a dashboard original V613.
v622.v621.v620.v616.base = base
v622.v621.v620.v616.dashboard_v616 = base.dashboard

# V622 continua registrando internamente /procurado, /imagem-procurado,
# /fotos e /foto através do ApplicationPatch.
base.start_server = v622.start_server_v622


def install(bot_module):
    return base.install(bot_module)
