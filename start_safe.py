# -*- coding: utf-8 -*-
"""Launcher protegido do DICOR: Discord only."""
import asyncio, gc, json, os, traceback
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("MALLOC_ARENA_MAX", "2")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("ORT_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import bot
import bo_legacy_guard_v201
import bo_sistema_v200
import bo_painel_fix_v202
import bo_nome_guard_v203
import dossie_v210
import dossie_runtime_v212
import runtime_safety_v180


def diagnostic(context, exc):
    try:
        data_dir=Path(str(getattr(bot,"DATA_DIR",Path(__file__).parent/"data"))); data_dir.mkdir(parents=True,exist_ok=True)
        with (data_dir/"diagnostico_erros.jsonl").open("a",encoding="utf-8") as fh:
            fh.write(json.dumps({"timestamp":datetime.now(timezone.utc).isoformat(),"contexto":context,"tipo":type(exc).__name__,"erro":str(exc),"traceback":traceback.format_exc()},ensure_ascii=False)+"\n")
    except Exception: pass
    print(f"[SAFE] {context}: {type(exc).__name__}: {exc}",flush=True)


def trim_cache():
    try:
        client=getattr(bot,"bot",None); state=getattr(client,"_connection",None) if client else None
        if state is not None:
            state.max_messages=5; messages=getattr(state,"_messages",None)
            if messages is not None: state._messages=deque(list(messages)[-5:],maxlen=5)
        gc.collect()
    except Exception as exc: diagnostic("cache_trim",exc)


def install_guards():
    client=getattr(bot,"bot",None)
    if client is None: return
    tree=getattr(client,"tree",None)
    async def tree_error(interaction,error):
        diagnostic("slash_command",error)
        try:
            if not interaction.response.is_done(): await interaction.response.send_message("❌ Ocorreu um erro interno. O sistema continua online.",ephemeral=True)
            else: await interaction.followup.send("❌ Ocorreu um erro interno. O sistema continua online.",ephemeral=True)
        except Exception: pass
    if tree is not None:
        try: tree.on_error=tree_error
        except Exception as exc: diagnostic("tree_guard",exc)
    async def prefix_error(ctx,error):
        diagnostic("prefix_command",error)
        try: await ctx.send("❌ Ocorreu um erro interno. O sistema continua online.")
        except Exception: pass
    try: client.on_command_error=prefix_error
    except Exception as exc: diagnostic("prefix_guard",exc)


def install_compat():
    client=getattr(bot,"bot",None)
    if client is None or hasattr(client,"remove_view"): return
    def remove_view(view):
        try:
            store=getattr(getattr(client,"_connection",None),"_view_store",None); remover=getattr(store,"remove_view",None)
            return remover(view) if callable(remover) else None
        except Exception: return None
    try: client.remove_view=remove_view
    except Exception: pass


def _wire_dossie_pdf():
    """Porta única e protegida para geração do PDF."""
    def _safe(dados, caminho):
        return dossie_runtime_v212.gerar_pdf_seguro(bot, dados, caminho)
    bot._V159_RENDER_PDF_APROVADO = _safe
    bot._V155_GERAR_PDF_BASE = _safe
    # Algumas versões antigas do bot chamam helpers diretamente; expomos a mesma
    # porta segura nesses aliases para evitar que uma rotina bypass o fallback.
    try:
        bot._V212_GERAR_PDF_SEGURO = _safe
    except Exception:
        pass


def install_secondary():
    for name in ("stability_v184","pericia_fix_v185"):
        try: __import__(name).install(bot)
        except Exception as exc: diagnostic(name,exc)
    for name in ("procurados_central_v162","interaction_fix_v169","pericia_fix_v181","pericia_fix_v186"):
        try:
            mod=__import__(name); mod.install(bot); print(f"✅ {name} carregado após READY.",flush=True)
        except Exception as exc: diagnostic(name,exc)
    try:
        dossie_v210.install(bot)
        dossie_runtime_v212.install(bot)
        _wire_dossie_pdf()
        print("✅ Dossiê V212 ativo: qualquer falha de renderização entra em contingência e não trava o encerramento.",flush=True)
    except Exception as exc: diagnostic("dossie_runtime_v212",exc)


async def install_integrations():
    for name in ("gestao_v5","hierarquia_v7","fivemanage_media"):
        try: await __import__(name).install(bot)
        except Exception as exc: diagnostic(name,exc)


async def after_ready():
    await asyncio.sleep(3); trim_cache(); install_secondary(); await asyncio.sleep(.5); await install_integrations(); trim_cache()


async def main():
    client=getattr(bot,"bot",None); token=str(os.getenv("DISCORD_TOKEN") or getattr(bot,"DISCORD_TOKEN","")).strip()
    if client is None or not token: raise RuntimeError("cliente Discord ou DISCORD_TOKEN ausente")
    try:
        bo_legacy_guard_v201.install(bot); bo_sistema_v200.install(bot); bo_painel_fix_v202.install(bot); bo_nome_guard_v203.install(bot)
        dossie_v210.install(bot)
        dossie_runtime_v212.install(bot)
        _wire_dossie_pdf()
    except Exception as exc: diagnostic("discord_modules",exc)
    try: runtime_safety_v180.install(bot)
    except Exception as exc: diagnostic("runtime_safety",exc)
    install_guards(); install_compat(); trim_cache()
    for name in ("stability_v184","pericia_fix_v185"):
        try: __import__(name).install(bot)
        except Exception as exc: diagnostic(name,exc)
    try: import pericia_fix_v186; pericia_fix_v186.install(bot)
    except Exception as exc: diagnostic("pre_gateway_v186",exc)
    ready_once=False
    async def ready_listener():
        nonlocal ready_once
        if ready_once: return
        ready_once=True; print("✅ DISCORD READY — DICOR Discord-only ativo.",flush=True); trim_cache(); asyncio.create_task(after_ready(),name="dicor-after-ready")
    client.add_listener(ready_listener,"on_ready")
    await client.start(token,reconnect=True)

if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
    except Exception as exc: diagnostic("fatal_boot",exc); raise
