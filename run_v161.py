# -*- coding: utf-8 -*-
"""Bootstrap estável do DICOR."""
import os

os.environ.setdefault("MALLOC_ARENA_MAX", "2")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("ORT_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import asyncio
import gc
import json
import traceback
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import bot
import dossie_v161
import dossie_v161_signatures
import central_pf_v163
import central_auth_v164
import central_auth_v165
import central_migration_v167
import central_buttons_rescue_v168
import interaction_fix_v169
import gestao_v3
import hierarquia_dicor


def _diagnostico_erro(contexto, error):
    try:
        data_dir = Path(str(getattr(bot, 'DATA_DIR', Path(__file__).parent / 'data')))
        data_dir.mkdir(parents=True, exist_ok=True)
        caminho = data_dir / 'diagnostico_erros.jsonl'
        registro = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'contexto': str(contexto),
            'tipo': type(error).__name__,
            'erro': str(error),
            'traceback': traceback.format_exc(),
        }
        with caminho.open('a', encoding='utf-8') as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + '\n')
        print(f'🚨 [AUTO-DIAGNOSTICO] {contexto} | {type(error).__name__}: {error}', flush=True)
    except Exception as log_error:
        print(f'⚠️ [AUTO-DIAGNOSTICO] falhou ao salvar erro: {type(log_error).__name__}: {log_error}', flush=True)


def _limitar_cache_discord():
    try:
        client = getattr(bot, 'bot', None)
        state = getattr(client, '_connection', None) if client else None
        mensagens = getattr(state, '_messages', None) if state else None
        if mensagens is not None:
            limite = 50
            state._messages = deque(list(mensagens)[-limite:], maxlen=limite)
            print(f'✅ CACHE DISCORD limitado a {limite} mensagens.', flush=True)
    except Exception as exc:
        _diagnostico_erro('discord_cache_limit', exc)


def _manutencao_memoria():
    try:
        gc.collect()
        _limitar_cache_discord()
    except Exception as exc:
        _diagnostico_erro('memory_maintenance', exc)


def _iniciar_manutenção_memoria():
    async def _loop():
        while True:
            await asyncio.sleep(90)
            _manutencao_memoria()
    try:
        asyncio.create_task(_loop())
        print('✅ V90 memory governor ativo.', flush=True)
    except Exception as exc:
        _diagnostico_erro('memory_governor_start', exc)


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
        _diagnostico_erro('slash_command', error)
        try:
            if interaction.response and not interaction.response.is_done():
                await interaction.response.send_message('❌ Erro no comando. O sistema continua online.', ephemeral=True)
            else:
                await interaction.followup.send('❌ Erro no comando. O sistema continua online.', ephemeral=True)
        except Exception as response_error:
            _diagnostico_erro('slash_command_response', response_error)

    if tree is not None:
        try:
            tree.on_error = _tree_error
            print('✅ COMMAND GUARD + AUTO-DIAGNOSTICO ativo.', flush=True)
        except Exception as exc:
            _diagnostico_erro('command_guard_install', exc)

    if client is not None:
        async def _prefix_error(context, error):
            _diagnostico_erro('prefix_command', error)
            try:
                await context.send('❌ Erro no comando. O sistema continua online.')
            except Exception as response_error:
                _diagnostico_erro('prefix_command_response', response_error)

        try:
            client.on_command_error = _prefix_error
        except Exception as exc:
            _diagnostico_erro('prefix_guard_install', exc)

        try:
            original_on_error = getattr(client, 'on_error', None)

            async def _safe_on_error(event_method, *args, **kwargs):
                try:
                    if original_on_error is not None:
                        await original_on_error(event_method, *args, **kwargs)
                except Exception as exc:
                    _diagnostico_erro(f'discord_event:{event_method}', exc)

            client.on_error = _safe_on_error
        except Exception as exc:
            _diagnostico_erro('event_guard_install', exc)


def _liberar_porta_http_antes_da_central():
    parar = getattr(bot, '_v70_parar_health_bootstrap_sync', None)
    if callable(parar):
        try:
            parar()
            print('✅ V70 healthcheck provisório encerrado; PORT liberada para a Central.', flush=True)
        except Exception as exc:
            _diagnostico_erro('release_health_port', exc)


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
            _diagnostico_erro(nome, exc)
            print(f'⚠️ {nome} falhou isoladamente: {type(exc).__name__}: {exc}', flush=True)


async def _instalar_discord_dicor():
    """Instala Gestão V3 e a hierarquia após o READY.

    A Gestão V3 não publica painel automaticamente. A hierarquia é mantida
    somente no canal próprio de HIERARQUIA.
    """
    try:
        await gestao_v3.install(bot)
        print('✅ Gestão DICOR V3 instalada — sem publicação automática de painel.', flush=True)
    except Exception as exc:
        _diagnostico_erro('gestao_v3', exc)

    try:
        await hierarquia_dicor.install(bot)
        print('✅ Hierarquia DICOR instalada.', flush=True)
    except Exception as exc:
        _diagnostico_erro('hierarquia_dicor', exc)


async def _publicar_central_http():
    start = getattr(bot, 'start_web_server', None)
    if not callable(start):
        _diagnostico_erro('central_http_missing', RuntimeError('start_web_server ausente'))
        return False
    try:
        await start()
        if getattr(bot, '_WEB_RUNNER_DICOR', None) is None:
            _diagnostico_erro('central_http_runner_missing', RuntimeError('Central iniciou sem registrar _WEB_RUNNER_DICOR'))
            return False
        print(f'✅ CENTRAL DICOR REATIVADA — porta {getattr(bot, "PORT", os.getenv("PORT", "8000"))}.', flush=True)
        return True
    except Exception as exc:
        _diagnostico_erro('central_http', exc)
        print(f'❌ CENTRAL HTTP isolada: {type(exc).__name__}: {exc}', flush=True)
        return False


async def _instalar_extensoes_depois_do_ready():
    await asyncio.sleep(8)
    _manutencao_memoria()
    await _instalar_discord_dicor()
    try:
        _instalar_central_web()
    except Exception as exc:
        _diagnostico_erro('boot_central', exc)
    await _publicar_central_http()


def _registrar_boot_seguro():
    client = getattr(bot, 'bot', None)
    if client is None:
        return

    async def _on_ready_extensions():
        if getattr(bot, '_dicor_extensions_started', False):
            return
        bot._dicor_extensions_started = True
        print('Discord READY — Gateway protegido; iniciando componentes web/Discord isolados.', flush=True)
        _limitar_cache_discord()
        _iniciar_manutenção_memoria()
        asyncio.create_task(_instalar_extensoes_depois_do_ready())

    try:
        client.add_listener(_on_ready_extensions, 'on_ready')
    except Exception as exc:
        _diagnostico_erro('ready_listener', exc)


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
    except Exception as exc:
        _diagnostico_erro('health_bootstrap', exc)

    _instalar_guardas_discord()

    for nome, modulo in (
        ('V169', interaction_fix_v169),
        ('V168', central_buttons_rescue_v168),
    ):
        try:
            modulo.install(bot)
        except Exception as exc:
            _diagnostico_erro(nome, exc)

    try:
        _instalar_renderer_visual_v161()
    except Exception as exc:
        _diagnostico_erro('V161', exc)

    _registrar_boot_seguro()
    _manutencao_memoria()

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
        _diagnostico_erro('fatal_bootstrap', exc)
        print(f'[FATAL] bootstrap encerrou: {type(exc).__name__}: {exc}', flush=True)
        raise
