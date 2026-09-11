# -*- coding: utf-8 -*-
"""Central DICOR V624.

Servidor limpo baseado diretamente na Central V613.
Mantém a home PCPT/POLÍCIA FEDERAL original e adiciona somente
as rotas internas de Procurados e Banco de Fotos da V622.
"""
from __future__ import annotations

from urllib.parse import quote
from typing import Any

import central_discord_v613 as base
import central_procurados_v622 as v622

base.quote = quote

# Todas as funções novas usam o mesmo módulo-base da Central original.
v622.base = base
v622.v621.base = base
v622.v621.v620.base = base
v622.v621.v620.v616.base = base

# Mantém o coletor robusto de Procurados, mas NÃO substitui o dashboard
# original da V613 (PCPT/PF + layout interno aprovado).
base.collect_procurados = v622.collect_procurados
v622.v621.collect_procurados = v622.collect_procurados
v622.v621.v620.collect_procurados = v622.collect_procurados
v622.v621.v620.v616.collect_procurados = v622.collect_procurados

# Application extra: o servidor original da V613 continua responsável por
# login, /, /funcionalidades, /boletins, /pericias, /fichas e /arvore.
# Estas são apenas as novas rotas internas da V622.
class ApplicationPatch(base.web.Application):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.router.add_get("/procurado/{source_id}", v622.detail_route, name="v624_detail")
        self.router.add_get("/imagem-procurado/{message_id}", v622.procurado_photo, name="v624_wanted_photo")
        self.router.add_get("/fotos", v622.photos_page, name="v624_photos")
        self.router.add_get("/foto/{message_id}", v622.stable_photo, name="v624_stable_photo")
        self.router.add_post("/fotos/upload", v622.upload_photo, name="v624_upload")


async def start_server_v624(client: Any):
    v622._CLIENT = client
    original_application = base.web.Application
    base.web.Application = ApplicationPatch
    try:
        # Usa diretamente o servidor da V613. Não passa por V616/V617/V623.
        return await base.start_server(client)
    finally:
        base.web.Application = original_application


base.start_server = start_server_v624


def install(bot_module: Any):
    return base.install(bot_module)
