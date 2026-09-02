# -*- coding: utf-8 -*-
"""V180 - proteção de runtime do Discord.

Objetivo: reduzir picos de RAM antes do Gateway e impedir que exceções de
 tarefas secundárias derrubem o processo. Não altera a lógica dos comandos.
"""
import asyncio
import gc
import logging
from collections import deque

LOG = logging.getLogger("dicor.runtime")


def _set_message_cache(client, limit=25):
    try:
        state = getattr(client, "_connection", None)
        if state is None:
            return
        # discord.py usa max_messages para controlar o deque interno.
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

    # Deve acontecer ANTES do Gateway, não apenas depois do READY.
    _set_message_cache(client, 25)

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

    # Expõe um helper para callbacks que criam tarefas.
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
    bot_module._v180_trim_message_cache = lambda: _set_message_cache(client, 25)

    try:
        gc.collect()
    except Exception:
        pass

    print("✅ V180 runtime safety ativo — cache Discord limitado antes do Gateway.", flush=True)
