# -*- coding: utf-8 -*-
"""DICOR V205 — camada de abertura/visibilidade do atendimento de BO.

Mantém toda a lógica do V200 e corrige o principal problema observado:
threads privados eram criados, mas podiam ficar invisíveis porque nenhum
usuário humano era efetivamente adicionado quando o rodízio não encontrava
agente elegível.

A camada também:
- adiciona o autor humano da mensagem de origem;
- adiciona membros elegíveis encontrados pelo módulo principal;
- faz fallback para membros com permissão de gerência de threads/canais;
- envia um aviso de diagnóstico quando a thread foi criada sem membros;
- não altera a numeração, banco, painel ou demais funcionalidades do V200.
"""
from __future__ import annotations

import discord
import bo_sistema_v200 as core

_INSTALLED = False


async def _safe_add(thread, member):
    try:
        if member and not member.bot:
            await thread.add_user(member)
            return True
    except Exception as exc:
        try:
            await core._botmod.enviar_log(
                f"⚠️ V205: não foi possível adicionar {getattr(member, 'id', 0)} ao BO {thread.id}: {type(exc).__name__}: {exc}"
            )
        except Exception:
            pass
    return False


async def _add_members_v205(thread, guild, agent, source_message=None):
    added = set()

    async def add(member):
        if not member or member.bot or member.id in added:
            return
        if await _safe_add(thread, member):
            added.add(member.id)

    # 1) agente definido pelo rodízio
    await add(agent)

    # 2) equipe autorizada pelo núcleo existente
    try:
        for member in core._botmod._membros_inspetor_mais_boletim(guild) or []:
            await add(member)
    except Exception:
        pass

    # 3) autor humano da mensagem de origem (quando aplicável)
    try:
        author = getattr(source_message, "author", None)
        if isinstance(author, discord.Member) and not author.bot:
            await add(author)
    except Exception:
        pass

    # 4) fallback: pessoas que realmente possuem permissão de gerenciamento
    # de threads/canais no servidor. Isso evita thread privada invisível.
    if not added:
        try:
            me = guild.me
            for member in getattr(guild, "members", []) or []:
                if member.bot:
                    continue
                perms = member.guild_permissions
                if perms.administrator or perms.manage_threads or perms.manage_channels:
                    await add(member)
                    if len(added) >= 10:
                        break
        except Exception:
            pass

    if not added:
        try:
            await core._botmod.enviar_log(
                f"⚠️ V205: BO {thread.id} foi criado, mas nenhum usuário humano foi adicionado à thread privada."
            )
        except Exception:
            pass

    return added


async def _create_v205(message):
    # Reproduz o fluxo do V200, mas usa o novo controle de membros.
    guild = message.guild
    if guild is None:
        return None

    numero = core._numero(message)
    month = core._month(message)
    if not month or core._find_message(message.id) or core._find_monthly(numero, month):
        return None

    parent = await core._get_target(guild)
    if not isinstance(parent, discord.TextChannel):
        raise RuntimeError(f"Canal de atendimento {core.TARGET_ID} não é TextChannel")

    agent = await core._agent(guild, numero)
    title = f"📋 BOLETIM DE OCORRÊNCIA — Nº {core._short(numero)}"
    try:
        thread = await parent.create_thread(
            name=title[:100],
            type=discord.ChannelType.private_thread,
            invitable=False,
            auto_archive_duration=10080,
            reason=f"DICOR V205 • BO {numero}",
        )
    except discord.HTTPException:
        thread = await parent.create_thread(
            name=title[:100],
            type=discord.ChannelType.private_thread,
            invitable=False,
            auto_archive_duration=1440,
            reason=f"DICOR V205 • BO {numero}",
        )

    await _add_members_v205(thread, guild, agent, message)

    text = core._text(message) or "Sem texto."
    await thread.send(
        content=agent.mention if agent else None,
        embed=core._embed(numero, message, agent, text),
        allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
    )
    files = await core._attachments(thread, message, numero)
    now = core._botmod.agora_br() if hasattr(core._botmod, "agora_br") else __import__("datetime").datetime.now().strftime("%d/%m/%Y %H:%M")

    atendimento = {
        "id": f"ATD-{message.id}", "numero": numero, "numero_original_texto": core._text(message),
        "mensagem_original_id": message.id, "mensagem_original_url": message.jump_url,
        "canal_origem_id": core.SOURCE_ID, "area_id": thread.id, "thread_id": thread.id,
        "canal_atendimento_id": parent.id, "topico_privado": True,
        "agente_id": agent.id if agent else None, "agente_nome": str(agent) if agent else "Nenhum agente elegível",
        "agente_atribuido_por": "RODIZIO_AUTOMATICO", "agente_atribuido_em": now,
        "autor_id": message.author.id if message.author else None, "autor_nome": str(message.author) if message.author else "Não identificado",
        "status": "EM ATENDIMENTO" if agent else "SEM AGENTE ELEGÍVEL", "data_criacao": now,
        "data_bo_original": message.created_at.strftime("%d/%m/%Y"), "mes_bo": month,
        "anexos_salvos": [str(p) for p in files], "painel_msg_id": None,
        "comparecimento_status": "não solicitado", "procurado_status": "não solicitado",
        "historico": [{"acao": "Tópico privado criado automaticamente", "usuario": "Sistema", "agente_id": agent.id if agent else None, "data": now}],
    }
    data = core._records(); data.append(atendimento); core._botmod.salvar_atendimentos_boletins(data)
    panel = await thread.send(view=core.BoletimAtendimentoV200())
    atendimento["painel_msg_id"] = panel.id
    core._botmod.atualizar_atendimento_boletim("id", atendimento["id"], atendimento)

    try:
        await core._botmod.alertar_coincidencias_novo_boletim(message, atendimento)
    except Exception:
        pass
    try:
        await core._botmod.enviar_log(
            f"📋 V205 BO aberto automaticamente | BO `{numero}` | mês `{month}` | tópico `{thread.id}` | agente `{agent.id if agent else 0}` | membros adicionados={thread.id}"
        )
    except Exception:
        pass
    return atendimento


async def process(message):
    if int(getattr(message.channel, "id", 0) or 0) != core.SOURCE_ID or not core._valid(message):
        return False
    mid = int(message.id)
    if mid in core._locks:
        return False
    core._locks.add(mid)
    try:
        numero = core._numero(message)
        month = core._month(message)
        if not month or core._find_message(mid) or core._find_monthly(numero, month):
            return False
        result = await _create_v205(message)
        if result:
            print(f"✅ V205: BO processado e visível | origem={mid} | numero={numero} | mes={month} | thread={result.get('thread_id')}", flush=True)
            return True
    except Exception as exc:
        import traceback
        traceback.print_exc()
        try:
            await core._botmod.enviar_log(f"❌ V205 falha ao abrir BO `{core._numero(message)}`: {type(exc).__name__}: {exc}")
        except Exception:
            pass
    finally:
        core._locks.discard(mid)
    return False


async def _recover_v205():
    await core._recover()


def install(botmod):
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    core._botmod = botmod
    client = botmod.bot
    try:
        client.add_view(core.BoletimAtendimentoV200())
    except Exception:
        pass

    @client.listen("on_message")
    async def _v205_message(message):
        await process(message)

    @client.listen("on_ready")
    async def _v205_ready():
        try:
            await _recover_v205()
        except Exception:
            import traceback
            traceback.print_exc()

    print("✅ V205 BO: abertura automática + visibilidade de threads privadas ativa.", flush=True)
