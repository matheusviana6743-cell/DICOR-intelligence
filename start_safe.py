# -*- coding: utf-8 -*-
"""Entrada segura do DICOR.

Instala a proteção de runtime antes de abrir o Gateway do Discord.
"""
import asyncio
import gc
import os

# Limita paralelismo de bibliotecas nativas antes dos imports do bot.
os.environ.setdefault("MALLOC_ARENA_MAX", "2")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("ORT_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import bot
import runtime_safety_v180
import run_v161

runtime_safety_v180.install(bot)
gc.collect()


if __name__ == "__main__":
    try:
        asyncio.run(run_v161._main())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"[FATAL] start_safe encerrou: {type(exc).__name__}: {exc}", flush=True)
        raise
