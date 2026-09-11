# -*- coding: utf-8 -*-
"""Proteção de recuperação do DICOR V606.

O Core V605 varria todo o histórico do canal. Isso fazia um restart/redeploy
reabrir BOs muito antigos. Este módulo mantém o gatilho imediato do Core, mas
substitui SOMENTE a rotina de recuperação por uma janela curta e segura.
"""
from __future__ import annotations

import asyncio
import os
import types
from datetime import datetime, timedelta, timezone
from typing import Any

import discord

RECOVERY_HOURS = max(0.25, float(os.getenv("DICOR_RECOVERY_HOURS", "2")))
RECOVERY_LIMIT = max(50, int(os.getenv("DICOR_RECOVERY_LIMIT", "500")))


def install(core: Any) -> Any:
    if getattr(core, "_dicor_recovery_guard_v606", False):
        return core

    async def safe_recover(self: Any, kind: str, channel_id: int) -> tuple[int, int]:
        channel = await self.channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return 0, 0

        cutoff = datetime.now(timezone.utc) - timedelta(hours=RECOVERY_HOURS)
        recent: list[discord.Message] = []
        seen = 0
        created = 0

        try:
            # Mais recente primeiro para podar o histórico imediatamente.
            async for message in channel.history(limit=RECOVERY_LIMIT, oldest_first=False):
                seen += 1
                created_at = message.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at < cutoff:
                    break
                recent.append(message)

            # Processa em ordem cronológica, preservando o comportamento do
            # gatilho imediato e deixando a deduplicação do Core decidir.
            for message in reversed(recent):
                if await self.create_attendance(kind, message):
                    created += 1
        except Exception as exc:
            await self.log(self.client, f"⚠️ V606 recovery {kind}: {type(exc).__name__}: {exc}") if hasattr(self, "log") else None

        return seen, created

    core.recover_channel = types.MethodType(safe_recover, core)
    core._dicor_recovery_guard_v606 = True
    print(f"🛡️ DICOR Recovery Guard V606 ativo | janela={RECOVERY_HOURS:g}h | sem varredura histórica", flush=True)
    return core
