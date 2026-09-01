# -*- coding: utf-8 -*-
import asyncio
import traceback
import bot
import dossie_v161
import dossie_v161_signatures
import procurados_central_v162
import central_pf_v163
import central_auth_v164
import central_auth_v165
import central_migration_v167


def _instalar_renderer_visual_v161() -> None:
    """Conecta o layout V161 ao fluxo real de fechamento V159/V160."""
    dossie_v161_signatures.install(dossie_v161, bot)
    dossie_v161.install(bot)

    def _render_v161(dados, caminho):
        preparador = getattr(bot, '_v160_preparar_dados_pdf', None)
        if callable(preparador):
            dados = preparador(dados)
        return dossie_v161.gerar_pdf_dossie(bot, dados, caminho)

    if hasattr(bot, '_V159_RENDER_PDF_APROVADO'):
        bot._V159_RENDER_PDF_APROVADO = _render_v161
    if hasattr(bot, '_V155_GERAR_PDF_BASE'):
        bot._V155_GERAR_PDF_BASE = _render_v161

    print('✅ V165 visual conectado ao fechamento real V159/V160.', flush=True)


def _instalar_correcao_procurados_e_central() -> None:
    """Mantém o bot principal independente da migração pesada do Discord."""
    procurados_central_v162.install(bot)
    central_pf_v163.install(bot)
    central_auth_v164.install(bot)
    central_auth_v165.install(bot)

    # V166 foi retirado do boot principal porque sua rotina de histórico pode
    # consumir o loop de eventos por muito tempo e fazer os botões do Discord
    # expirarem sem resposta. A Central V167 continua disponível e usa o
    # arquivo de migração já existente quando houver um.
    try:
        central_migration_v167.install(bot)
        print('✅ V167 integração da migração instalada sem bloquear o Discord.', flush=True)
    except Exception as exc:
        print(
            f'⚠️ V167 integração não instalada; bot principal preservado: '
            f'{type(exc).__name__}: {exc}',
            flush=True,
        )
        traceback.print_exc()


if __name__ == '__main__':
    try:
        if hasattr(bot, '_v70_iniciar_health_bootstrap'):
            bot._v70_iniciar_health_bootstrap()
    except Exception:
        pass

    _instalar_renderer_visual_v161()
    _instalar_correcao_procurados_e_central()
    asyncio.run(bot._runtime_lifecycle_entrypoint())
