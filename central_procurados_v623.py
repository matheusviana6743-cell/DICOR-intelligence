# -*- coding: utf-8 -*-
"""Central DICOR V623.

Restaura a home PCPT/DICOR da Central base e mantém Procurados/Fotos da V622.
"""
from __future__ import annotations

import importlib
from urllib.parse import quote

import central_discord_v613 as base
import central_procurados_v622 as v622

# Recarrega somente o módulo-base para recuperar exatamente a home/login,
# sem deixar V616/V622 substituírem a apresentação principal.
importlib.reload(base)
base.web.URLEncode = quote

# O servidor V622 adiciona as rotas novas e usa o servidor V616 por baixo.
# Todas as referências compartilhadas passam a apontar para o base recarregado.
v622.base = base
v622.v621.base = base
v622.v621.v620.base = base
v622.v621.v620.v616.base = base

# Mantém o coletor robusto de Procurados da V622.
base.collect_procurados = v622.collect_procurados
v622.v621.collect_procurados = v622.collect_procurados
v622.v621.v620.collect_procurados = v622.collect_procurados
v622.v621.v620.v616.collect_procurados = v622.collect_procurados

# A rota / da camada V616 chama dashboard_v616 diretamente.
# Substituímos apenas essa função pelo dashboard original do base.
v622.v621.v620.v616.dashboard_v616 = base.dashboard

# A CentralV613 original captura a função global start_server no módulo base.
# Por isso o atributo base.start_server sozinho não basta: substituímos o
# método start da classe para chamar explicitamente o servidor V622.
_original_start = base.CentralV613.start

async def _start_v623(self):
    if self.runner is not None:
        return
    self.runner = await v622.start_server_v622(self.client)
    self.task = __import__("asyncio").create_task(base.refresh_loop(self.client))

base.CentralV613.start = _start_v623


def install(bot_module):
    return base.install(bot_module)
