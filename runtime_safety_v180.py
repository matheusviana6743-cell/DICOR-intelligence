# -*- coding: utf-8 -*-
"""Runtime mínimo e estável do DICOR."""
from __future__ import annotations

import asyncio
import gc
import os
from collections import deque

MAX_RSS_MB = int(os.getenv("DICOR_MAX_RSS_MB", "760") or 760)
_watchdog = None
_installed = False
_patched = False


def _rss_mb():
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024.0
    except Exception:
        pass
    return 0.0


def _trim(client):
    try:
        state = getattr(client, "_connection", None)
        if state is not None:
            state.max_messages = 5
            try:
                flags_cls = __import__("discord").MemberCacheFlags
                state.member_cache_flags = flags_cls.none()
            except Exception:
                pass
            messages = getattr(state, "_messages", None)
            if messages is not None:
                state._messages = deque(list(messages)[-5:], maxlen=5)
        gc.collect()
    except Exception:
        pass


def _is_heavy(name):
    value = str(name or "").lower()
    return any(key in value for key in (
        "snapshot", "ocr", "visual", "catalog", "catalogo", "auditoria",
        "prisional", "v75-startup", "startup-escalonado", "sincroniza", "reconcilia"
    ))


def _disable_v75(bot_module):
    global _patched
    if _patched:
        return
    original = getattr(bot_module, "_v75_startup_escalonado", None)
    if not callable(original):
        return

    async def minimal_startup():
        _trim(getattr(bot_module, "bot", None))
        return None

    bot_module._V75_STARTUP_ORIGINAL = original
    bot_module._v75_startup_escalonado = minimal_startup
    _patched = True


async def _watch(client):
    global _watchdog
    try:
        while True:
            await asyncio.sleep(30)
            _trim(client)
            rss = _rss_mb()
            if rss and rss >= MAX_RSS_MB:
                current = asyncio.current_task()
                cancelled = 0
                for task in list(asyncio.all_tasks()):
                    if task is current or task.done() or task.cancelled():
                        continue
                    try:
                        name = task.get_name()
                    except Exception:
                        name = ""
                    if _is_heavy(name):
                        task.cancel()
                        cancelled += 1
                gc.collect()
                print(f"⚠️ [MEM] {rss:.1f} MB; {cancelled} tarefa(s) pesada(s) cancelada(s).", flush=True)
    except asyncio.CancelledError:
        raise
    except Exception:
        _watchdog = None


def _start_watchdog(client):
    global _watchdog
    if _watchdog is not None and not _watchdog.done():
        return
    try:
        _watchdog = asyncio.create_task(_watch(client), name="dicor-memory-watchdog")
    except Exception:
        pass


def _safe_create_task(coro, *, name=None):
    try:
        wanted = str(name or "")
        if wanted and _is_heavy(wanted):
            for task in asyncio.all_tasks():
                if task.done() or task.cancelled():
                    continue
                try:
                    if task.get_name() == wanted:
                        coro.close()
                        return task
                except Exception:
                    pass
        return asyncio.create_task(coro, name=wanted or None)
    except Exception:
        try:
            coro.close()
        except Exception:
            pass
        return None


def install(bot_module):
    global _installed
    client = getattr(bot_module, "bot", None)
    if client is None:
        return
    _trim(client)
    _disable_v75(bot_module)
    if not _installed:
        try:
            client.add_listener(lambda: _start_watchdog(client), "on_ready")
        except Exception:
            pass
        _installed = True
    bot_module._v180_safe_create_task = _safe_create_task
    bot_module._v188_runtime_minimal = True
    print(f"✅ [MEM] proteção ativa — limite {MAX_RSS_MB} MB, cache 5.", flush=True)
