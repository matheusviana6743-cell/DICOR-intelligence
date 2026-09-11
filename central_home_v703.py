# -*- coding: utf-8 -*-
"""DICOR Central V703 - ajuste visual final sobre a Central aprovada."""
from __future__ import annotations

import central_home_v702 as v702
import central_home_v700 as v700

# URL persistente do brasão DICOR usado no projeto. Mantém o brasão visível
# mesmo que a variável antiga DICOR_LOGO_URL esteja apontando para a marca d'água.
DICOR_CREST_URL = "https://media.discordapp.net/attachments/1426821172237963375/1547778833866817596/image.png?format=png&quality=lossless&width=512&height=512"
v700.LOGO = DICOR_CREST_URL

# A Central não exibe indicadores técnicos Discord/Gmail no painel principal.
def _status_chips() -> str:
    return ""

v702._status_chips = _status_chips
v702.v700.LOGO = DICOR_CREST_URL
v702.v700.DICOR_LOGO_URL = DICOR_CREST_URL

# Remove a faixa técnica caso o renderer consulte o nome antigo.
def status_chip() -> str:
    return ""

if hasattr(v702, "status_chip"):
    v702.status_chip = status_chip

# O renderer da V702 já mantém exatamente a composição visual aprovada:
# cabeçalho, hero à esquerda, brasão à direita, módulos e áreas inferiores.
# Este módulo só corrige o asset do brasão e remove os chips técnicos.
def install(bot_module):
    return v702.install(bot_module)
