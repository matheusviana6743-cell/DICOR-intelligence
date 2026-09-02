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


def _instalar_renderer_visual_v161():
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


def _instalar_guardas_discord():
    client = getattr(bot, 'bot', None)
    tree = getattr(client, 'tree', None) if client else None
    async def _tree_error(interaction, error):
        print(f'⚠️ [COMMAND GUARD] {type(error).__name__}: {error}', flush=True)
        try:
            if interaction.response and not interaction.response.is_done():
                await interaction.response.send_message('❌ Erro no comando. O sistema continua online.', ephemeral=True)
            elif interaction.followup:
                await interaction.followup.send('❌ Erro no comando. O sistema continua online.', ephemeral=True)
        except Exception:
            pass
    if tree is not None:
        try:
            tree.on_error = _tree_error
            print('✅ COMMAND GUARD ativo.', flush=True)
        except Exception as exc:
            print(f'⚠️ COMMAND GUARD: {type(exc).__name__}: {exc}', flush=True)
    if client is not None:
        async def _prefix_error(context, error):
            print(f'⚠️ [PREFIX GUARD] {type(error).__name__}: {error}', flush=True)
            try:
                await context.send('❌ Erro no comando. O sistema continua online.')
            except Exception:
                pass
        try:
            client.on_command_error = _prefix_error
        except Exception:
            pass


def _liberar_porta_http_antes_da_central():
    parar = getattr(bot, '_v70_parar_health_bootstrap_sync', None)
    if callable(parar):
        try:
            parar()
            print('✅ V70 healthcheck provisório encerrado; PORT liberada para a Central.', flush=True)
        except Exception as exc:
            print(f'⚠️ V70 não conseguiu liberar a PORT: {type(exc).__name__}: {exc}', flush=True)


def _instalar_central_web():
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
            print(f'⚠️ {nome} falhou isoladamente: {type(exc).__name__}: {exc}', flush=True)
            traceback.print_exc()


async def _publicar_central_http():
    """Usa o servidor web consolidado do bot; não cria um segundo AppRunner."""
    start = getattr(bot, 'start_web_server', None)
    if not callable(start):
        print('❌ CENTRAL: start_web_server ausente.', flush=True)
        return False
    try:
        await start()
        runner = getattr(bot, '_WEB_RUNNER_DICOR', None)
        if runner is None:
            print('⚠️ CENTRAL: servidor não registrou _WEB_RUNNER_DICOR.', flush=True)
            return False
        print(f'✅ CENTRAL DICOR REATIVADA — porta {getattr(bot, "PORT", os.getenv("PORT", "8000"))} — dados existentes preservados.', flush=True)
        return True
    except Exception as exc:
        print(f'❌ CENTRAL HTTP isolada: {type(exc).__name__}: {exc}', flush=True)
        traceback.print_exc()
        return False


def _instalar_procurados_background():
    try:
        procurados_central_v162.install(bot)
        print('V162 Procurados instalado.', flush=True)
    except Exception as exc:
        print(f'V162 falhou isoladamente: {type(exc).__name__}: {exc}', flush=True)
        traceback.print_exc()


async def _instalar_extensoes_depois_do_ready():
    await asyncio.sleep(3)
    try:
        _instalar_central_web()
    except Exception as exc:
        print(f'⚠️ Boot Central isolado: {type(exc).__name__}: {exc}', flush=True)
        traceback.print_exc()
    await _publicar_central_http()
    asyncio.create_task(asyncio.to_thread(_instalar_procurados_background))


def _registrar_boot_seguro():
    client = getattr(bot, 'bot', None)
    if client is None:
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
        print(f'⚠️ Listener Central: {type(exc).__name__}: {exc}', flush=True)


async def _bootstrap_discord_direto():
    client = getattr(bot, 'bot', None)
    token = str(os.getenv('DISCORD_TOKEN') or getattr(bot, 'DISCORD_TOKEN', '') or '').strip()
    if client is None:
        raise RuntimeError('cliente Discord não encontrado')
    if not token:
        raise RuntimeError('DISCORD_TOKEN não encontrado')
    print('[BOOT] cliente Discord encontrado; iniciando Gateway diretamente.', flush=True)
    await client.start(token, reconnect=True)


async def _main():
    try:
        if hasattr(bot, '_v70_iniciar_health_bootstrap'):
            bot._v70_iniciar_health_bootstrap()
    except Exception:
        pass
    _instalar_guardas_discord()
    try:
        interaction_fix_v169.install(bot)
    except Exception as exc:
        print(f'⚠️ V169 isolado: {type(exc).__name__}: {exc}', flush=True)
    try:
        central_buttons_rescue_v168.install(bot)
    except Exception as exc:
        print(f'⚠️ V168 isolado: {type(exc).__name__}: {exc}', flush=True)
    _instalar_renderer_visual_v161()
    _registrar_boot_seguro()
    client = getattr(bot, 'bot', None)
    token = str(os.getenv('DISCORD_TOKEN') or getattr(bot, 'DISCORD_TOKEN', '') or '').strip()
    if client is not None and token:
        await _bootstrap_discord_direto()
    else:
        print('[BOOT] fallback para runtime_lifecycle_entrypoint.', flush=True)
        await bot._runtime_lifecycle_entrypoint()


if __name__ == '__main__':
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f'[FATAL] bootstrap encerrou: {type(exc).__name__}: {exc}', flush=True)
        traceback.print_exc()
        raise
