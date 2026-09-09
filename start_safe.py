# -*- coding: utf-8 -*-
"""Entrypoint de produção do DICOR com boot protegido."""
import asyncio
import gc
import json
import os
import traceback
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
import runtime_safety_v180


def diagnostic(context, exc):
    try:
        data_dir = Path(str(getattr(bot, "DATA_DIR", Path(__file__).parent / "data")))
        data_dir.mkdir(parents=True, exist_ok=True)
        with (data_dir / "diagnostico_erros.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "contexto": context, "tipo": type(exc).__name__, "erro": str(exc), "traceback": traceback.format_exc()}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    print(f"[SAFE] {context}: {type(exc).__name__}: {exc}", flush=True)


def trim_cache():
    try:
        client = getattr(bot, "bot", None)
        state = getattr(client, "_connection", None) if client else None
        if state is not None:
            state.max_messages = 5
            messages = getattr(state, "_messages", None)
            if messages is not None:
                state._messages = deque(list(messages)[-5:], maxlen=5)
        gc.collect()
    except Exception as exc: diagnostic("cache_trim", exc)


def install_guards():
    client = getattr(bot, "bot", None)
    if client is None: return
    tree = getattr(client, "tree", None)
    async def tree_error(interaction, error):
        diagnostic("slash_command", error)
        try:
            if not interaction.response.is_done(): await interaction.response.send_message("❌ Ocorreu um erro interno. O sistema continua online.", ephemeral=True)
            else: await interaction.followup.send("❌ Ocorreu um erro interno. O sistema continua online.", ephemeral=True)
        except Exception as exc: diagnostic("slash_error_response", exc)
    if tree is not None:
        try: tree.on_error = tree_error
        except Exception as exc: diagnostic("tree_guard", exc)
    async def prefix_error(ctx, error):
        diagnostic("prefix_command", error)
        try: await ctx.send("❌ Ocorreu um erro interno. O sistema continua online.")
        except Exception as exc: diagnostic("prefix_error_response", exc)
    try: client.on_command_error = prefix_error
    except Exception as exc: diagnostic("prefix_guard", exc)


def install_compat():
    client = getattr(bot, "bot", None)
    if client is None or hasattr(client, "remove_view"): return
    def remove_view(view):
        try:
            store = getattr(getattr(client, "_connection", None), "_view_store", None)
            remover = getattr(store, "remove_view", None)
            if callable(remover): return remover(view)
        except Exception as exc: diagnostic("remove_view_compat", exc)
        return None
    try: client.remove_view = remove_view
    except Exception as exc: diagnostic("remove_view_install", exc)


def lazy_install_secondary():
    for module_name, context in (("stability_v184", "pre_ready_v184"), ("pericia_fix_v185", "pre_ready_v185")):
        try:
            module = __import__(module_name); module.install(bot)
        except Exception as exc: diagnostic(context, exc)
    installers = (("dossie_v161", "dossie_v161", "dossie_v161_signatures", "lazy_dossie"), ("procurados_central_v162", "procurados_central_v162", None, "lazy_procurados"), ("interaction_fix_v169", "interaction_fix_v169", None, "lazy_v169"), ("central_buttons_rescue_v168", "central_buttons_rescue_v168", None, "lazy_v168"), ("pericia_fix_v181", "pericia_fix_v181", None, "lazy_v181"), ("pericia_fix_v186", "pericia_fix_v186", None, "lazy_v186"))
    for _, module_name, companion, context in installers:
        try:
            module = __import__(module_name)
            if companion:
                companion_module = __import__(companion); companion_module.install(module, bot)
            module.install(bot); print(f"✅ {module_name} carregado após READY.", flush=True)
        except Exception as exc: diagnostic(context, exc)
    try:
        import dossie_v161
        if hasattr(bot, "_V159_RENDER_PDF_APROVADO") and getattr(bot, "_V159_RENDER_PDF_APROVADO", None) is None: bot._V159_RENDER_PDF_APROVADO = lambda dados, caminho: dossie_v161.gerar_pdf_dossie(bot, dados, caminho)
        if hasattr(bot, "_V155_GERAR_PDF_BASE") and getattr(bot, "_V155_GERAR_PDF_BASE", None) is None: bot._V155_GERAR_PDF_BASE = lambda dados, caminho: dossie_v161.gerar_pdf_dossie(bot, dados, caminho)
    except Exception as exc: diagnostic("lazy_v161_renderer", exc)


async def lazy_install_central():
    try:
        import central_pf_v163, central_auth_v164, central_auth_v165, central_migration_v167
        for module in (central_pf_v163, central_auth_v164, central_auth_v165, central_migration_v167):
            try: module.install(bot)
            except Exception as exc: diagnostic(f"central_{module.__name__}", exc)
        for module_name in ("central_data_v172", "central_data_v173"):
            try:
                module = __import__(module_name); installer = getattr(module, "install", None)
                if callable(installer): installer(bot)
            except Exception as exc: diagnostic(module_name, exc)
    except Exception as exc: diagnostic("central_imports", exc)
    try:
        start = getattr(bot, "start_web_server", None)
        if callable(start):
            result = start()
            if hasattr(result, "__await__"): await result
    except Exception as exc: diagnostic("central_http", exc)


async def install_new_integrations():
    for module_name, context in (("gestao_v5", "gestao_v5"), ("hierarquia_v7", "hierarquia_v7"), ("fivemanage_media", "fivemanage_media")):
        try:
            module = __import__(module_name); await module.install(bot)
        except Exception as exc: diagnostic(context, exc)


async def after_ready():
    await asyncio.sleep(3); trim_cache(); lazy_install_secondary(); await asyncio.sleep(0.5); await install_new_integrations(); await lazy_install_central()
    for module_name, context in (("stability_v184", "post_v184"), ("pericia_fix_v185", "post_v185")):
        try: __import__(module_name).install(bot)
        except Exception as exc: diagnostic(context, exc)
    try:
        import pericia_fix_v186
        pericia_fix_v186.install(bot)
        repair = getattr(bot, "_V186_REPAIR_EXISTING_PERICIA", None); client = getattr(bot, "bot", None); topic = client.get_channel(1541978969035771916) if client else None
        if callable(repair) and not bool(getattr(topic, "archived", False)): await repair()
    except Exception as exc: diagnostic("post_v186_repair", exc)
    trim_cache()


async def main():
    client = getattr(bot, "bot", None); token = str(os.getenv("DISCORD_TOKEN") or getattr(bot, "DISCORD_TOKEN", "")).strip()
    if client is None or not token: raise RuntimeError("cliente Discord ou DISCORD_TOKEN ausente")
    try:
        bo_legacy_guard_v201.install(bot)
        bo_sistema_v200.install(bot)
    except Exception as exc: diagnostic("V200_bo_sistema", exc)
    try: runtime_safety_v180.install(bot)
    except Exception as exc: diagnostic("V180", exc)
    install_guards(); install_compat(); trim_cache()
    for module_name, context in (("stability_v184", "pre_gateway_v184"), ("pericia_fix_v185", "pre_gateway_v185")):
        try: __import__(module_name).install(bot)
        except Exception as exc: diagnostic(context, exc)
    try:
        import pericia_fix_v186; pericia_fix_v186.install(bot)
    except Exception as exc: diagnostic("pre_gateway_v186", exc)
    try:
        import gestao_v5; await gestao_v5.install(bot)
    except Exception as exc: diagnostic("pre_gateway_gestao_v5", exc)
    ready_once = False
    async def ready_listener():
        nonlocal ready_once
        if ready_once: return
        ready_once = True; print("✅ DISCORD READY — modo protegido ativo.", flush=True); trim_cache(); asyncio.create_task(after_ready(), name="dicor-after-ready")
    client.add_listener(ready_listener, "on_ready")
    await client.start(token, reconnect=True)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
    except Exception as exc: diagnostic("fatal_boot", exc); raise
