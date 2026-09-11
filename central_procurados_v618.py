# -*- coding: utf-8 -*-
"""Shim V618 para a Central de Procurados V617."""
from urllib.parse import quote

import central_procurados_v617 as v617

# A base V613/V616 pode não expor URLEncode/quote; garante o helper usado
# pela rota interna de detalhes sem alterar a arquitetura existente.
v617.base.quote = quote

install = v617.install
start_server_v617 = v617.start_server_v617
