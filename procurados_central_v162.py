# -*- coding: utf-8 -*-
"""V162: procurados estritos pelo canal ativo + Central DICOR normal."""
from __future__ import annotations

import asyncio
import html
import re
from typing import Any, Dict, List, Set

ACTIVE_WANTED_CHANNEL_ID = 1490200533980545097


def install(bot_module) -> None:
    """Instala correções sem reescrever o bot.py gigante.

    - A lista/catálogo só aceita registros cuja mensagem existe de fato no canal
      oficial de procurados ativos.
    - A rota raiz volta a ser a Central DICOR normal (sem painel live).
    """
    state = {
        'message_ids': frozenset(),
        'ready': False,
        'last_error': '',
        'sync_task': None,
        'loop_task': None,
    }

    def _record_message_id(registro: Dict[str, Any]) -> int:
        for chave in (
            'mensagem_id', 'publicacao_mensagem_id', 'message_id',
            'discord_message_id', 'procurado_mensagem_id',
        ):
            try:
                valor = int(registro.get(chave) or 0)
                if valor:
                    return valor
            except (TypeError, ValueError):
                pass
        for chave in ('mensagem_url', 'jump_url', 'publicacao_url', 'url'):
            valor = str(registro.get(chave) or '').strip()
            if not valor:
                continue
            achados = re.findall(r'(?<!\d)(\d{15,25})(?!\d)', valor)
            if achados:
                try:
                    return int(achados[-1])
                except (TypeError, ValueError):
                    pass
        return 0

    def _invalidate_catalog_cache() -> None:
        for nome, valor in (
            ('_V17_CATALOGO_CACHE_HTML', ''),
            ('_V17_CATALOGO_CACHE_KEY', None),
        ):
            if hasattr(bot_module, nome):
                try:
                    setattr(bot_module, nome, valor)
                except Exception:
                    pass

    async def _resolve_channel():
        client = getattr(bot_module, 'bot', None)
        if client is None:
            return None
        canal = client.get_channel(ACTIVE_WANTED_CHANNEL_ID)
        if canal is not None:
            return canal
        try:
            return await client.fetch_channel(ACTIVE_WANTED_CHANNEL_ID)
        except Exception:
            return None

    async def _refresh_live_ids(reason: str = '') -> Set[int]:
        canal = await _resolve_channel()
        if canal is None or not hasattr(canal, 'history'):
            state['last_error'] = 'canal_indisponivel'
            print(
                f'⚠️ V162 procurados: canal {ACTIVE_WANTED_CHANNEL_ID} indisponível; '
                'mantendo o último snapshot válido.',
                flush=True,
            )
            return set(state['message_ids'])

        ids: Set[int] = set()
        try:
            async for mensagem in canal.history(limit=None, oldest_first=False):
                try:
                    ids.add(int(mensagem.id))
                except Exception:
                    continue
        except Exception as exc:
            state['last_error'] = f'{type(exc).__name__}: {exc}'
            print(
                f'⚠️ V162 procurados: falha ao ler canal ativo: {type(exc).__name__}: {exc}',
                flush=True,
            )
            return set(state['message_ids'])

        state['message_ids'] = frozenset(ids)
        state['ready'] = True
        state['last_error'] = ''
        _invalidate_catalog_cache()
        print(
            f'✅ V162 procurados: snapshot do canal {ACTIVE_WANTED_CHANNEL_ID} '
            f'atualizado com {len(ids)} mensagens' + (f' ({reason})' if reason else '') + '.',
            flush=True,
        )
        return ids

    def _strict_active_records() -> List[Dict[str, Any]]:
        if not state['ready']:
            return []

        ids_ativos = state['message_ids']
        try:
            registros = bot_module.carregar_procurados() or []
        except Exception:
            registros = []

        unicos: Dict[str, Dict[str, Any]] = {}
        for registro in registros if isinstance(registros, list) else []:
            if not isinstance(registro, dict):
                continue
            mensagem_id = _record_message_id(registro)
            if not mensagem_id or mensagem_id not in ids_ativos:
                continue

            rg = str(registro.get('rg') or '').strip()
            nome = str(registro.get('nome') or '').strip()
            chave = rg or nome.casefold() or str(mensagem_id)
            anterior = unicos.get(chave)
            if anterior is None:
                unicos[chave] = registro
                continue
            try:
                if int(registro.get('mensagem_id') or 0) >= int(anterior.get('mensagem_id') or 0):
                    unicos[chave] = registro
            except Exception:
                pass

        normalizar = getattr(bot_module, 'normalizar_busca', None)
        if callable(normalizar):
            return sorted(unicos.values(), key=lambda x: normalizar(str(x.get('nome') or '')))
        return sorted(unicos.values(), key=lambda x: str(x.get('nome') or '').casefold())

    def _strict_is_active(registro: Dict[str, Any]) -> bool:
        if not state['ready'] or not isinstance(registro, dict):
            return False
        mensagem_id = _record_message_id(registro)
        return bool(mensagem_id and mensagem_id in state['message_ids'])

    async def _schedule_refresh(reason: str) -> None:
        tarefa = state.get('sync_task')
        if tarefa is not None and not tarefa.done():
            return

        async def _run():
            try:
                await asyncio.sleep(0.35)
                await _refresh_live_ids(reason)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f'⚠️ V162 procurados: refresh falhou: {type(exc).__name__}: {exc}', flush=True)

        state['sync_task'] = asyncio.create_task(_run())

    async def _sync_loop() -> None:
        while True:
            try:
                await asyncio.sleep(20)
                await _refresh_live_ids('sincronização periódica')
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f'⚠️ V162 procurados: loop de sync falhou: {type(exc).__name__}: {exc}', flush=True)
                await asyncio.sleep(20)

    async def _on_ready() -> None:
        await _refresh_live_ids('on_ready')
        tarefa = state.get('loop_task')
        if tarefa is None or tarefa.done():
            state['loop_task'] = asyncio.create_task(_sync_loop())

    async def _on_message(message) -> None:
        try:
            if int(getattr(getattr(message, 'channel', None), 'id', 0) or 0) == ACTIVE_WANTED_CHANNEL_ID:
                await _schedule_refresh('nova mensagem')
        except Exception:
            pass

    async def _on_raw_message_delete(payload) -> None:
        try:
            if int(getattr(payload, 'channel_id', 0) or 0) == ACTIVE_WANTED_CHANNEL_ID:
                await _schedule_refresh('mensagem removida')
        except Exception:
            pass

    async def _on_raw_bulk_message_delete(payload) -> None:
        try:
            if int(getattr(payload, 'channel_id', 0) or 0) == ACTIVE_WANTED_CHANNEL_ID:
                await _schedule_refresh('mensagens removidas')
        except Exception:
            pass

    bot_module.PROCURADOS_CHANNEL_ID = ACTIVE_WANTED_CHANNEL_ID
    bot_module._v43_procurados_ativos = _strict_active_records
    bot_module._v43_procurado_esta_no_canal_ativo = _strict_is_active
    bot_module._V162_PROCURADOS_STATE = state
    bot_module._v162_refresh_procurados_ativos = _refresh_live_ids

    client = getattr(bot_module, 'bot', None)
    if client is not None and hasattr(client, 'add_listener'):
        client.add_listener(_on_ready, 'on_ready')
        client.add_listener(_on_message, 'on_message')
        client.add_listener(_on_raw_message_delete, 'on_raw_message_delete')
        client.add_listener(_on_raw_bulk_message_delete, 'on_raw_bulk_message_delete')

    def _central_card(icone: str, titulo: str, descricao: str, link: str, botao: str, privado: bool) -> str:
        classe = 'card private' if privado else 'card'
        return (
            f'<article class="{classe}"><div class="ico">{html.escape(icone)}</div>'
            f'<h3>{html.escape(titulo)}</h3><p>{html.escape(descricao)}</p>'
            f'<a href="{html.escape(link, quote=True)}">{html.escape(botao)}</a></article>'
        )

    async def _central_normal_http(request):
        qtd_procurados = len(_strict_active_records())
        cards = ''.join([
            _central_card('🎯', 'Procurados', f'{qtd_procurados} indivíduo(s) no canal oficial ativo.', '/catalogo', 'Abrir catálogo', False),
            _central_card('🗃️', 'Banco de Dados', 'Fichas, veículos, organizações, evidências e histórico investigativo.', '/fichas', 'Acessar banco', True),
            _central_card('🧬', 'Árvore de Inteligência', 'Conexões entre indivíduos, veículos, ocorrências e organizações.', '/arvore', 'Abrir vínculos', True),
            _central_card('📋', 'Boletins', 'Consulta dos boletins e registros operacionais.', '/boletins', 'Abrir boletins', True),
            _central_card('🧪', 'Perícias', 'Consulta de perícias e materiais vinculados.', '/pericias', 'Abrir perícias', True),
            _central_card('📂', 'Dossiês', 'Consulta centralizada dos dossiês operacionais.', '/dossies-central', 'Abrir dossiês', True),
        ])
        pagina = f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Central DICOR</title><style>
