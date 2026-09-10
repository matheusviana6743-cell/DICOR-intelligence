# -*- coding: utf-8 -*-
"""DICOR V601 - ingestão automática de BO e Perícia.

Responsabilidade única: observar os dois canais de entrada, recuperar mensagens
perdidas durante deploy/restart e garantir que cada mensagem de entrada gere seu
tópico uma única vez.

O processamento NÃO ignora mensagens de bots/webhooks: os canais de entrada
podem receber registros encaminhados por automações.
"""
from __future__ import annotations

import asyncio
import traceback
from typing import Any, Awaitable, Callable, Optional

import discord

SOURCE_BO_ID = 1490200514837745754
SOURCE_PERICIA_ID = 1490200524367200297
SCAN_INTERVAL = 20
SCAN_LIMIT = 250


class AutomaticIngest:
    def __init__(self, bot_module: Any):
        self.bot_module = bot_module
        self.client = getattr(bot_module, "bot", None)
        self._seen_runs: set[int] = set()
        self._locks: set[tuple[str, int]] = set()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def _channel(self, guild: discord.Guild, channel_id: int):
        channel = guild.get_channel(channel_id)
        if channel is not None:
            return channel
        try:
            return await self.client.fetch_channel(channel_id)
        except Exception:
            return None

    async def _process_with_core(self, kind: str, message: discord.Message) -> None:
        if not message.guild:
            return
        key = (kind, int(message.id))
        if key in self._locks:
            return
        self._locks.add(key)
        try:
            if kind == "bo":
                fn = getattr(self.bot_module, "_v600_auto_process_bo", None)
            else:
                fn = getattr(self.bot_module, "_v600_auto_process_pericia", None)
            if not callable(fn):
                return
            await fn(message)
        except Exception as exc:
            print(f"❌ V601 {kind}: falha na mensagem {message.id}: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
        finally:
            self._locks.discard(key)

    async def scan_once(self, guild: discord.Guild) -> None:
        for channel_id, kind in ((SOURCE_BO_ID, "bo"), (SOURCE_PERICIA_ID, "pericia")):
            channel = await self._channel(guild, channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                async for message in channel.history(limit=SCAN_LIMIT, oldest_first=False):
                    await self._process_with_core(kind, message)
            except Exception as exc:
                print(f"⚠️ V601 scanner {kind}/{channel_id}: {type(exc).__name__}: {exc}", flush=True)

    async def recovery(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            await asyncio.sleep(2)
            for guild in list(getattr(self.client, "guilds", []) or []):
                await self.scan_once(guild)
            print("✅ V601: recuperação inicial de BO + Perícia concluída.", flush=True)
            while True:
                await asyncio.sleep(SCAN_INTERVAL)
                for guild in list(getattr(self.client, "guilds", []) or []):
                    await self.scan_once(guild)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"❌ V601 scanner principal: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
        finally:
            self._running = False

    async def on_message(self, message: discord.Message) -> None:
        if not message.guild:
            return
        channel_id = int(getattr(message.channel, "id", 0) or 0)
        # Não usamos message.author.bot como filtro: BOs/Perícias podem chegar
        # por webhook/bot. O canal de origem é a fronteira de segurança.
        if channel_id == SOURCE_BO_ID:
            await self._process_with_core("bo", message)
        elif channel_id == SOURCE_PERICIA_ID:
            await self._process_with_core("pericia", message)

    def start(self) -> None:
        if self.client is None:
            raise RuntimeError("cliente Discord indisponível")
        # As funções reais continuam no V600; este componente apenas garante
        # que toda mensagem nova e toda mensagem perdida cheguem ao núcleo.
        if not hasattr(self.client, "_dicor_v601_ingest"):
            self.client._dicor_v601_ingest = self
            self.client.add_listener(self.on_message, "on_message")
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.recovery(), name="dicor-v601-auto-ingest")


def install(bot_module: Any) -> None:
    ingest = AutomaticIngest(bot_module)
    # Expõe os processadores do V600 para o componente de ingestão.
    client = getattr(bot_module, "bot", None)
    if client is None:
        raise RuntimeError("cliente Discord indisponível")
    client._dicor_v601_ingest = ingest
    ingest.start()
    print("✅ V601: ingestão automática BO + Perícia ativa; mensagens de bot/webhook também são processadas.", flush=True)
