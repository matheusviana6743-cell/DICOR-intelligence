# -*- coding: utf-8 -*-
import asyncio
import bot
import dossie_v161
import dossie_v161_signatures


def _instalar_renderer_visual_v161() -> None:
    """Conecta o layout V161 ao fluxo real de fechamento V159/V160."""
    # Regra oficial: a página final possui somente as assinaturas dos dois delegados.
    dossie_v161_signatures.install(dossie_v161)
    dossie_v161.install(bot)

    def _render_v161(dados, caminho):
        preparador = getattr(bot, '_v160_preparar_dados_pdf', None)
        if callable(preparador):
            dados = preparador(dados)
        return dossie_v161.gerar_pdf_dossie(bot, dados, caminho)

    # O fechamento atual (V159/V160) chama este renderer diretamente.
    if hasattr(bot, '_V159_RENDER_PDF_APROVADO'):
        bot._V159_RENDER_PDF_APROVADO = _render_v161

    # Mantem tambem o caminho legado/watchdog apontando para o mesmo layout.
    if hasattr(bot, '_V155_GERAR_PDF_BASE'):
        bot._V155_GERAR_PDF_BASE = _render_v161

    print('✅ V161 visual conectado ao fechamento real V159/V160.', flush=True)


if __name__ == '__main__':
    try:
        if hasattr(bot, '_v70_iniciar_health_bootstrap'):
            bot._v70_iniciar_health_bootstrap()
    except Exception:
        pass

    _instalar_renderer_visual_v161()
    asyncio.run(bot._runtime_lifecycle_entrypoint())
