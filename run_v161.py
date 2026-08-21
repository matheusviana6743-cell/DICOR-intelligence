# -*- coding: utf-8 -*-
import asyncio
import bot
import dossie_v161
import dossie_v161_signatures
import procurados_central_v162
import central_pf_v163


def _instalar_renderer_visual_v161() -> None:
    """Conecta o layout V161 ao fluxo real de fechamento V159/V160."""
    # Regra oficial: a página final possui somente as assinaturas dos dois delegados.
    # Passamos o módulo do bot para o renderer conseguir usar as imagens reais cadastradas.
    dossie_v161_signatures.install(dossie_v161, bot)
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

    print('✅ V163 visual conectado ao fechamento real V159/V160.', flush=True)


def _instalar_correcao_procurados_e_central() -> None:
    """Mantém filtro estrito de procurados e aplica a Central PF V163 por último."""
    procurados_central_v162.install(bot)
    central_pf_v163.install(bot)


if __name__ == '__main__':
    try:
        if hasattr(bot, '_v70_iniciar_health_bootstrap'):
            bot._v70_iniciar_health_bootstrap()
    except Exception:
        pass

    _instalar_renderer_visual_v161()
    _instalar_correcao_procurados_e_central()
    asyncio.run(bot._runtime_lifecycle_entrypoint())
