# -*- coding: utf-8 -*-
"""Sistema de BO V200.

Processamento automático independente do legado: detecta BOs na origem,
cria tópico privado no atendimento, preserva anexos, usa rodízio existente,
grava no mesmo banco de atendimentos e reinicia a numeração por mês.
"""
import asyncio
import re
import traceback
from datetime import datetime

import discord
from discord.ui import Button, View

SOURCE_ID = 1490200514837745754
TARGET_ID = 1525762770253910136

_installed = False
_recovery_task = None
_locks = set()
_botmod = None


def _text(message):
    try:
        return _botmod.coletar_texto_embed(message) or message.content or ""
    except Exception:
        return message.content or ""


def _short(numero):
    try:
        return _botmod.numero_curto_boletim(numero)
    except Exception:
        m = re.search(r"(\d{1,8})$", str(numero or ""))
        return m.group(1).zfill(3) if m else str(numero or "")


def _month_from_date(value):
    text = str(value or "")
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
    if m:
        return f"{m.group(2)}/{m.group(3)}"
    return ""


def _month(message):
    try:
        meta = _botmod._v104_bo_meta_mensagem(message)
        found = _month_from_date(meta.get("data"))
        if found:
            return found
    except Exception:
        pass
    try:
        return message.created_at.strftime("%m/%Y")
    except Exception:
        return ""


def _item_month(item):
    return _month_from_date(item.get("data_bo_original")) or _month_from_date(item.get("data_criacao"))


def _records():
    try:
        return list(_botmod.carregar_atendimentos_boletins() or [])
    except Exception:
        return []


def _find_message(message_id):
    for item in _records():
        if str(item.get("mensagem_original_id")) == str(message_id):
            return item
    return None


def _find_monthly(numero, month):
    short = _short(numero)
    for item in _records():
        if _short(item.get("numero")) == short and _item_month(item) == month:
            return item
    return None


def _next_monthly(month):
    values = []
    for item in _records():
        if _item_month(item) != month:
            continue
        m = re.search(r"(\d{1,8})$", str(item.get("numero") or ""))
        if m:
            values.append(int(m.group(1)))
    return f"{(max(values) + 1 if values else 1):03d}"


def _numero(message):
    try:
        value = _botmod.extrair_numero_boletim_seguro(_text(message))
    except Exception:
        value = ""
    if value:
        return value
    short = _next_monthly(_month(message))
    return f"BO-DICOR-{datetime.now().strftime('%Y%m%d')}-{short}"


def _valid(message):
    try:
        return bool(_botmod.eh_boletim_valido_para_atendimento(message))
    except Exception:
        text = _text(message).lower()
        return "boletim de ocorrencia" in text or "boletim de ocorrência" in text


async def _channel(guild):
    channel = guild.get_channel(TARGET_ID)
    if channel is None:
        try:
            channel = await guild.fetch_channel(TARGET_ID)
        except Exception:
            channel = None
    return channel


async def _members(guild, agent):
    members = {}
    if isinstance(agent, discord.Member) and not agent.bot:
        members[agent.id] = agent
    try:
        for member in _botmod._membros_inspetor_mais_boletim(guild):
            members[member.id] = member
    except Exception:
        pass
    return list(members.values())


async def _choose_agent(guild, numero):
    try:
        return await _botmod.escolher_agente_rodizio(guild, numero)
    except Exception:
        try:
            valid = _botmod.membros_agentes_validos(guild)
            return valid[0] if valid else None
        except Exception:
            return None


async def _send_files(thread, message, numero):
    try:
        folder = _botmod.BOLETIM_ARQUIVOS_DIR / str(numero).replace("/", "-")
        files = await _botmod.arquivos_para_reenvio_de_mensagens([message], folder, numero)
        if files:
            await _botmod.enviar_arquivos_em_lotes(thread, files, "📎 Provas e anexos do boletim")
        return files
    except Exception as exc:
        try:
            await _botmod.enviar_log(f"⚠️ V200 anexos BO {numero}: {type(exc).__name__}: {exc}")
        except Exception:
            pass
        return []


def _embed(numero, message, agent, text, original):
    embed = discord.Embed(title="📋 BOLETIM DE OCORRÊNCIA", description=text[:3900] or "Sem texto.")
    embed.add_field(name="Número", value=f"`{_short(numero)}`", inline=True)
    embed.add_field(name="Responsável", value=agent.mention if agent else "Nenhum agente elegível", inline=True)
    embed.add_field(name="Autor", value=message.author.mention if message.author else "Não identificado", inline=True)
    embed.add_field(name="Recebido em", value=discord.utils.format_dt(message.created_at, "F"), inline=False)
    embed.add_field(name="Boletim original", value=original, inline=False)
    embed.set_footer(text="DICOR • Atendimento de Boletim")
    return embed


