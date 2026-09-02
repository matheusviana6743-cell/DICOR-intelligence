# -*- coding: utf-8 -*-
import asyncio
import os
import traceback
import bot
import dossie_v161
import dossie_v161_signatures
import procurados_central_v162
import central_pf_v163
import central_auth_v164
import central_auth_v165
import central_migration_v167
import central_buttons_rescue_v168
import interaction_fix_v169


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


def _liberar_porta_http_antes_da_central() -> None:
    """Libera o healthcheck provisório antes da Central assumir a PORT da Railway."""
    parar = getattr(bot, '_v70_parar_health_bootstrap_sync', None)
    if not callable(parar):
        return
    try:
        parar()
        print('✅ V70 healthcheck provisório encerrado; PORT liberada para a Central.', flush=True)
    except Exception as exc:
        print(f'⚠️ V70 não conseguiu liberar a PORT para a Central: {type(exc).__name__}: {exc}', flush=True)
        traceback.print_exc()


def _instalar_central_web() -> None:
    """Instala a camada HTTP da Central no contexto do event loop do Discord."""
    _liberar_porta_http_antes_da_central()

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


def _instalar_procurados_background() -> None:
    """Instala o módulo de Procurados fora do caminho crítico da porta HTTP."""
    try:
        procurados_central_v162.install(bot)
        print('V162 Procurados instalado.', flush=True)
    except Exception as exc:
        print(f'V162 falhou sem derrubar o Discord: {type(exc).__name__}: {exc}', flush=True)
        traceback.print_exc()


async def _instalar_extensoes_depois_do_ready():
    await asyncio.sleep(3)

    # A Central precisa nascer no mesmo event loop do Discord. O V162 de
    # Procurados pode continuar isolado em thread, pois não deve bloquear o
    # bind da PORT pública da Railway.
    try:
        _instalar_central_web()
    except Exception as exc:
        print(f'⚠️ Boot HTTP da Central falhou sem derrubar o Discord: {type(exc).__name__}: {exc}', flush=True)
        traceback.print_exc()

    asyncio.create_task(asyncio.to_thread(_instalar_procurados_background))


def _registrar_boot_seguro() -> None:
    """Registra extensoes pesadas como listener de READY, sem bloquear o gateway."""
    client = getattr(bot, 'bot', None)
    if client is None:
        print('AVISO: objeto Discord nao encontrado; seguindo com bot principal.', flush=True)
        return

    async def _on_ready_extensions():
        if getattr(bot, '_dicor_extensions_started', False):
            return
        bot._dicor_extensions_started = True
        print('Discord READY — iniciando extensoes da Central em segundo plano.', flush=True)
        asyncio.create_task(_instalar_extensoes_depois_do_ready())

    try:
        client.add_listener(_on_ready_extensions, 'on_ready')
    except Exception as exc:
        print(f'AVISO: nao foi possivel registrar extensoes pos-READY: {exc}', flush=True)


async def _bootstrap_discord_direto() -> None:
    """Bootstrap enxuto: conecta o Gateway Discord diretamente."""
    client = getattr(bot, 'bot', None)
    token = str(os.getenv('DISCORD_TOKEN') or getattr(bot, 'DISCORD_TOKEN', '') or '').strip()

    if client is None:
        raise RuntimeError('cliente Discord (bot.bot) nao foi encontrado')
    if not token:
        raise RuntimeError('DISCORD_TOKEN nao encontrado no ambiente')

    print('[BOOT] cliente Discord encontrado; iniciando Gateway diretamente.', flush=True)
    print('[BOOT] token presente; aguardando READY do Discord.', flush=True)
    await client.start(token, reconnect=True)


async def _main() -> None:
    try:
        if hasattr(bot, '_v70_iniciar_health_bootstrap'):
            bot._v70_iniciar_health_bootstrap()
    except Exception:
        pass

    # V169 precisa ser aplicado antes de qualquer View persistente ser criada.
    try:
        interaction_fix_v169.install(bot)
    except Exception as exc:
        print(f'⚠️ V169 falhou sem derrubar o Discord: {type(exc).__name__}: {exc}', flush=True)
        traceback.print_exc()

    try:
        central_buttons_rescue_v168.install(bot)
    except Exception as exc:
        print(f'V168 falhou sem derrubar o Discord: {type(exc).__name__}: {exc}', flush=True)
        traceback.print_exc()

    _instalar_renderer_visual_v161()
    _registrar_boot_seguro()

    client = getattr(bot, 'bot', None)
    token = str(os.getenv('DISCORD_TOKEN') or getattr(bot, 'DISCORD_TOKEN', '') or '').strip()
    if client is not None and token and callable(getattr(client, 'start', None)):
        await _bootstrap_discord_direto()
        return

    print('[BOOT] fallback para runtime_lifecycle_entrypoint.', flush=True)
    await bot._runtime_lifecycle_entrypoint()


if __name__ == '__main__':
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f'[FATAL] bootstrap do Discord encerrou: {type(exc).__name__}: {exc}', flush=True)
        traceback.print_exc()
        raise
