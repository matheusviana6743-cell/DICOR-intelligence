# -*- coding: utf-8 -*-
"""Central DICOR V624.

Correção da V623: não recarrega o módulo-base em runtime.
Mantém a home PCPT/PF original e adiciona Procurados/Fotos da V622
sem quebrar a instância da Central nem o servidor HTTP.
"""
from __future__ import annotations

from urllib.parse import quote

import central_discord_v613 as base

# Guarda a home original ANTES de carregar as camadas que fazem patches.
_ORIGINAL_DASHBOARD = getattr(base, "dashboard", None)

import central_procurados_v622 as v622

base.web.URLEncode = quote

# Todas as camadas devem compartilhar exatamente o mesmo objeto base.
v622.base = base
v622.v621.base = base
v622.v621.v620.base = base
v622.v621.v620.v616.base = base

# Restaura SOMENTE a apresentação principal. Os recursos novos continuam
# registrados pelo servidor V622.
if _ORIGINAL_DASHBOARD is not None:
    base.dashboard = _ORIGINAL_DASHBOARD
    v622.v621.dashboard = getattr(v622.v621, "dashboard_v617", _ORIGINAL_DASHBOARD)
    v622.v621.v620.v616.dashboard_v616 = _ORIGINAL_DASHBOARD

# Coleta robusta de Procurados da V622.
base.collect_procurados = v622.collect_procurados
v622.v621.collect_procurados = v622.collect_procurados
v622.v621.v620.collect_procurados = v622.collect_procurados
v622.v621.v620.v616.collect_procurados = v622.collect_procurados

# Usa o servidor V622, que já registra /procurado, /imagem-procurado,
# /fotos e /foto, sem substituir a classe CentralV613.start.
base.start_server = v622.start_server_v622


def install(bot_module):
    return base.install(bot_module)
