# -*- coding: utf-8 -*-
"""Patch V616 da Central DICOR.

Mantém a Central V613/V614 e adiciona uma camada específica para Procurados:
- leitura ao vivo do canal de Procurados do Discord;
- coleta de nome, RG/passaporte, crime, status e imagem;
- pesquisa por nome ou RG/passaporte;
- painel com identidade visual DICOR azul/gold;
- tratamento visual das logos para não exibir o fundo branco.
"""
from __future__ import annotations

import asyncio
import html
import re
import time
from datetime import datetime, timezone
from typing import Any

import central_discord_v613 as base

PROCURADOS_SCAN_LIMIT = 1000


def clean(v: Any) -> str:
    return " ".join(str(v or "").split())


def esc(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def text_of(m: Any) -> str:
    parts = [getattr(m, "content", "") or ""]
    for e in getattr(m, "embeds", []) or []:
        parts.extend([getattr(e, "title", "") or "", getattr(e, "description", "") or ""])
        for f in getattr(e, "fields", []) or []:
            parts.append(f"{getattr(f, 'name', '')}: {getattr(f, 'value', '')}")
    return clean(" ".join(x for x in parts if x))


def extract_label(text: str, labels: tuple[str, ...], default: str = "Não informado") -> str:
    label = "|".join(re.escape(x) for x in labels)
    m = re.search(rf"(?:{label})\s*[:=-]\s*([^|•\n]+)", text, re.I)
    return clean(m.group(1))[:100] if m else default


def extract_name(text: str) -> str:
    value = extract_label(text, ("nome completo", "nome", "indivíduo", "individuo", "procurado"), "")
    if value:
        return value
    for p in (r"^([^|•]+)\s*[|•]", r"^([A-ZÀ-Ú][A-Za-zÀ-ú' -]{3,70})"):
        m = re.search(p, text)
        if m:
            value = clean(m.group(1))
            if value and not value.casefold().startswith(("procurado", "registro", "rg")):
                return value[:80]
    return "Indivíduo não identificado"


def extract_rg(text: str) -> str:
    value = extract_label(text, ("rg", "registro geral", "passaporte", "id", "identidade"), "")
    if value:
        return value
    m = re.search(r"\b(?:RG|PASSAPORTE|ID)\s*#?\s*[:=-]?\s*([A-Z0-9.-]{3,20})\b", text, re.I)
    return clean(m.group(1)) if m else "Não informado"


def image_url(m: Any) -> str:
    for e in getattr(m, "embeds", []) or []:
        image = getattr(e, "image", None)
        url = getattr(image, "url", "") if image else ""
        if url:
            return url
        thumb = getattr(e, "thumbnail", None)
        url = getattr(thumb, "url", "") if thumb else ""
        if url:
            return url
    for a in getattr(m, "attachments", []) or []:
        url = getattr(a, "url", "")
        if url:
            return url
    return ""


def is_closed(text: str) -> bool:
    s = clean(text).casefold()
    return any(x in s for x in (
        "capturado", "capturada", "preso", "presa", "encerrado", "encerrada",
        "cancelado", "cancelada", "finalizado", "finalizada",
    ))


async def collect_procurados(client: Any) -> list[dict[str, Any]]:
    channel = await base.get_channel(client, base.PROCURADOS_ID)
    if channel is None:
        return []

    out: list[dict[str, Any]] = []
    try:
        async for m in channel.history(limit=PROCURADOS_SCAN_LIMIT, oldest_first=False):
            text = text_of(m)
            if not text or is_closed(text):
                continue
            created = getattr(m, "created_at", None) or datetime.now(timezone.utc)
            name = extract_name(text)
            rg = extract_rg(text)
            crime = extract_label(text, ("crime", "crimes", "acusação", "acusacao"))
            status = extract_label(text, ("status", "situação", "situacao"), "ATIVO")
            out.append({
                "number": base.number_from(text),
                "name": name,
                "rg": rg,
                "crime": crime,
                "status": status,
                "created": created,
                "url": getattr(m, "jump_url", "#"),
                "image": image_url(m),
                "preview": text[:500],
                "source_id": getattr(m, "id", 0),
            })
    except Exception as exc:
        print(f"⚠️ Central V616 Procurados: {type(exc).__name__}: {exc}", flush=True)
        return []

    unique: dict[int | str, dict[str, Any]] = {}
    for row in out:
        key = row.get("source_id") or row.get("url") or f"{row.get('name')}|{row.get('rg')}"
        unique[key] = row
    return sorted(unique.values(), key=lambda r: r.get("created") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


# A V613 tinha um refresh a cada 20s. V616 deixa a guarda V615 controlar o ritmo.
base.collect_procurados = collect_procurados

# Ajuste visual: mantém as logos sem uma caixa branca aparente.
base.APP_CSS += """
.logo,.brand img{background:transparent!important;mix-blend-mode:multiply;filter:drop-shadow(0 5px 12px rgba(0,0,0,.45));}
.brand img{width:52px;height:52px;object-fit:contain;}
.search-box{margin-top:16px;padding:14px;border:1px solid #284967;border-radius:14px;background:#08121e;display:flex;gap:9px;align-items:center}
.search-box input{flex:1;min-width:0;height:44px;border:1px solid #23435e;border-radius:9px;background:#0b1826;color:#eef5fb;padding:0 13px;outline:none;font-size:12px}
.search-box input:focus{border-color:#4b9ce6;box-shadow:0 0 0 3px #1d5a9630}
.search-box button{height:44px;border:0;border-radius:9px;padding:0 17px;background:linear-gradient(135deg,#dcb65c,#8e6517);color:#090c10;font-weight:900;cursor:pointer}
.result-note{margin:12px 2px;color:#7890a5;font-size:9px}
.card .rg{color:#9bb3c8;font-size:8px;margin-top:2px}
"""


def searched(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    q = clean(query).casefold()
    if not q:
        return rows
    return [r for r in rows if q in clean(r.get("name")).casefold() or q in clean(r.get("rg")).casefold()]


def card_v616(row: dict[str, Any]) -> str:
    image = f'<img src="{esc(row.get("image"))}" alt="" loading="lazy">' if row.get("image") else '<div class="placeholder">◉</div>'
    dt = row.get("created")
    try:
        date = dt.astimezone().strftime("%d/%m/%Y • %H:%M")
    except Exception:
        date = "--"
    return f'''<article class="card"><div class="photo">{image}</div><div class="card-body"><span class="tag">PROCURADO</span><h3>{esc(row.get("name"))}</h3><div class="rg">RG/PASSAPORTE: {esc(row.get("rg"))}</div><div class="meta">Nº {esc(row.get("number"))}<br>Crime: {esc(row.get("crime"))}<br>Atualizado: {esc(date)}</div><a class="details" href="{esc(row.get("url") or '#')}" target="_blank">VER REGISTRO&nbsp; →</a></div></article>'''


def dashboard_v616(rows: list[dict[str, Any]], qra: str, passport: str, query: str = "") -> str:
    result = searched(rows, query)
    cards = "".join(card_v616(r) for r in result[:100]) or '<div class="empty">Nenhum procurado encontrado para esta pesquisa.</div>'
    updated = datetime.now().strftime("%d/%m/%Y • %H:%M")
    body = f'''<div class="app"><aside class="side"><div class="brand">{base.img(base.DICOR_LOGO, "", "DICOR")}<div><b>DICOR</b><small>INTELIGÊNCIA</small></div></div><div class="side-note">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<br><br>CONSULTA INTERNA<br>SISTEMA SOMENTE LEITURA</div></aside><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i> {esc(qra)} • {esc(passport)}</div></header><section class="hero"><div class="eyebrow">CENTRAL DICOR • MONITORAMENTO</div><h1>PROCURADOS</h1><p>Consulta integrada diretamente ao canal de Procurados do Discord.</p></section><section class="search-box"><form style="display:flex;gap:9px;width:100%" method="get" action="/procurados"><input name="q" value="{esc(query)}" placeholder="Pesquisar por nome ou RG / passaporte..."><button type="submit">PESQUISAR</button></form></section><div class="result-note">{len(result)} resultado(s) • sincronizado do Discord • {esc(updated)}</div><section class="wanted"><div class="wanted-head"><b>BASE DE PROCURADOS</b><span>{len(rows)} REGISTRO(S) ATIVO(S)</span></div><div class="grid">{cards}</div></section><a class="access" href="/funcionalidades"><div><strong>ACESSAR TODAS AS FUNCIONALIDADES</strong><span>BOLETINS • PERÍCIAS • BANCO DE DADOS • ÁRVORE • OPERAÇÕES</span></div><div class="access-btn">ACESSAR&nbsp; →</div></a><div class="foot">DICOR • INTELIGÊNCIA E OPERAÇÕES ESPECIAIS</div></main></div>'''
    return base.page("DICOR • Procurados", body, base.APP_CSS)


base.dashboard = dashboard_v616


async def start_server_v616(client: Any):
    """Mesmo servidor da V613, com pesquisa dedicada de Procurados."""
    app = base.web.Application()

    @base.web.middleware
    async def errors(req: base.web.Request, handler):
        try:
            return await handler(req)
        except base.web.HTTPException:
            raise
        except Exception:
            if req.path == "/health":
                return base.web.json_response({"ok": False})
            return base.web.Response(text="Central temporariamente indisponível. Tente novamente.", status=503, content_type="text/plain")

    app.middlewares.append(errors)

    async def auth_required(req: base.web.Request):
        session = base.read_session(req)
        if session:
            return session
        target = req.path + (("?" + req.query_string) if req.query_string else "")
        raise base.web.HTTPFound("/cadastro-operador?next=" + base.web.URLEncode(target))

    async def health(req):
        return base.web.json_response({"ok": True, "service": "DICOR Central V616", "procurados": len(base.CACHE.get("procurados", []))})

    async def get_login(req):
        return base.web.Response(text=base.login_page(next_url=req.query.get("next", "/")), content_type="text/html")

    async def post_login(req):
        data = await req.post()
        qra, passport = clean(data.get("qra")), clean(data.get("passaporte"))
        next_url = clean(data.get("next")) or "/"
        if not qra or not passport:
            return base.web.Response(text=base.login_page("Preencha QRA e passaporte.", next_url), content_type="text/html")
        accounts = base.load_accounts()
        key = base.account_key(qra, passport)
        stored = accounts.get(key)
        if not stored:
            return base.web.Response(text=base.password_page(qra, passport, next_url), content_type="text/html")
        body = f'''<main class="auth">{base.img(base.PF_LOGO, "logo", "Polícia Federal")}<div class="pcpt">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL</div><h1>CONFIRMAR ACESSO</h1><p class="sub">Operador cadastrado. Digite sua senha para continuar.</p><form class="form" method="post" action="/entrar"><input type="hidden" name="qra" value="{esc(qra)}"><input type="hidden" name="passaporte" value="{esc(passport)}"><input type="hidden" name="next" value="{esc(next_url)}"><label>SENHA</label><input type="password" name="senha" autocomplete="current-password" placeholder="Digite sua senha" required><button class="primary gold">ENTRAR&nbsp; →</button></form></main>'''
        return base.web.Response(text=base.page("PCPT • Senha", body, base.AUTH_CSS), content_type="text/html")

    async def create_password(req):
        data = await req.post()
        qra, passport = clean(data.get("qra")), clean(data.get("passaporte"))
        password, confirm = str(data.get("senha") or ""), str(data.get("confirmar") or "")
        next_url = clean(data.get("next")) or "/"
        if len(password) < 4 or password != confirm:
            return base.web.Response(text=base.password_page(qra, passport, next_url, "As senhas precisam ser iguais e ter pelo menos 4 caracteres."), content_type="text/html")
        accounts = base.load_accounts()
        accounts[base.account_key(qra, passport)] = base.password_hash(password)
        base.save_accounts(accounts)
        response = base.web.HTTPFound(next_url if next_url.startswith("/") else "/")
        response.set_cookie(base.COOKIE, base.session_cookie(qra, passport), httponly=True, samesite="Lax", max_age=30*86400, secure=False)
        raise response

    async def enter(req):
        data = await req.post()
        qra, passport, password = clean(data.get("qra")), clean(data.get("passaporte")), str(data.get("senha") or "")
        next_url = clean(data.get("next")) or "/"
        stored = base.load_accounts().get(base.account_key(qra, passport), "")
        if not stored or not base.password_ok(password, stored):
            body = f'''<main class="auth">{base.img(base.PF_LOGO, "logo", "Polícia Federal")}<div class="pcpt">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL</div><h1>ACESSO NEGADO</h1><p class="sub">QRA, passaporte ou senha incorretos.</p><a class="primary gold" style="display:block;text-decoration:none;padding-top:16px" href="/cadastro-operador">VOLTAR AO ACESSO</a></main>'''
            return base.web.Response(text=base.page("PCPT • Acesso negado", body, base.AUTH_CSS), status=401, content_type="text/html")
        response = base.web.HTTPFound(next_url if next_url.startswith("/") else "/")
        response.set_cookie(base.COOKIE, base.session_cookie(qra, passport), httponly=True, samesite="Lax", max_age=30*86400, secure=False)
        raise response

    async def dashboard(req):
        qra, passport = await auth_required(req)
        return base.web.Response(text=dashboard_v616(base.CACHE.get("procurados", []), qra, passport, req.query.get("q", "")), content_type="text/html")

    async def funcs(req):
        qra, _ = await auth_required(req)
        return base.web.Response(text=base.functionalities(qra), content_type="text/html")

    async def boletins(req):
        qra, _ = await auth_required(req)
        return base.web.Response(text=base.listing("BOLETINS", "Boletins ativos consultados diretamente do Discord.", base.CACHE.get("bo", []), qra, "bo"), content_type="text/html")

    async def pericias(req):
        qra, _ = await auth_required(req)
        return base.web.Response(text=base.listing("PERÍCIAS", "Perícias externas ativas consultadas diretamente do Discord.", base.CACHE.get("pericia", []), qra, "pe"), content_type="text/html")

    async def empty_module(req, title, subtitle, kind):
        qra, _ = await auth_required(req)
        return base.web.Response(text=base.listing(title, subtitle, [], qra, kind), content_type="text/html")

    app.router.add_get("/health", health)
    app.router.add_get("/cadastro-operador", get_login)
    app.router.add_post("/cadastro-operador", post_login)
    app.router.add_post("/criar-senha", create_password)
    app.router.add_post("/entrar", enter)
    app.router.add_get("/", dashboard)
    app.router.add_get("/procurados", dashboard)
    app.router.add_get("/funcionalidades", funcs)
    app.router.add_get("/boletins", boletins)
    app.router.add_get("/pericias", pericias)
    app.router.add_get("/fichas", lambda req: empty_module(req, "BANCO DE DADOS", "Módulo de consulta integrado à Central.", "db"))
    app.router.add_get("/arvore", lambda req: empty_module(req, "ÁRVORE DE INTELIGÊNCIA", "Estrutura de vínculos e informações.", "tree"))

    runner = base.web.AppRunner(app, access_log=None)
    await runner.setup()
    site = base.web.TCPSite(runner, "0.0.0.0", base.PORT)
    await site.start()
    return runner


base.start_server = start_server_v616


def install(bot_module: Any):
    # Reaproveita o CentralV613 e o guard V615, mas com o servidor/coletores V616.
    return base.install(bot_module)