:root{{--gold:#d7a93d;--gold2:#f2d47d;--bg:#070806;--panel:#10120d;--line:#3b321a;--text:#f7f1db;--muted:#96917e}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;background:radial-gradient(circle at 50% -18%,#6f56152f,transparent 38%),var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}}
header{{min-height:104px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:center;padding:14px 5vw;background:#090a07ef}}
.brand{{display:flex;align-items:center;gap:16px;text-align:left}}.brand img{{width:74px;height:74px;object-fit:contain}}.brand h1{{font-size:19px;letter-spacing:2.2px;margin:0}}.brand small{{display:block;color:var(--gold);margin-top:5px;letter-spacing:1.2px}}
main{{max-width:1260px;margin:0 auto;padding:58px 24px 70px}}.hero{{text-align:center;max-width:820px;margin:0 auto 48px}}.eyebrow{{font-size:10px;letter-spacing:2.2px;color:var(--gold)}}.hero h2{{font-family:Georgia,serif;font-size:48px;margin:10px 0 14px}}.hero h2 span{{color:var(--gold2)}}.hero p{{color:#b9b29d;line-height:1.65;font-size:16px}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}.card{{min-height:220px;padding:26px;border:1px solid #302919;border-radius:19px;background:linear-gradient(155deg,#15170f,#0b0d09);position:relative}}.card:hover{{border-color:#8b712d;transform:translateY(-3px)}}.ico{{font-size:30px}}.card h3{{margin:20px 0 9px}}.card p{{color:#9d9783;line-height:1.55;min-height:66px}}.card a{{display:inline-flex;text-decoration:none;color:#111;background:linear-gradient(135deg,var(--gold2),var(--gold));padding:11px 15px;border-radius:9px;font-weight:900}}.private:after{{content:'ACESSO RESTRITO';position:absolute;right:16px;top:16px;color:#bfa85d;font-size:9px;border:1px solid #5b4b22;border-radius:99px;padding:5px 8px}}
footer{{text-align:center;color:#625f52;font-size:11px;padding:0 15px 45px}}@media(max-width:900px){{.grid{{grid-template-columns:1fr 1fr}}}}@media(max-width:620px){{.grid{{grid-template-columns:1fr}}.hero h2{{font-size:36px}}}}
</style></head><body><header><div class="brand"><img src="/central/brasao-dicor.png" alt="Brasão DICOR"><div><h1>CENTRAL DICOR</h1><small>INTELIGÊNCIA E COMBATE AO CRIME ORGANIZADO</small></div></div></header>
<main><section class="hero"><div class="eyebrow">PLATAFORMA OPERACIONAL</div><h2>Central de Inteligência <span>DICOR</span></h2><p>Acesso aos módulos oficiais da DICOR em uma única central. Esta é a página central normal, sem painel ao vivo.</p></section><section class="grid">{cards}</section></main><footer>DICOR • AMBIENTE FICTÍCIO DE GTA RP</footer></body></html>'''
        return bot_module.web.Response(text=pagina, content_type='text/html', charset='utf-8')

    bot_module.central_portal_http = _central_normal_http

    print(
        f'✅ V162 procurados/central: lista estrita pelo canal {ACTIVE_WANTED_CHANNEL_ID} '
        'e Central DICOR normal reativada.',
        flush=True,
    )
