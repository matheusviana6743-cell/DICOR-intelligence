# -*- coding: utf-8 -*-
"""V187 - estabilidade de RAM/event-loop sem alterar comandos."""
from __future__ import annotations
import asyncio, gc, os
from collections import deque

_MAX_RSS_MB=int(os.getenv('DICOR_MAX_RSS_MB','760') or 760)
_watchdog=None
_installed=False

def _rss_mb():
    try:
        with open('/proc/self/status',encoding='utf-8') as f:
            for line in f:
                if line.startswith('VmRSS:'): return float(line.split()[1])/1024
    except Exception: pass
    return 0.0

def _cache(client):
    try:
        state=getattr(client,'_connection',None)
        if state is None:return
        state.max_messages=5
        msgs=getattr(state,'_messages',None)
        if msgs is not None: state._messages=deque(list(msgs)[-5:],maxlen=5)
    except Exception: pass

def _heavy(name):
    s=str(name or '').lower()
    return any(x in s for x in ('snapshot','ocr','visual','catalog','catalogo','auditoria','prisional','background','v75-startup','startup-escalonado','sincroniza','reconcilia'))

async def _watch(client):
    global _watchdog
    try:
        while True:
            await asyncio.sleep(20)
            _cache(client); gc.collect()
            rss=_rss_mb()
            if rss and rss>=_MAX_RSS_MB:
                n=0; cur=asyncio.current_task()
                for t in list(asyncio.all_tasks()):
                    if t is cur or t.done() or t.cancelled(): continue
                    try:name=t.get_name()
                    except Exception:name=''
                    if _heavy(name): t.cancel(); n+=1
                gc.collect()
                print(f'⚠️ V187 RAM alta: {rss:.1f} MB; {n} tarefa(s) pesada(s) interrompida(s).',flush=True)
    except asyncio.CancelledError: raise
    except Exception as e:
        print(f'⚠️ V187 watchdog: {type(e).__name__}: {e}',flush=True)
        _watchdog=None

def _ready(client):
    global _watchdog
    if _watchdog is not None and not _watchdog.done(): return
    try:_watchdog=asyncio.create_task(_watch(client),name='v187-memory-watchdog')
    except Exception: pass

def install(bot_module):
    global _installed
    client=getattr(bot_module,'bot',None)
    if client is None:return
    _cache(client)
    try:
        loop=asyncio.get_event_loop(); old=loop.get_exception_handler()
        def handler(lp,ctx):
            exc=ctx.get('exception')
            if exc: print(f'⚠️ V187 async: {type(exc).__name__}: {exc}',flush=True)
            if old:
                try: old(lp,ctx)
                except Exception: pass
        loop.set_exception_handler(handler)
    except Exception: pass
    if not _installed:
        try: client.add_listener(lambda:_ready(client),'on_ready')
        except Exception: pass
        _installed=True
    def safe_create_task(coro,*,name=None):
        try:
            desired=str(name or '')
            if desired and _heavy(desired):
                for t in asyncio.all_tasks():
                    if t.done() or t.cancelled(): continue
                    try: tn=t.get_name()
                    except Exception: tn=''
                    if tn==desired:
                        try:coro.close()
                        except Exception:pass
                        return t
            return asyncio.create_task(coro,name=desired or None)
        except Exception:
            try:coro.close()
            except Exception:pass
            return None
    bot_module._v180_safe_create_task=safe_create_task
    bot_module._v180_trim_message_cache=lambda:_cache(client)
    print(f'✅ V187 runtime safety ativo — RAM limite={_MAX_RSS_MB} MB, cache=5.',flush=True)
