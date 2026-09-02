# -*- coding: utf-8 -*-
"""V180.1 - proteção de RAM do runtime Discord.

Mantém a lógica dos comandos intacta e reduz somente caches recriáveis.
"""
import asyncio
import gc
import logging
from collections import deque

LOG = logging.getLogger("dicor.runtime")


def _set_message_cache(client, limit=5):
    try:
        state = getattr(client, "_connection", None)
        if state is None:
            return
        try:
            state.max_messages = limit
        except Exception:
            pass
        messages = getattr(state, "_messages", None)
        if messages is not None:
            try:
                state._messages = deque(list(messages)[-limit:], maxlen=limit)
            except Exception:
                state._messages = deque(maxlen=limit)
    except Exception as exc:
        print(f"[V180] cache protection failed: {type(exc).__name__}: {exc}", flush=True)


def _set_member_cache_minimal(client):
    try:
        discord = __import__("discord")
        flags_cls = getattr(discord, "MemberCacheFlags", None)
        state = getattr(client, "_connection", None)
        if flags_cls is None or state is None:
            return
        state.member_cache_flags = flags_cls.none()
    except Exception as exc:
        print(f"[V180] member cache minimal failed: {type(exc).__name__}: {exc}", flush=True)


def _trim_recreatable_caches(client):
    try:
        _set_message_cache(client, 5)
        gc.collect()
    except Exception as exc:
        print(f"[V180] trim failed: {type(exc).__name__}: {exc}", flush=True)


def _task_done(task):
    try:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            print(f"[V180] tarefa secundária encerrada com erro: {type(exc).__name__}: {exc}", flush=True)
    except Exception:
        pass


def install(bot_module):
    client = getattr(bot_module, "bot", None)
    if client is None:
        return

    # Aplicado antes do Gateway para evitar o pico inicial de RAM.
    _set_message_cache(client, 5)
    _set_member_cache_minimal(client)

    try:
        loop = asyncio.get_event_loop()
        old_handler = loop.get_exception_handler()

        def _handler(current_loop, context):
            exc = context.get("exception")
            if exc is not None:
                print(f"[V180] exceção assíncrona isolada: {type(exc).__name__}: {exc}", flush=True)
            else:
                print(f"[V180] evento assíncrono isolado: {context.get('message', 'sem mensagem')}", flush=True)
            if old_handler is not None:
                try:
                    old_handler(current_loop, context)
                except Exception:
                    pass

        loop.set_exception_handler(_handler)
    except Exception as exc:
        print(f"[V180] event loop guard failed: {type(exc).__name__}: {exc}", flush=True)

    def safe_create_task(coro, *, name=None):
        try:
            task = asyncio.create_task(coro, name=name)
            task.add_done_callback(_task_done)
            return task
        except Exception as exc:
            print(f"[V180] create_task bloqueado: {type(exc).__name__}: {exc}", flush=True)
            try:
                coro.close()
            except Exception:
                pass
            return None

    bot_module._v180_safe_create_task = safe_create_task
    bot_module._v180_trim_message_cache = lambda: _trim_recreatable_caches(client)

    try:
        gc.collect()
    except Exception:
        pass

    print("✅ V180.1 RAM: cache de mensagens=5 + member cache mínimo + GC ativo.", flush=True)