async def _create(message):
    guild = message.guild
    if guild is None:
        return None
    numero = _numero(message)
    month = _month(message)
    if not month:
        return None
    if _find_message(message.id) or _find_monthly(numero, month):
        return None
    parent = await _channel(guild)
    if not isinstance(parent, discord.TextChannel):
        raise RuntimeError(f"canal de atendimento {TARGET_ID} não é um canal de texto")
    agent = await _choose_agent(guild, numero)
    title = f"📋 BOLETIM DE OCORRÊNCIA — Nº {_short(numero)}"
    thread = await parent.create_thread(
        name=title[:100],
        type=discord.ChannelType.private_thread,
        invitable=False,
        auto_archive_duration=10080,
        reason=f"DICOR V200 • BO {numero}",
    )
    for member in await _members(guild, agent):
        try:
            await thread.add_user(member)
        except Exception as exc:
            try:
                await _botmod.enviar_log(f"⚠️ V200 acesso BO {numero} para {member.id}: {exc}")
            except Exception:
                pass
    text = _text(message) or "Sem texto."
    await thread.send(
        content=(agent.mention if agent else None),
        embed=_embed(numero, message, agent, text, message.jump_url),
        allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
    )
    files = await _send_files(thread, message, numero)
    now = _botmod.agora_br() if hasattr(_botmod, "agora_br") else datetime.now().strftime("%d/%m/%Y %H:%M")
    atendimento = {
        "id": f"ATD-{message.id}",
        "numero": numero,
        "numero_original_texto": _botmod.extrair_numero_boletim_seguro(_text(message)) if hasattr(_botmod, "extrair_numero_boletim_seguro") else numero,
        "mensagem_original_id": message.id,
        "mensagem_original_url": message.jump_url,
        "canal_origem_id": SOURCE_ID,
        "area_id": thread.id,
        "thread_id": thread.id,
        "canal_atendimento_id": parent.id,
        "topico_privado": True,
        "agente_id": agent.id if agent else None,
        "agente_nome": str(agent) if agent else "Nenhum agente elegível",
        "agente_atribuido_por": "RODIZIO_AUTOMATICO",
        "agente_atribuido_em": now,
        "autor_id": message.author.id if message.author else None,
        "autor_nome": str(message.author) if message.author else "Não identificado",
        "status": "EM ATENDIMENTO" if agent else "SEM AGENTE ELEGÍVEL",
        "data_criacao": now,
        "data_bo_original": message.created_at.strftime("%d/%m/%Y"),
        "mes_bo": month,
        "anexos_salvos": [str(p) for p in files],
        "painel_msg_id": None,
        "comparecimento_status": "não solicitado",
        "procurado_status": "não solicitado",
        "historico": [{"acao": "Tópico privado criado automaticamente", "usuario": "Sistema", "agente_id": agent.id if agent else None, "data": now}],
    }
    records = _records()
    records.append(atendimento)
    _botmod.salvar_atendimentos_boletins(records)
    panel = await thread.send(view=BoletimAtendimentoV200())
    atendimento["painel_msg_id"] = panel.id
    _botmod.atualizar_atendimento_boletim("id", atendimento["id"], atendimento)
    try:
        await _botmod.alertar_coincidencias_novo_boletim(message, atendimento)
    except Exception:
        pass
    try:
        await _botmod.enviar_log(f"📋 V200 BO aberto automaticamente | BO `{numero}` | mês `{month}` | tópico `{thread.id}` | agente `{agent.id if agent else 0}`")
    except Exception:
        pass
    return atendimento


