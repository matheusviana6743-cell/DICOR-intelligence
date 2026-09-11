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

# Guarda a função ORIGINAL antes de qualquer patch.
_ORIGINAL_START_SERVER = base.start_server

import central_procurados_v622 as v622

base.web.URLEncode = quote
v622.base = base
v622.v621.base = base
v622.v621.v620.base = base
v622.v621.v620.v616.base = base

# Somente o coletor de Procurados é substituído.
base.collect_procurados = v622.collect_procurados
v622.v621.collect_procurados = v622.collect_procurados
v622.v621.v620.collect_procurados = v622.collect_procurados
v622.v621.v620.v616.collect_procurados = v622.collect_procurados

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
        # Chama a função original V613, evitando V616/V617/V622 e evitando recursão.
        return await _ORIGINAL_START_SERVER(client)
    finally:
        base.web.Application = original_application

base.start_server = start_server_v624

def install(bot_module: Any):
    return base.install(bot_module)
