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

    print('V161 visual conectado.', flush=True)


def _instalar_extensoes_central() -> None:
    """Instala a Central somente depois que o Discord estiver conectado.

    A inicializacao do bot nao pode depender de leitura de historico, scans de
    canais ou inicializacao de paginas web. Se uma extensao falhar, o Discord
    continua online e o erro fica isolado no log.
    """
    try:
        procurados_central_v162.install(bot)
        print('V162 Procurados instalado.', flush=True)
    except Exception as exc:
        print(f'V162 falhou sem derrubar o Discord: {type(exc).__name__}: {exc}', flush=True)
        traceback.print_exc()

    for nome, modulo in (
        ('V163 Central PF', central_pf_v163),
        ('V164 autenticação Central', central_auth_v164),
        ('V165 autenticação Central', central_auth_v165),
        ('V167 migração Central', central_migration_v167),
    ):
        try:
            modulo.install(bot)
            print(f'{nome} instalado.', flush=True)
        except Exception as exc:
            print(f'{nome} falhou sem derrubar o Discord: {type(exc).__name__}: {exc}', flush=True)
            traceback.print_exc()


async def _instalar_extensoes_depois_do_ready():
    """Espera o READY do Discord e só entao instala os modulos da Central."""
    await asyncio.sleep(3)
    await asyncio.to_thread(_instalar_extensoes_central)



def _registrar_boot_seguro() -> None:
    """Registra extensoes pesadas como listener de READY, sem bloquear o boot."""
    client = getattr(bot, 'bot', None)
    if client is None:
        print('AVISO: objeto Discord nao encontrado; seguindo com bot principal.', flush=True)
        return

    async def _on_ready_extensions():
        # Cada reconexao pode disparar READY novamente. O lock evita instalar
        # os mesmos patches varias vezes.
        if getattr(bot, '_dicor_extensions_started', False):
            return
        bot._dicor_extensions_started = True
        print('Discord READY — iniciando extensoes da Central em segundo plano.', flush=True)
        asyncio.create_task(_instalar_extensoes_depois_do_ready())

    try:
        client.add_listener(_on_ready_extensions, 'on_ready')
    except Exception as exc:
        print(f'AVISO: nao foi possivel registrar extensoes pos-READY: {exc}', flush=True)


if __name__ == '__main__':
    try:
        if hasattr(bot, '_v70_iniciar_health_bootstrap'):
            bot._v70_iniciar_health_bootstrap()
    except Exception:
        pass

    # Tudo que for necessario para o Discord iniciar fica fora da Central.
    # Assim, uma falha de web/migracao nao pode deixar o bot offline.
    _instalar_renderer_visual_v161()
    _registrar_boot_seguro()

    asyncio.run(bot._runtime_lifecycle_entrypoint())