class BoletimAtendimentoV200(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Escolher Agente", emoji="👤", style=discord.ButtonStyle.primary, custom_id="dicor_bo_v200_escolher")
    async def escolher(self, interaction: discord.Interaction, button: Button):
        try:
            if not _botmod.usuario_e_administrador(interaction.user):
                return await interaction.response.send_message("❌ Somente Inspetor, Vice-Diretor ou Diretor pode escolher o agente.", ephemeral=True)
            atendimento = await _botmod.garantir_atendimento_interaction(interaction)
            if not atendimento:
                return await interaction.response.send_message("❌ Atendimento não encontrado.", ephemeral=True)
            agentes = _botmod.membros_agentes_validos(interaction.guild)
            if not agentes:
                return await interaction.response.send_message("❌ Nenhum agente válido encontrado.", ephemeral=True)
            await interaction.response.send_message("Selecione o agente responsável:", view=_botmod.SelecionarAgenteBoletimView(atendimento.get("id"), agentes), ephemeral=True)
        except Exception as exc:
            await _error(interaction, exc)

    @discord.ui.button(label="Finalizar Boletim", emoji="✅", style=discord.ButtonStyle.success, custom_id="dicor_bo_v200_finalizar")
    async def finalizar(self, interaction: discord.Interaction, button: Button):
        try:
            atendimento = await _botmod.garantir_atendimento_interaction(interaction)
            if not atendimento:
                return await interaction.response.send_message("❌ Atendimento não encontrado.", ephemeral=True)
            if atendimento.get("status") == "FINALIZADO":
                return await interaction.response.send_message("⚠️ Este boletim já foi finalizado.", ephemeral=True)
            await interaction.response.send_modal(_botmod.FinalizarBoletimAtendimentoModal())
        except Exception as exc:
            await _error(interaction, exc)

    @discord.ui.button(label="Solicitar Comparecimento", emoji="📩", style=discord.ButtonStyle.secondary, custom_id="dicor_bo_v200_comparecimento")
    async def comparecimento(self, interaction: discord.Interaction, button: Button):
        try:
            atendimento = await _botmod.garantir_atendimento_interaction(interaction)
            if not atendimento or not atendimento.get("agente_id"):
                return await interaction.response.send_message("⚠️ Escolha um agente antes de solicitar o mandado.", ephemeral=True)
            await interaction.response.send_modal(_botmod.ComparecimentoBoletimModal())
        except Exception as exc:
            await _error(interaction, exc)

    @discord.ui.button(label="Cadastrar como Procurado", emoji="🚨", style=discord.ButtonStyle.danger, custom_id="dicor_bo_v200_procurado")
    async def procurado(self, interaction: discord.Interaction, button: Button):
        try:
            atendimento = await _botmod.garantir_atendimento_interaction(interaction)
            if not atendimento:
                return await interaction.response.send_message("❌ Atendimento não encontrado.", ephemeral=True)
            texto = ""
            try:
                origem = interaction.guild.get_channel(int(atendimento.get("canal_origem_id") or SOURCE_ID))
                if origem:
                    msg = await origem.fetch_message(int(atendimento.get("mensagem_original_id")))
                    texto = _botmod.coletar_texto_embed(msg)
            except Exception:
                pass
            await interaction.response.send_modal(_botmod.ProcuradoBoletimModal(_botmod.extrair_dados_procurado_de_texto(texto)))
        except Exception as exc:
            await _error(interaction, exc)


async def _error(interaction, exc):
    traceback.print_exc()
    try:
        await _botmod.enviar_log(f"❌ V200 erro em interação BO: {type(exc).__name__}: {exc}")
    except Exception:
        pass
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Ocorreu um erro interno no atendimento do BO.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Ocorreu um erro interno no atendimento do BO.", ephemeral=True)
    except Exception:
        pass


async def process(message):
    if int(getattr(message.channel, "id", 0) or 0) != SOURCE_ID or not _valid(message):
        return False
    key = int(message.id)
    if key in _locks:
        return False
    _locks.add(key)
    try:
        numero = _numero(message)
        month = _month(message)
        if not month or _find_message(key) or _find_monthly(numero, month):
            return False
        await _create(message)
        print(f"✅ V200: BO processado | origem={key} | numero={numero} | mes={month}", flush=True)
        return True
    except Exception as exc:
        traceback.print_exc()
        try:
            await _botmod.enviar_log(f"❌ V200 falha ao abrir BO `{_numero(message)}`: {type(exc).__name__}: {exc}")
        except Exception:
            pass
        return False
    finally:
        _locks.discard(key)


async def _recover():
    await asyncio.sleep(5)
    try:
        for guild in list(getattr(_botmod.bot, "guilds", []) or []):
            channel = guild.get_channel(SOURCE_ID)
            if channel is None:
                continue
            async for message in channel.history(limit=3000, oldest_first=True):
                await process(message)
        print(f"✅ V200: recuperação automática concluída | origem={SOURCE_ID} | destino={TARGET_ID}", flush=True)
    except Exception as exc:
        traceback.print_exc()


def install(botmod):
    global _installed, _botmod
    _botmod = botmod
    if _installed:
        return
    _installed = True
    client = botmod.bot
    try:
        client.add_view(BoletimAtendimentoV200())
    except Exception:
        pass
    @client.listen("on_message")
    async def _v200_message(message):
        await process(message)
    @client.listen("on_ready")
    async def _v200_ready():
        global _recovery_task
        if _recovery_task is None or _recovery_task.done():
            _recovery_task = asyncio.create_task(_recover(), name="dicor-bo-v200-recovery")
    botmod._V200_BO_PROCESS = process
    botmod._V200_BO_VIEW = BoletimAtendimentoV200
    print(f"✅ V200 BO reescrito instalado | origem={SOURCE_ID} | destino={TARGET_ID} | reset mensal ativo", flush=True)
