# -*- coding: utf-8 -*-
"""DICOR V306: integração do novo gerador com o template real já versionado."""
from pathlib import Path

def install(bot_module):
    import dossie_v305
    # O template aprovado já está versionado no repositório como base64.
    dossie_v305.TEMPLATE_FILE = "dicor_template_v302.b64"
    # Garante que a interface usada pelo fluxo de fechamento seja a do V305.
    bot_module._V159_RENDER_PDF_APROVADO = lambda dados, caminho: dossie_v305.gerar_pdf_dossie(bot_module, dados, caminho)
    bot_module._V155_GERAR_PDF_BASE = lambda dados, caminho: dossie_v305.gerar_pdf_dossie(bot_module, dados, caminho)
    print("✅ V306 patch: V305 ligado ao template visual aprovado e ao fechamento da mesa.", flush=True)
