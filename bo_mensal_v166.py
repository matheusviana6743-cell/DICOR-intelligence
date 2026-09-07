# -*- coding: utf-8 -*-
"""BO mensal: origem fixa, numeração reiniciada por mês e abertura imediata."""
import asyncio
import contextvars
import re
import traceback


def install(botmod):
    client = getattr(botmod, "bot", None)
    if client is None:
        return

    SOURCE = 1490200514837745754
    TARGET = 1525762770253910136
    month_ctx = contextvars.ContextVar("dicor_bo_month_v166", default="")

    # Desliga listeners de recuperação antigos que poderiam duplicar BOs.
    async def _disabled(*args, **kwargs):
        return None
    if hasattr(botmod, "_v165_bo_processar_bo"):
        botmod._v165_bo_processar_bo = _disabled
    if hasattr(botmod, "_v165_processar_bo"):
        botmod._v165_processar_bo = _disabled
    if hasattr(botmod, "_v165_recuperar_boletins_sem_atendimento"):
        botmod._v165_recuperar_boletins_sem_atendimento = lambda: {"analisados": 0, "ja_abertos": 0, "abertos": 0, "falhas": 0}

    old_search = getattr(botmod, "buscar_atendimento_por_numero", None)

    def month_of_message(message):
        try:
            meta = botmod._v104_bo_meta_mensagem(message)
            data = str(meta.get("data") or "")
            m = re.search(r"(\d{2})/(\d{2})/(\d{4})", data)
            if m:
                return f"{m.group(2)}/{m.group(3)}"
        except Exception:
            pass
        try:
            return message.created_at.strftime("%m/%Y")
        except Exception:
            return ""

    def month_of_item(item):
        for key in ("data_bo_original", "data_criacao"):
            data = str(item.get(key) or "")
            m = re.search(r"(\d{2})/(\d{2})/(\d{4})", data)
            if m:
                return f"{m.group(2)}/{m.group(3)}"
        return ""

    def search_month(numero, month):
        short = botmod.numero_curto_boletim(numero)
        for item in botmod.carregar_atendimentos_boletins():
            if botmod.numero_curto_boletim(str(item.get("numero") or "")) == short and month_of_item(item) == month:
                return item
        return None

    def monthly_search(numero):
        month = str(month_ctx.get() or "")
        if month:
            return search_month(numero, month)
        return old_search(numero) if callable(old_search) else None

    botmod.buscar_atendimento_por_numero = monthly_search

    async def target_has_bo(guild, numero, month):
        try:
            target = guild.get_channel(TARGET) or await client.fetch_channel(TARGET)
            if target is None:
                return False
            short = botmod.numero_curto_boletim(numero)
            channels = list(getattr(target, "channels", []) or [])
            if not channels and getattr(target, "category", None):
                channels = list(getattr(target.category, "channels", []) or [])
            if getattr(target, "name", None):
                channels.append(target)
            for ch in channels:
                name = str(getattr(ch, "name", "") or "")
                if short.lower() not in name.lower():
                    continue
                m = re.search(r"(\d{2})-(\d{2})-(\d{4})", name)
                if m and f"{m.group(2)}/{m.group(3)}" == month:
                    return True
                cid = str(getattr(ch, "id", ""))
                for item in botmod.carregar_atendimentos_boletins():
                    if str(item.get("area_id") or item.get("canal_atendimento_id") or "") == cid:
                        if botmod.numero_curto_boletim(str(item.get("numero") or "")) == short and month_of_item(item) == month:
                            return True
        except Exception:
            pass
        return False

    async def process(message):
        try:
            if int(getattr(message.channel, "id", 0) or 0) != SOURCE:
                return False
            if not botmod.eh_boletim_valido_para_atendimento(message):
                return False
            texto = botmod._pericia_texto_mensagem(message)
            numero = botmod.extrair_numero_boletim_seguro(texto)
            if not numero:
                return False
            month = month_of_message(message)
            if not month:
                return False
            if botmod.buscar_atendimento_por_mensagem(int(message.id)) is not None:
                return False
            if search_month(numero, month) is not None:
                return False
            if message.guild and await target_has_bo(message.guild, numero, month):
                return False
            lock_id = int(message.id)
            if lock_id in botmod.boletins_processando:
                return False
            botmod.boletins_processando.add(lock_id)
            token = month_ctx.set(month)
            try:
                if search_month(numero, month) is not None:
                    return False
                atendimento = await botmod.criar_area_atendimento_boletim(message)
                if atendimento:
                    print(f"🛟 V166: BO {numero} aberto | mês={month} | origem={message.id} | destino={atendimento.get('area_id') or atendimento.get('thread_id')}", flush=True)
                    return True
            finally:
                month_ctx.reset(token)
                botmod.boletins_processando.discard(lock_id)
        except Exception as exc:
            traceback.print_exc()
            try:
                await botmod.enviar_log(f"❌ V166 erro BO: {type(exc).__name__}: {exc}")
            except Exception:
                pass
        return False

    @client.listen("on_message")
    async def _v166_on_message(message):
        await process(message)

    async def recover():
        await asyncio.sleep(8)
        try:
            channel = client.get_channel(SOURCE) or await client.fetch_channel(SOURCE)
            if channel is None:
                return
            seen = set()
            async for message in channel.history(limit=3000, oldest_first=True):
                if not botmod.eh_boletim_valido_para_atendimento(message):
                    continue
                numero = botmod.extrair_numero_boletim_seguro(botmod._pericia_texto_mensagem(message))
                month = month_of_message(message)
                if not numero or not month:
                    continue
                key = f"{month}|{botmod.numero_curto_boletim(numero)}"
                if key in seen:
                    continue
                seen.add(key)
                await process(message)
            print(f"✅ V166: recuperação mensal concluída | ch={SOURCE} | destino={TARGET}", flush=True)
        except Exception as exc:
            traceback.print_exc()

    @client.listen("on_ready")
    async def _v166_on_ready():
        await recover()

    botmod._V166_BO_MENSAL_PROCESS = process
    print(f"✅ V166 BO mensal instalado | origem={SOURCE} | destino={TARGET}", flush=True)
