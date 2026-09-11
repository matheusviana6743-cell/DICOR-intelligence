# -*- coding: utf-8 -*-
"""DICOR Central V701 - interface profissional sobre o núcleo V700.

Preserva a autenticação, autorização, persistência, e-mail, FiveM e integração
Discord da V700 e apenas substitui o renderer e alguns coletores defensivos.
"""
from __future__ import annotations

import asyncio
import email
import email.header
import html
import imaplib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import central_home_v700 as base

MAIL_STATUS: dict[str, Any] = {"ok": False, "configured": False, "message": "Aguardando sincronização"}


def esc(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def clean(v: Any) -> str:
    return " ".join(str(v or "").split())


def _clean_source(v: Any) -> str:
    """Limpa scaffolding interno do Discord sem remover dados operacionais."""
    s = str(v or "")
    s = re.sub(r"\[([^\]]*)\]\((?:https?://|/)[^)]*\)", r"\1", s)
    s = re.sub(r"https?://(?:discord\.com|cdn\.discordapp\.com|media\.discordapp\.net)[^\s)>]*", "", s, flags=re.I)
    s = s.replace("**", "").replace("__", "").replace("`", "")
    blocked = (
        r"^\s*(?:📌\s*)?TAREFA\s+PENDENTE\b",
        r"^\s*ATENDIMENTO\s*:",
        r"^\s*RESPONSÁVEL\s*:\s*@\[",
        r"^\s*REGISTRE\s+NO\s+PAINEL\b",
        r"^\s*ENVOLVIDO\s+PEGAD[OA]\s+PELO\s+PAINEL\b",
        r"^\s*RECUPERAÇÃO\s+(?:ASSISTIDA|AUTOMÁTICA|ÓRFÃ)\b",
        r"^\s*RECUPERACAO\s+(?:ASSISTIDA|AUTOMATICA|ORFA)\b",
        r"^\s*TÓPICO\s*🟠",
        r"^\s*TOPICO\s*🟠",
        r"^\s*PAINEL\s+(?:ATUALIZADO|RECRIADO|RECUPERADO)\b",
        r"^\s*AGUARDE\s+ATUALIZAÇÃO\b",
    )
    rx = tuple(re.compile(x, re.I) for x in blocked)
    out: list[str] = []
    for line in re.split(r"\r?\n+", s):
        line = clean(line)
        if not line or any(p.search(line) for p in rx):
            continue
        out.append(line)
    return "\n".join(out)


base.clean_source = _clean_source


def _mail_poll_sync() -> dict[str, list[dict[str, Any]]]:
    out = {x: [] for x in ("procurados", "boletins", "pericias", "operacoes")}
    configured = bool(base.MAIL_HOST and base.MAIL_USER and base.MAIL_PASS)
    MAIL_STATUS["configured"] = configured
    if not configured:
        MAIL_STATUS.update(ok=False, message="Gmail não configurado")
        return out

    conn = None
    try:
        conn = imaplib.IMAP4_SSL(base.MAIL_HOST, base.MAIL_PORT, timeout=45)
        conn.login(base.MAIL_USER, base.MAIL_PASS)
        ok, _ = conn.select(base.MAIL_FOLDER, readonly=True)
        if ok != "OK":
            raise RuntimeError(f"pasta IMAP indisponível: {base.MAIL_FOLDER}")
        ok, data = conn.uid("search", None, "ALL")
        if ok != "OK" or not data or not data[0]:
            MAIL_STATUS.update(ok=True, message="Gmail conectado • nenhuma mensagem encontrada")
            return out

        uids = list(reversed(data[0].split()[-base.MAIL_LIMIT:]))
        for uid in uids:
            try:
                ok, fetched = conn.uid("fetch", uid, "(BODY.PEEK[])")
                raw = b"".join(
                    part[1] for part in (fetched or [])
                    if isinstance(part, tuple) and len(part) > 1 and isinstance(part[1], bytes)
                )
                if ok != "OK" or not raw:
                    continue
                msg = email.message_from_bytes(raw)
                body, files = base.mail_body(msg)
                body_clean = _clean_source(body)
                subject = base.dh(msg.get("Subject", ""))
                kind = base.mail_kind(subject, body_clean)
                if kind:
                    out[kind].append(base.mail_row(kind, msg, uid, body_clean, files))
            except Exception:
                continue

        MAIL_STATUS.update(
            ok=True,
            message=f"Gmail conectado • {sum(len(v) for v in out.values())} registro(s) lido(s)",
        )
        return out
    except Exception as exc:
        MAIL_STATUS.update(ok=False, message=f"Gmail indisponível • {type(exc).__name__}")
        print(f"⚠️ [CENTRAL MAIL V701] {type(exc).__name__}: {exc}", flush=True)
        return out
    finally:
        if conn:
            try:
                conn.logout()
            except Exception:
                pass


base.poll_mail_sync = _mail_poll_sync


async def _ops_discord_auto() -> list[dict[str, Any]]:
    """Consulta operações pelo canal configurado e, sem configuração, por nomes óbvios."""
    client = base.CLIENT
    if not client or not getattr(client, "is_ready", lambda: False)():
        return []

    channels: list[Any] = []
    seen: set[int] = set()
    configured = int(os.getenv("DICOR_OPERACOES_CHANNEL_ID", "0") or 0)
    if configured:
        channel = client.get_channel(configured)
        if channel is None:
            try:
                channel = await client.fetch_channel(configured)
            except Exception:
                channel = None
        if channel is not None:
            channels.append(channel)
            seen.add(int(getattr(channel, "id", 0) or 0))

    if not channels:
        wanted = ("operacao", "operacoes", "operação", "operações", "operacional", "operacional")
        for guild in list(getattr(client, "guilds", []) or []):
            for channel in list(getattr(guild, "text_channels", []) or []):
                name = clean(getattr(channel, "name", "")).casefold()
                if any(term in name for term in wanted):
                    cid = int(getattr(channel, "id", 0) or 0)
                    if cid and cid not in seen:
                        channels.append(channel)
                        seen.add(cid)
                if len(channels) >= 5:
                    break
            if len(channels) >= 5:
                break

    rows: list[dict[str, Any]] = []
    for channel in channels[:5]:
        try:
            async for message in channel.history(limit=160):
                text = _clean_source(base.source.text_of(message))
                if not text:
                    continue
                low = text.casefold()
                if not any(token in low for token in ("operação", "operacao", "missão", "missao", "ação operacional", "acao operacional")):
                    continue
                number = base.number(text)
                name = base.field(text, ("operação", "operacao", "missão", "missao", "nome"))
                rows.append({
                    "id": str(getattr(message, "id", "")),
                    "number": number,
                    "name": name if name != "Não informado" else "Operação",
                    "kind": "operacoes",
                    "source": "DISCORD",
                    "subject": "",
                    "date": str(getattr(message, "created_at", "")),
                    "image": base.source.media_url(message),
                    "url": str(getattr(message, "jump_url", "")),
                    "fields": {"Número do registro": number},
                    "full_text": text,
                })
        except Exception as exc:
            print(f"⚠️ [CENTRAL OPS V701] {type(exc).__name__}", flush=True)
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        unique[row["id"]] = row
    return list(unique.values())


base.ops_discord = _ops_discord_auto


def _brand() -> str:
    return f'''<a class="brand" href="/">
      <span class="crest-wrap"><img class="crest" src="{esc(base.LOGO)}" alt="Brasão DICOR" onerror="this.style.display='none';this.nextElementSibling.style.display='grid'"><span class="crest-fallback">D</span></span>
      <span class="brand-copy"><b>PCPT POLÍCIA MORADA</b><small>POLÍCIA FEDERAL</small><strong>DICOR</strong></span>
    </a>'''


def _header(title: str, u: dict[str, Any] | None = None, admin: bool = False) -> str:
    who = ""
    if u:
        who = f'''<div class="userbox"><span class="online-dot"></span><div><b>{esc(u.get("nome") or u.get("qra"))}</b><small>PASSAPORTE {esc(u.get("passaporte"))}</small></div></div>
        <form method="post" action="/logout"><input type="hidden" name="csrf" value="{esc(base.csrf(u))}"><button class="logout">SAIR</button></form>'''
    links = '<a href="/">CENTRAL</a><a href="/procurados">PROCURADOS</a><a href="/fotos">FOTO → FIVE M</a><a href="/central">ÁREA RESTRITA</a>'
    if admin:
        links += '<a href="/admin">USUÁRIOS</a>'
    return f'''<header class="topbar"><div class="top-inner">{_brand()}<nav>{links}</nav><div class="top-right">{who}</div></div></header>'''


def _shell(title: str, body: str, u: dict[str, Any] | None = None, admin: bool = False) -> str:
    csp = "default-src 'self';img-src 'self' data: https:;connect-src 'self';style-src 'self' 'unsafe-inline';script-src 'self' 'unsafe-inline';frame-ancestors 'none';base-uri 'self';form-action 'self';object-src 'none'"
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{esc(csp)}"><meta name="theme-color" content="#06111c"><title>{esc(title)}</title><style>{CSS}</style></head><body>{_header(title,u,admin)}<main class="wrap">{body}</main><footer class="footer">DICOR • CENTRAL DE INTELIGÊNCIA &nbsp;|&nbsp; PCPT POLÍCIA MORADA - POLÍCIA FEDERAL</footer><script>setInterval(function(){fetch('/api/heartbeat',{method:'POST',credentials:'same-origin',cache:'no-store'}).catch(function(){});},60000);function cp(v,b){if(!navigator.clipboard)return;navigator.clipboard.writeText(v).then(function(){var t=b.innerText;b.innerText='COPIADO';setTimeout(function(){b.innerText=t},1100)});}function fileName(i){var e=document.getElementById('picked');if(i.files&&i.files[0])e.innerText=i.files[0].name;}</script></body></html>'''


def _stat(label: str, value: Any, tone: str = "") -> str:
    return f'<div class="stat {tone}"><span>{esc(label)}</span><b>{esc(value)}</b></div>'


def _module(title: str, desc: str, href: str, count: Any = "—", locked: bool = False) -> str:
    tag = 'RESTRITO' if locked else 'DISPONÍVEL'
    cls = 'module locked' if locked else 'module'
    return f'''<a class="{cls}" href="{esc(href)}"><div class="module-top"><span>{esc(tag)}</span><b>{esc(count)}</b></div><h3>{esc(title)}</h3><p>{esc(desc)}</p><div class="module-open">ABRIR MÓDULO <strong>→</strong></div></a>'''


def _home(u: dict[str, Any]) -> str:
    rs = list(base.C.get("procurados", []) or [])
    bs = list(base.C.get("boletins", []) or [])
    ps = list(base.C.get("pericias", []) or [])
    ops = list(base.C.get("operacoes", []) or [])
    cards = []
    for r in rs[:3]:
        fs = r.get("fields") or {}
        image = f'<img src="{esc(r.get("image"))}" alt="Foto do procurado" loading="lazy">' if r.get("image") else '<div class="no-photo"><span>DICOR</span><small>SEM FOTO</small></div>'
        cards.append(f'''<article class="wanted-card"><div class="wanted-photo">{image}<span class="wanted-badge">PROCURADO ATIVO</span></div><div class="wanted-body"><div class="wanted-title">{esc(r.get("name") or "Indivíduo não identificado")}</div><div class="wanted-id">REGISTRO {esc(r.get("number") or "S/N")}</div><div class="wanted-row"><span>CRIMES</span><b>{esc(fs.get("Crimes") or "Não informado")}</b></div><div class="wanted-row"><span>LOCALIZAÇÃO</span><b>{esc(fs.get("Localização") or "Não informado")}</b></div><a href="/registro/procurados/{esc(r.get('id'))}" class="wanted-open">ABRIR FICHA COMPLETA →</a></div></article>''')
    mail_text = esc(MAIL_STATUS.get("message") or "Aguardando sincronização")
    mail_cls = "ok" if MAIL_STATUS.get("ok") else ("warn" if MAIL_STATUS.get("configured") else "muted")
    auth = bool(u.get("authorized")); pending = bool(u.get("access_request_pending"))
    access = '<a class="primary" href="/central">ABRIR CENTRAL OPERACIONAL →</a>' if auth else ('<span class="pending-btn">SOLICITAÇÃO EM ANÁLISE</span>' if pending else f'<form method="post" action="/abrir-central"><input type="hidden" name="csrf" value="{esc(base.csrf(u))}"><button class="primary">SOLICITAR ACESSO RESTRITO →</button></form>')
    status = '<span class="access-ok">● ACESSO AUTORIZADO</span>' if auth else ('<span class="access-pending">● AGUARDANDO AUTORIZAÇÃO</span>' if pending else '<span class="access-locked">● ÁREA PROTEGIDA</span>')
    body = f'''<section class="hero-grid"><section class="hero-panel"><div class="eyebrow">SISTEMA INTEGRADO DE INTELIGÊNCIA • DICOR</div><h1>CENTRAL<br><span>DE INTELIGÊNCIA</span></h1><p>Ambiente interno da Polícia Federal para consulta de Procurados, Boletins, Perícias, Operações e recursos visuais do FiveM.</p><div class="hero-actions"><a class="primary" href="/procurados">CONSULTAR PROCURADOS</a><a class="secondary" href="/fotos">FOTO → FIVE M</a></div></section><section class="identity-panel"><div class="ring"></div><img src="{esc(base.LOGO)}" alt="Brasão DICOR" class="hero-crest" onerror="this.style.display='none';document.getElementById('heroFallback').style.display='grid'"><div id="heroFallback" class="hero-fallback">DICOR</div><strong>PCPT • POLÍCIA FEDERAL</strong><small>DIVISÃO DE INTELIGÊNCIA E COMBATE AO CRIME ORGANIZADO</small></section></section>
    <section class="stats-grid">{_stat('PROCURADOS',len(rs),'gold')}{_stat('BOLETINS',len(bs) if auth else '—')}{_stat('PERÍCIAS',len(ps) if auth else '—')}{_stat('OPERAÇÕES',len(ops) if auth else '—')}</section>
    <section class="system-status"><div><span class="status-label">STATUS DA CENTRAL</span><h2>INTEGRAÇÕES</h2><p>Discord e Gmail monitorados pela Central, com atualização automática e filtros de conteúdo interno.</p></div><div class="status-chips"><span class="chip ok">● DISCORD ONLINE</span><span class="chip {mail_cls}">● {mail_text.upper()}</span></div></section>
    <div class="section-head"><div><span>MONITORAMENTO</span><h2>PROCURADOS EM DESTAQUE</h2></div><a href="/procurados">VER TODOS →</a></div>
    <section class="wanted-grid">{''.join(cards) or '<div class="empty">Nenhum Procurado ativo encontrado.</div>'}</section>
    <section class="access-panel"><div><span class="eyebrow">SEGURANÇA</span><h2>ACESSO OPERACIONAL</h2><p>Boletins, Perícias e Operações permanecem protegidos e só são liberados após aprovação administrativa.</p><div class="access-status">{status}</div></div><div>{access}</div></section>
    <div class="section-head"><div><span>MÓDULOS</span><h2>RECURSOS DA CENTRAL</h2></div></div><section class="modules-grid">{_module('PROCURADOS','Consulta e fichas completas dos registros ativos.','/procurados',len(rs))}{_module('BOLETINS','Registros recebidos pela Central e organizados por ficha.','/boletins',len(bs) if auth else 'RESTRITO',not auth)}{_module('PERÍCIAS','Laudos e registros periciais recebidos pelo Gmail.','/pericias',len(ps) if auth else 'RESTRITO',not auth)}{_module('OPERAÇÕES','Registros operacionais e missões identificadas.','/operacoes',len(ops) if auth else 'RESTRITO',not auth)}{_module('FOTO → FIVE M','Envie uma imagem e gere um link direto para o FiveM.','/fotos','↗')}</section>'''
    return _shell('DICOR • Central', body, u, base.is_admin(u))


def _restricted(u: dict[str, Any]) -> str:
    rs, bs, ps, ops = (len(base.C.get(x,[]) or []) for x in ('procurados','boletins','pericias','operacoes'))
    if not u.get('authorized'):
        text = 'Solicitação enviada. Aguarde a aprovação do administrador no canal interno.' if u.get('access_request_pending') else 'Esta área contém dados operacionais protegidos. Solicite acesso pela Central principal.'
        body = f'''<section class="restricted-hero"><div class="eyebrow">DICOR • CONTROLE DE ACESSO</div><h1>ÁREA <span>RESTRITA</span></h1><p>{esc(text)}</p><div class="lock-card"><div class="lock-icon">⌾</div><div><strong>BOLETINS • PERÍCIAS • OPERAÇÕES</strong><small>Autorização administrativa obrigatória</small></div></div><a class="secondary wide" href="/">← VOLTAR À CENTRAL</a></section>'''
        return _shell('DICOR • Área Restrita', body, u, base.is_admin(u))
    modules = [_module('BOLETINS','Consulta completa dos registros recebidos pela Central.','/boletins',bs),_module('PERÍCIAS','Laudos e atendimentos periciais.','/pericias',ps),_module('OPERAÇÕES','Missões e registros operacionais.','/operacoes',ops),_module('PROCURADOS','Catálogo de Procurados com ficha completa.','/procurados',rs),_module('FOTO → FIVE M','Upload seguro e link direto da imagem.','/fotos','↗')]
    body = f'''<section class="panel section-panel"><div class="eyebrow">DICOR • ACESSO AUTORIZADO</div><h1>CENTRAL <span>OPERACIONAL</span></h1><p>Usuário autorizado: <b>{esc(u.get('nome') or u.get('qra'))}</b> • Passaporte {esc(u.get('passaporte'))}</p><section class="modules-grid">{''.join(modules)}</section></section>'''
    return _shell('DICOR • Central Operacional', body, u, base.is_admin(u))


def _record_card(r: dict[str, Any], href: str) -> str:
    fs = r.get('fields') or {}
    vals = list(fs.items())[:7]
    return f'''<article class="record-card"><div class="record-top"><div><span class="record-source">{esc(r.get('source') or 'REGISTRO')}</span><h3>{esc(r.get('name') or r.get('subject') or 'Registro')}</h3></div><span class="record-number">Nº {esc(r.get('number') or 'S/N')}</span></div><div class="record-date">{esc(r.get('date') or 'Data não informada')}</div><div class="record-fields">{''.join(f'<div><label>{esc(a)}</label><strong>{esc(b)}</strong></div>' for a,b in vals)}</div><a class="record-open" href="{esc(href)}">ABRIR REGISTRO COMPLETO <b>→</b></a></article>'''


def _list_page(u: dict[str, Any], kind: str, title: str, desc: str) -> str:
    rows = list(base.C.get(kind,[]) or [])
    content = ''.join(_record_card(r,f'/registro/{kind}/{base.quote(str(r.get("id")))}') for r in rows) or '<div class="empty">Nenhum registro disponível no momento.</div>'
    body = f'''<section class="section-panel"><div class="eyebrow">DICOR • BANCO OPERACIONAL</div><h1>{esc(title)}</h1><p>{esc(desc)}</p><div class="list-toolbar"><div><span>REGISTROS SINCRONIZADOS</span><strong>{len(rows):02d}</strong></div><a href="/central">← ÁREA OPERACIONAL</a></div><section class="records-grid">{content}</section></section>'''
    return _shell('DICOR • '+title, body, u, base.is_admin(u))


def _detail(u: dict[str, Any], kind: str, rid: str) -> str:
    rows = list(base.C.get(kind,[]) or [])
    r = next((x for x in rows if str(x.get('id')) == rid), None)
    if kind != 'procurados' and not u.get('authorized'):
        return _restricted(u)
    if not r:
        body = '<section class="section-panel"><div class="eyebrow">DICOR • REGISTRO</div><h1>REGISTRO NÃO ENCONTRADO</h1><p>O registro solicitado não está disponível na sincronização atual.</p><a class="secondary" href="/central">← VOLTAR</a></section>'
        return _shell('DICOR • Registro', body, u, base.is_admin(u))
    fs = r.get('fields') or {}
    image = f'<img class="detail-image" src="{esc(r.get("image"))}" alt="Registro">' if r.get('image') else '<div class="detail-no-image">SEM IMAGEM</div>'
    fields = ''.join(f'<div class="detail-field"><label>{esc(a)}</label><strong>{esc(b)}</strong></div>' for a,b in fs.items())
    origin = f'<a class="secondary" target="_blank" rel="noopener" href="{esc(r.get("url"))}">ABRIR ORIGEM →</a>' if r.get('url') else ''
    body = f'''<section class="detail-layout"><aside class="detail-media"><div class="record-source">{esc(r.get('source'))}</div>{image}<div class="detail-meta">Nº {esc(r.get('number') or 'S/N')}<br>{esc(r.get('date') or 'Data não informada')}</div></aside><section class="section-panel detail-content"><div class="eyebrow">DICOR • REGISTRO COMPLETO</div><h1>{esc(r.get('name') or r.get('subject') or 'Registro')}</h1><p>{esc(kind.upper())} • fonte {esc(r.get('source') or 'não informada')}</p><div class="detail-fields">{fields}</div><div class="full-content"><div class="full-title">CONTEÚDO CONSOLIDADO</div>{esc(r.get('full_text') or 'Sem informações adicionais.')}</div><div class="hero-actions"><a class="secondary" href="/{esc(kind)}">← VOLTAR</a>{origin}</div></section></section>'''
    return _shell('DICOR • Registro', body, u, base.is_admin(u))


def _photos(u: dict[str, Any], result: str = '', error: str = '') -> str:
    result_box = ''
    if result:
        result_box = f'''<section class="link-result"><div class="eyebrow">UPLOAD CONCLUÍDO</div><h2>LINK DIRETO PARA FIVE M</h2><p>URL pronta para copiar e usar no FiveM.</p><div class="copy-row"><input id="five" readonly value="{esc(result)}"><button class="primary small" onclick="cp(document.getElementById('five').value,this)">COPIAR LINK</button></div></section>'''
    err = f'<div class="notice-error">{esc(error)}</div>' if error else ''
    body = f'''<section class="section-panel"><div class="eyebrow">DICOR • ARQUIVO VISUAL</div><h1>FOTO <span>→ FIVE M</span></h1><p>Envie uma imagem para o armazenamento configurado e receba um link direto. Formatos: PNG, JPG, WEBP ou GIF • até 10 MB.</p>{err}<form class="upload-panel" method="post" action="/fotos/upload" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{esc(base.csrf(u))}"><label class="dropzone"><input type="file" name="foto" accept="image/png,image/jpeg,image/webp,image/gif" required onchange="fileName(this)"><span class="drop-icon">＋</span><strong>SELECIONAR IMAGEM</strong><small id="picked">Nenhum arquivo selecionado</small></label><button class="primary wide" type="submit">ENVIAR E GERAR LINK →</button></form></section>{result_box}'''
    return _shell('DICOR • Foto → FiveM', body, u, base.is_admin(u))


def _admin(u: dict[str, Any]) -> str:
    rows = sorted(base.users().values(), key=lambda x: str(x.get('updated_at','')), reverse=True)
    items = []
    for r in rows:
        online = base.online(r)
        authorized = bool(r.get('authorized'))
        pending = bool(r.get('access_request_pending'))
        kk = base.k(r.get('qra'), r.get('passaporte'))
        status = '<span class="pill ok">ONLINE</span>' if online else '<span class="pill">OFFLINE</span>'
        access = '<span class="pill blue">AUTORIZADO</span>' if authorized else ('<span class="pill gold">PENDENTE</span>' if pending else '<span class="pill">BLOQUEADO</span>')
        items.append(f'''<article class="admin-row"><div><span class="record-source">OPERADOR</span><h3>{esc(r.get('nome') or r.get('qra'))}</h3><small>QRA {esc(r.get('qra'))} • PASSAPORTE {esc(r.get('passaporte'))}</small></div><div><span class="admin-label">STATUS</span><div>{status} {access}</div><span class="last">ÚLTIMO ACESSO {esc(r.get('last_seen') or 'nunca')}</span></div><form class="admin-form" method="post" action="/admin/user"><input type="hidden" name="csrf" value="{esc(base.csrf(u))}"><input type="hidden" name="key" value="{esc(kk)}"><input name="nome" value="{esc(r.get('nome') or '')}" maxlength="100" placeholder="Nome do operador"><input name="cargo" value="{esc(r.get('cargo') or '')}" maxlength="100" placeholder="Cargo definido pelo administrador"><button>SALVAR</button></form></article>''')
    alln=len(rows); on=sum(1 for x in rows if base.online(x)); au=sum(1 for x in rows if x.get('authorized'))
    body = f'''<section class="section-panel"><div class="eyebrow">DICOR • ADMINISTRAÇÃO</div><h1>USUÁRIOS <span>DA CENTRAL</span></h1><p>Cadastro persistente, presença, autorização e cargo definido exclusivamente pelo administrador.</p><section class="stats-grid admin-stats">{_stat('USUÁRIOS',alln,'gold')}{_stat('ONLINE',on)}{_stat('AUTORIZADOS',au)}</section><div class="admin-list">{''.join(items) or '<div class="empty">Nenhum usuário cadastrado.</div>'}</div></section>'''
    return _shell('DICOR • Usuários', body, u, True)


CSS = r'''
:root{--bg:#030a11;--panel:#081521;--panel2:#0a1a28;--line:#1d4057;--line2:#315b75;--text:#edf4f8;--muted:#849caf;--blue:#54afea;--gold:#e0bb55;--gold2:#f1d47d;--green:#56d39a;--red:#ef6c75}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;background:radial-gradient(circle at 80% 0,#103555 0,#071622 25%,#03080d 68%,#02060a 100%);color:var(--text)}body{overflow-x:hidden}a{text-decoration:none;color:inherit}button,input{font:inherit}.topbar{position:sticky;top:0;z-index:80;background:rgba(3,12,19,.95);border-bottom:1px solid #1b3b52;backdrop-filter:blur(18px)}.top-inner{min-height:78px;width:min(1500px,calc(100% - 42px));margin:auto;display:flex;align-items:center;gap:25px}.brand{display:flex;align-items:center;gap:12px;min-width:340px}.crest-wrap{position:relative;width:52px;height:52px;display:grid;place-items:center;border:1px solid #305671;border-radius:13px;background:radial-gradient(circle,#0e2638,#06101a);overflow:hidden;box-shadow:0 10px 25px #0007}.crest{width:42px;height:42px;object-fit:contain;mix-blend-mode:screen;filter:drop-shadow(0 7px 13px #000)}.crest-fallback{display:none;place-items:center;width:38px;height:38px;border-radius:10px;border:1px solid #b38a28;color:var(--gold2);font-weight:950;font-size:19px}.brand-copy b,.brand-copy small,.brand-copy strong{display:block}.brand-copy b{font-size:10px;letter-spacing:1.7px}.brand-copy small{color:#829bad;font-size:8px;letter-spacing:1.5px;margin-top:3px}.brand-copy strong{color:var(--gold2);font-size:13px;letter-spacing:3.4px;margin-top:4px}.top-inner nav{display:flex;gap:22px;margin-left:auto;align-items:center;white-space:nowrap}.top-inner nav a{font-size:9px;color:#8198a9;font-weight:950;letter-spacing:1.15px}.top-inner nav a:hover{color:#fff}.top-right{display:flex;align-items:center;gap:12px}.userbox{display:flex;align-items:center;gap:8px}.online-dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 13px var(--green)}.userbox b{display:block;font-size:9px}.userbox small{display:block;color:#6d8698;font-size:7px;margin-top:2px}.logout{border:1px solid #2c4d61;background:#071722;color:#a2b6c4;border-radius:8px;padding:8px 11px;font-size:8px;font-weight:950;cursor:pointer}.wrap{width:min(1450px,calc(100% - 42px));margin:auto;padding:28px 0 50px}.hero-grid{display:grid;grid-template-columns:1.35fr .65fr;gap:16px}.hero-panel,.identity-panel,.section-panel,.access-panel,.system-status{border:1px solid var(--line);border-radius:20px;background:linear-gradient(145deg,#0b1b2a,#06111a);box-shadow:0 25px 65px #0008}.hero-panel{padding:46px}.eyebrow,.status-label{color:var(--blue);font-size:9px;font-weight:950;letter-spacing:2.5px}.hero-panel h1{font-size:57px;line-height:.98;letter-spacing:1px;margin:14px 0}.hero-panel h1 span,.section-panel h1 span,.restricted-hero h1 span{color:var(--gold2)}.hero-panel p,.section-panel>p,.system-status p,.access-panel p,.restricted-hero p{color:var(--muted);font-size:13px;line-height:1.75;max-width:720px;margin:0}.hero-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:26px}.primary,.secondary,.pending-btn{display:inline-flex;align-items:center;justify-content:center;min-height:46px;padding:0 18px;border-radius:10px;font-size:9px;font-weight:950;letter-spacing:1px;cursor:pointer}.primary{border:0;background:linear-gradient(135deg,#f1d16e,#a8791c);color:#090b0e;box-shadow:0 10px 25px #0006}.primary.small{min-height:39px}.secondary{border:1px solid #315a74;background:#0a2030;color:#c4ddeb}.pending-btn{border:1px solid #5b4721;background:#16130d;color:#d8b95c}.wide{width:100%}.identity-panel{position:relative;min-height:330px;display:flex;align-items:center;justify-content:center;flex-direction:column;overflow:hidden;text-align:center;background:radial-gradient(circle,#123b5d,#081724 53%,#06101a)}.ring{position:absolute;width:245px;height:245px;border:1px solid #49a7dc4b;border-radius:50%;box-shadow:0 0 0 36px #49a7dc0b,0 0 0 74px #49a7dc05}.hero-crest{width:152px;height:152px;object-fit:contain;z-index:2;mix-blend-mode:screen;filter:drop-shadow(0 15px 27px #000)}.hero-fallback{display:none;z-index:2;width:150px;height:150px;border:1px solid #a67e29;border-radius:30px;place-items:center;background:#0a1c2a;color:var(--gold2);font-size:33px;font-weight:950;letter-spacing:4px}.identity-panel strong{z-index:3;margin-top:20px;font-size:11px;letter-spacing:1.8px}.identity-panel small{z-index:3;margin-top:7px;color:#7892a5;font-size:7px;letter-spacing:1.4px;max-width:310px;line-height:1.5}.stats-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin-top:16px}.stat{border:1px solid var(--line);border-radius:12px;background:#07131f;padding:17px 18px}.stat span{display:block;color:#668398;font-size:8px;font-weight:950;letter-spacing:1.3px}.stat b{display:block;margin-top:7px;font-size:30px}.stat.gold b{color:var(--gold2)}.system-status{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-top:16px;padding:20px 22px}.system-status h2,.access-panel h2{font-size:16px;margin:5px 0 3px;letter-spacing:1.3px}.status-chips{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.chip,.access-status,.pill{display:inline-flex;align-items:center;padding:7px 9px;border-radius:8px;border:1px solid #234b63;background:#071924;color:#9ab0bf;font-size:7px;font-weight:950;letter-spacing:.7px}.chip.ok,.pill.ok,.access-ok{color:#82ddb1;border-color:#28664f;background:#0b211b}.chip.warn,.pill.gold,.access-pending{color:#e0bd61;border-color:#6b5220;background:#19140a}.chip.muted,.pill,.access-locked{color:#81929e;border-color:#293a46;background:#0c141a}.section-head{display:flex;align-items:end;justify-content:space-between;gap:15px;margin:28px 3px 12px}.section-head span{display:block;color:var(--blue);font-size:8px;font-weight:950;letter-spacing:2px}.section-head h2{margin:6px 0 0;font-size:17px;letter-spacing:1.4px}.section-head>a{font-size:8px;color:#88b7d5;font-weight:950}.wanted-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.wanted-card{border:1px solid var(--line);border-radius:17px;overflow:hidden;background:linear-gradient(155deg,#091723,#050e16);box-shadow:0 15px 45px #0007}.wanted-photo{height:255px;background:#02070c;position:relative;display:grid;place-items:center;overflow:hidden}.wanted-photo img{width:100%;height:100%;object-fit:cover}.wanted-badge{position:absolute;left:12px;top:12px;padding:6px 8px;border-radius:7px;background:#050a0fdb;border:1px solid #d6af4f5b;color:var(--gold2);font-size:7px;font-weight:950}.no-photo{text-align:center;color:#496477}.no-photo span{display:block;font-size:23px;letter-spacing:3px;color:#6b7f8e}.no-photo small{display:block;font-size:7px;letter-spacing:1.3px;margin-top:5px}.wanted-body{padding:18px}.wanted-title{font-size:19px;font-weight:950;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.wanted-id{color:var(--gold2);font-size:8px;font-weight:900;letter-spacing:1px;margin-top:4px}.wanted-row{border-top:1px solid #143248;margin-top:12px;padding-top:10px;display:flex;justify-content:space-between;gap:15px}.wanted-row span{color:#607b90;font-size:7px;font-weight:950;letter-spacing:1.1px}.wanted-row b{font-size:9px;max-width:65%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.wanted-open,.record-open,.module-open{display:flex;align-items:center;justify-content:space-between;margin-top:15px;padding:11px;border:1px solid #285574;border-radius:9px;color:#96c3df;font-size:8px;font-weight:950;letter-spacing:1px}.access-panel{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-top:16px;padding:23px}.access-panel p{max-width:830px}.access-status{margin-top:11px}.modules-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.module{border:1px solid var(--line);border-radius:15px;padding:18px;background:linear-gradient(160deg,#0a1926,#06111a);transition:.16s}.module:hover{transform:translateY(-2px);border-color:#3b6d8c}.module.locked{opacity:.65}.module-top{display:flex;justify-content:space-between;gap:10px}.module-top span{font-size:7px;color:#67849a;font-weight:950;letter-spacing:1px}.module-top b{font-size:13px;color:var(--gold2)}.module h3{font-size:14px;margin:12px 0 6px;letter-spacing:.7px}.module p{color:#7990a3;font-size:10px;line-height:1.65;min-height:48px;margin:0}.module-open{margin-top:16px;color:#d2e0e8}.module-open strong{color:var(--gold2)}.section-panel{padding:31px}.section-panel h1,.restricted-hero h1{font-size:39px;margin:10px 0 7px;letter-spacing:1px}.list-toolbar{display:flex;justify-content:space-between;align-items:end;border-top:1px solid #17364b;margin-top:24px;padding-top:17px}.list-toolbar span,.admin-label,.last{display:block;color:#5f7b90;font-size:7px;font-weight:950;letter-spacing:1px}.list-toolbar strong{font-size:25px;display:block;margin-top:4px}.list-toolbar a{font-size:8px;color:#8eb8d5;font-weight:950}.records-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:13px;margin-top:13px}.record-card{border:1px solid var(--line);border-radius:15px;padding:17px;background:#07131f}.record-top{display:flex;justify-content:space-between;gap:15px}.record-source{font-size:7px;color:var(--blue);font-weight:950;letter-spacing:1.5px}.record-card h3{font-size:16px;margin:7px 0 0}.record-number{color:var(--gold2);font-size:8px;font-weight:950;white-space:nowrap}.record-date{color:#607a8d;font-size:8px;margin-top:5px}.record-fields{display:grid;grid-template-columns:repeat(2,1fr);gap:9px;margin-top:15px}.record-fields div{border-top:1px solid #153247;padding-top:8px}.record-fields label,.detail-field label{display:block;color:#5e7a90;font-size:7px;font-weight:950;letter-spacing:.9px}.record-fields strong{display:block;margin-top:4px;font-size:9px;line-height:1.45;overflow-wrap:anywhere}.record-open{border-color:#254b63}.detail-layout{display:grid;grid-template-columns:350px 1fr;gap:15px}.detail-media{border:1px solid var(--line);border-radius:18px;background:#06101a;padding:16px;height:max-content}.detail-image{width:100%;min-height:330px;max-height:560px;object-fit:cover;border-radius:12px;margin-top:12px}.detail-no-image{min-height:330px;display:grid;place-items:center;border-radius:12px;background:#02070c;color:#526d80;font-size:10px;font-weight:950;margin-top:12px}.detail-meta{font-size:9px;color:#7f96a8;line-height:1.7;border-top:1px solid #18374a;margin-top:13px;padding-top:12px}.detail-fields{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:22px}.detail-field{border:1px solid #19394f;border-radius:10px;padding:11px;background:#07141f}.detail-field strong{display:block;margin-top:5px;font-size:10px;line-height:1.55;overflow-wrap:anywhere}.full-content{margin-top:14px;border:1px solid #1a3a50;border-radius:12px;background:#040c13;padding:16px;white-space:pre-wrap;color:#b7c7d1;font-size:10px;line-height:1.7}.full-title{color:var(--gold2);font-size:8px;font-weight:950;letter-spacing:1px;margin-bottom:8px}.restricted-hero{border:1px solid var(--line);border-radius:20px;padding:42px;background:linear-gradient(145deg,#0b1a28,#06111a)}.restricted-hero h1{font-size:46px}.restricted-hero .lock-card{display:flex;align-items:center;gap:14px;margin:24px 0;padding:17px;border:1px solid #6b5222;border-radius:12px;background:#141109}.lock-icon{width:42px;height:42px;display:grid;place-items:center;border:1px solid #9c7527;border-radius:10px;color:var(--gold2);font-size:20px}.lock-card strong{display:block;font-size:11px}.lock-card small{display:block;color:#84775a;font-size:8px;margin-top:4px}.upload-panel{margin-top:20px;padding:20px;border:1px dashed #315a76;border-radius:15px;background:#06131e}.dropzone{min-height:220px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:8px;border:1px dashed #315a76;border-radius:12px;background:radial-gradient(circle,#0b2235,#06111b);cursor:pointer}.dropzone input{display:none}.drop-icon{font-size:38px;color:var(--gold2)}.dropzone strong{font-size:11px;letter-spacing:1px}.dropzone small{color:#70889b;font-size:8px}.upload-panel .primary{margin-top:12px}.link-result{margin-top:14px;border:1px solid #285c48;border-radius:15px;background:#071a16;padding:21px}.link-result h2{font-size:18px;margin:6px 0}.link-result p{color:#7f9d91;font-size:10px}.copy-row{display:flex;gap:7px}.copy-row input{flex:1;height:42px;border:1px solid #244b42;border-radius:8px;background:#04100d;color:#d9eee5;padding:0 10px;font-size:9px}.notice-error{margin-top:15px;padding:11px;border:1px solid #753740;background:#241016;color:#ffcbd0;border-radius:9px;font-size:9px}.admin-stats{grid-template-columns:repeat(3,1fr)}.admin-list{display:grid;gap:11px;margin-top:17px}.admin-row{display:grid;grid-template-columns:1.15fr .9fr 1.5fr;gap:15px;padding:17px;border:1px solid var(--line);border-radius:14px;background:#07131f}.admin-row h3{font-size:16px;margin:6px 0 4px}.admin-row small{color:#6f8798;font-size:7px}.admin-form{display:grid;grid-template-columns:1fr 1fr auto;gap:7px}.admin-form input{height:38px;border:1px solid #294960;background:#06111a;color:#eef4f7;border-radius:8px;padding:0 9px;font-size:9px;outline:none}.admin-form button{border:0;border-radius:8px;background:linear-gradient(135deg,#efd06d,#a9791c);color:#090b0d;font-size:8px;font-weight:950;padding:0 13px;cursor:pointer}.footer{text-align:center;border-top:1px solid #142e41;padding:18px 10px;color:#50687a;font-size:8px;letter-spacing:.8px}@media(max-width:1100px){.top-inner nav{gap:12px}.brand{min-width:250px}.hero-grid,.detail-layout{grid-template-columns:1fr}.modules-grid{grid-template-columns:repeat(2,1fr)}.wanted-grid{grid-template-columns:repeat(2,1fr)}.stats-grid{grid-template-columns:repeat(2,1fr)}.records-grid{grid-template-columns:1fr}.admin-row{grid-template-columns:1fr 1fr}.admin-form{grid-column:1/-1}}@media(max-width:720px){.top-inner{width:calc(100% - 20px);flex-wrap:wrap;padding:10px 0}.top-inner nav{order:3;width:100%;overflow:auto;padding-bottom:4px}.top-right{margin-left:auto}.brand{min-width:0}.userbox{display:none}.wrap{width:calc(100% - 18px);padding-top:12px}.hero-panel{padding:28px}.hero-panel h1{font-size:38px}.identity-panel{min-height:260px}.hero-crest{width:110px;height:110px}.stats-grid,.modules-grid,.wanted-grid,.record-fields,.detail-fields{grid-template-columns:1fr}.system-status,.access-panel{align-items:stretch;flex-direction:column}.status-chips{justify-content:flex-start}.section-panel,.restricted-hero{padding:23px}.section-panel h1,.restricted-hero h1{font-size:31px}.detail-media{order:2}.admin-row{grid-template-columns:1fr}.admin-form{grid-template-columns:1fr}.copy-row{flex-direction:column}.primary,.secondary{width:100%}}
'''


def install(bot_module: Any):
    # Renderer V701 usa o núcleo V700 já instalado; nenhuma funcionalidade legada é removida.
    base.home = _home
    base.restricted = _restricted
    base.list_page = _list_page
    base.record_card = _record_card
    base.detail = _detail
    base.photos = _photos
    base.admin_page = _admin
    base.CSS = CSS
    return CentralV701(getattr(bot_module, 'bot', None))


class CentralV701(base.CentralV700):
    async def start(self):
        if self.client is None:
            raise RuntimeError('cliente Discord não encontrado')
        return await super().start()
