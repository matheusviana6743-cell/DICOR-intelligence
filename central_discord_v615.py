# -*- coding: utf-8 -*-
"""DICOR Central V615.

Central web somente leitura.
Nesta etapa, a única fonte sincronizada em tempo real com o Discord é
PROCURADOS. Os demais módulos continuam visíveis no painel, mas ficam
reservados para integração posterior.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from aiohttp import web

PROCURADOS_ID = 1490200533980545097
PORT = int(os.getenv("PORT", "8080"))
COOKIE = "dicor_operador_v615"
SECRET = os.getenv("CENTRAL_DICOR_COOKIE_SECRET", os.getenv("DICOR_COOKIE_SECRET", "dicor-central-v615"))
# Arquivo oficial do emblema disponibilizado pela PF via Wikimedia Commons.
# A versão é PNG com fundo transparente.
PF_LOGO = "https://commons.wikimedia.org/wiki/Special:FilePath/Pol%C3%ADcia%20Federal%20do%20Brasil.png"
# Logo DICOR atual do projeto; o CSS abaixo impede qualquer moldura branca.
DICOR_LOGO = "https://media.discordapp.net/attachments/1426821172237963375/1547778833866817596/image.png?ex=6aa4a8de&is=6aa3575e&hm=95ab0f8951a7c48c3c2aff35c5cfdec8cef0af8add90348445dc7093b7d841d3&=&format=webp&quality=lossless"
ACCOUNT_FILE = Path(os.getenv("CENTRAL_ACCOUNT_FILE", "central_accounts_v615.json"))
CACHE: dict[str, Any] = {"procurados": [], "updated": 0.0, "busy": False}


def esc(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def clean(v: Any) -> str:
    return " ".join(str(v or "").split())


def text_of(m: Any) -> str:
    parts = [getattr(m, "content", "") or ""]
    for e in getattr(m, "embeds", []) or []:
        parts += [getattr(e, "title", "") or "", getattr(e, "description", "") or ""]
        for f in getattr(e, "fields", []) or []:
            parts.append(f"{getattr(f, 'name', '')}: {getattr(f, 'value', '')}")
    return clean(" ".join(x for x in parts if x))


def closed(text: str) -> bool:
    s = clean(text).casefold()
    return any(x in s for x in (
        "capturado", "capturada", "preso", "presa", "encerrado", "encerrada",
        "cancelado", "cancelada", "finalizado", "finalizada"
    ))


def number_from(text: str) -> str:
    for pattern in (r"(?:N[º°O.]?|NO|#)\s*(\d{1,8})", r"\b(\d{4,8})\b"):
        m = re.search(pattern, text or "", re.I)
        if m:
            return f"{int(m.group(1)):04d}"
    return "S/N"


def extract_name(text: str) -> str:
    patterns = (
        r"(?:nome|indivíduo|individuo|procurado)\s*[:=-]\s*([^|•\n]+)",
        r"^([A-ZÀ-Ú][A-Za-zÀ-ú' -]{3,60})\s*[|•]",
    )
    for pattern in patterns:
        m = re.search(pattern, text or "", re.I)
        if m:
            return clean(m.group(1))[:70]
    return clean(text.split("|")[0].split("•")[0])[:70] or "Indivíduo não identificado"


def extract_field(text: str, labels: tuple[str, ...]) -> str:
    label = "|".join(re.escape(x) for x in labels)
    m = re.search(rf"(?:{label})\s*[:=-]\s*([^|•\n]+)", text or "", re.I)
    return clean(m.group(1))[:90] if m else "Não informado"


def media_url(m: Any) -> str:
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
        if url and re.search(r"\.(?:png|jpe?g|webp|gif)(?:\?|$)", url, re.I):
            return url
    return ""


def account_key(qra: str, passport: str) -> str:
    return f"{clean(qra).casefold()}|{clean(passport).casefold()}"


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180_000)
    return base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def password_ok(password: str, stored: str) -> bool:
    try:
        salt_b64, digest_b64 = stored.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180_000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def load_accounts() -> dict[str, Any]:
    try:
        if ACCOUNT_FILE.exists():
            data = json.loads(ACCOUNT_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def save_accounts(data: dict[str, Any]) -> None:
    try:
        ACCOUNT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def session_cookie(qra: str, passport: str) -> str:
    payload = f"{clean(qra)[:45]}|{clean(passport)[:16]}|{int(time.time())}"
    raw = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return raw + "." + sig


def read_session(req: web.Request) -> tuple[str, str] | None:
    token = req.cookies.get(COOKIE, "")
    if "." not in token:
        return None
    try:
        raw, sig = token.rsplit(".", 1)
        payload = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
        expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        qra, passport, issued = payload.split("|", 2)
        if time.time() - int(issued) > 30 * 86400:
            return None
        return qra, passport
    except Exception:
        return None


def img(src: str, cls: str = "logo", alt: str = "") -> str:
    return f'<img class="{cls}" src="{esc(src)}" alt="{esc(alt)}" loading="eager" onerror="this.style.display=\'none\'">'


def page(title: str, body: str, css: str) -> str:
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#07101a"><title>{esc(title)}</title><style>{css}</style></head><body>{body}</body></html>'''


AUTH_CSS = """
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;color:#eef3f7}body{min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 50% 0,#172c45 0,#08121d 38%,#03070b 78%);overflow-x:hidden}.auth{width:min(520px,calc(100% - 28px));padding:34px;border:1px solid #21405e;border-radius:24px;background:linear-gradient(155deg,#0d1a28fa,#050c14f7);box-shadow:0 35px 100px #000c;text-align:center}.auth .logo{width:118px;height:118px;object-fit:contain;margin:0 auto 12px;filter:drop-shadow(0 12px 20px #0008)}.pcpt{font-size:10px;font-weight:900;letter-spacing:2px;color:#9eb1c3}.auth h1{font-size:26px;letter-spacing:1px;margin:9px 0 7px}.sub{font-size:12px;color:#71869a;margin:0 0 23px}.form{text-align:left}.form label{display:block;font-size:9px;letter-spacing:1.5px;color:#aebdca;font-weight:900;margin:15px 0 7px}.form input{width:100%;height:48px;border:1px solid #223d56;background:#08131f;color:#f1f5f8;border-radius:11px;padding:0 14px;outline:none;font-size:14px}.form input:focus{border-color:#c9a33a;box-shadow:0 0 0 3px #c9a33a25}.primary{width:100%;height:50px;border:0;border-radius:11px;margin-top:21px;background:linear-gradient(135deg,#c9a33a,#8f6c18);color:#090b0d;font-weight:900;letter-spacing:.5px;cursor:pointer;box-shadow:0 10px 25px #0008}.first{margin-top:13px;text-align:center;color:#70869b;font-size:10px}.err{padding:11px;border-radius:10px;background:#3b171d;border:1px solid #7b3340;color:#ffd0d5;font-size:11px;margin:12px 0}.secure{margin-top:18px;padding-top:11px;border-top:1px solid #1c3248;color:#5e7489;font-size:9px;letter-spacing:.6px}@media(max-width:600px){.auth{padding:27px 21px}.auth .logo{width:94px;height:94px}.auth h1{font-size:23px}.form input{height:52px;font-size:16px}}
"""


def login_page(error: str = "", next_url: str = "/") -> str:
    err = f'<div class="err">{esc(error)}</div>' if error else ""
    body = f'''<main class="auth">{img(PF_LOGO,"logo","Polícia Federal")}<div class="pcpt">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL</div><h1>ACESSO AO SISTEMA</h1><p class="sub">Central de inteligência e consulta operacional</p>{err}<form class="form" method="post" action="/cadastro-operador"><input type="hidden" name="next" value="{esc(next_url)}"><label>QRA OPERACIONAL</label><input name="qra" maxlength="45" autocomplete="username" placeholder="Digite seu QRA" required><label>PASSAPORTE</label><input name="passaporte" maxlength="20" placeholder="Digite seu passaporte" required><button class="primary" type="submit">ENTRAR&nbsp; →</button></form><div class="first">PRIMEIRO ACESSO? SUA SENHA SERÁ CRIADA NO CADASTRO.</div><div class="secure">PCPT • POLÍCIA CAPITAL / POLÍCIA FEDERAL</div></main>'''
    return page("PCPT • Acesso", body, AUTH_CSS)


def password_page(qra: str, passport: str, next_url: str, error: str = "") -> str:
    err = f'<div class="err">{esc(error)}</div>' if error else ""
    body = f'''<main class="auth">{img(PF_LOGO,"logo","Polícia Federal")}<div class="pcpt">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL</div><h1>CRIAR SENHA DE ACESSO</h1><p class="sub">Primeiro cadastro identificado. Defina uma senha para este operador.</p>{err}<form class="form" method="post" action="/criar-senha"><input type="hidden" name="qra" value="{esc(qra)}"><input type="hidden" name="passaporte" value="{esc(passport)}"><input type="hidden" name="next" value="{esc(next_url)}"><label>NOVA SENHA</label><input type="password" name="senha" minlength="4" maxlength="64" placeholder="Digite uma senha" required><label>CONFIRMAR SENHA</label><input type="password" name="confirmar" minlength="4" maxlength="64" placeholder="Confirme sua senha" required><button class="primary" type="submit">CRIAR ACESSO&nbsp; →</button></form><div class="secure">A senha fica vinculada ao QRA + passaporte deste cadastro.</div></main>'''
    return page("PCPT • Criar senha", body, AUTH_CSS)


async def get_channel(client: Any, cid: int):
    try:
        channel = client.get_channel(cid)
        return channel if channel is not None else await client.fetch_channel(cid)
    except Exception:
        return None


async def collect_procurados(client: Any) -> list[dict[str, Any]]:
    channel = await get_channel(client, PROCURADOS_ID)
    if channel is None:
        return []
    rows: list[dict[str, Any]] = []
    try:
        # Lê a base do canal principal de Procurados. Limit 300 evita uma rajada
        # desnecessária contra a API e cobre uma base grande de registros ativos.
        async for message in channel.history(limit=300):
            text = text_of(message)
            if not text or closed(text):
                continue
            rows.append({
                "id": getattr(message, "id", 0),
                "number": number_from(text),
                "name": extract_name(text),
                "crime": extract_field(text, ("crime", "crimes", "acusação", "acusacao")),
                "status": extract_field(text, ("status", "situação", "situacao")),
                "created": getattr(message, "created_at", datetime.now(timezone.utc)),
                "url": getattr(message, "jump_url", "#"),
                "image": media_url(message),
                "preview": text[:300],
            })
    except Exception:
        return rows
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("id") or f"{row['number']}|{row['name']}")
        unique[key] = row
    return sorted(unique.values(), key=lambda r: r["created"], reverse=True)


async def refresh(client: Any) -> None:
    if CACHE["busy"]:
        return
    CACHE["busy"] = True
    try:
        result = await collect_procurados(client)
        CACHE["procurados"] = result
        CACHE["updated"] = time.time()
    finally:
        CACHE["busy"] = False


async def refresh_loop(client: Any) -> None:
    # O rate guard V615 substitui este loop por um ciclo de 5 minutos após READY.
    while True:
        try:
            await refresh(client)
        except Exception:
            pass
        await asyncio.sleep(300)


APP_CSS = """
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;background:#04080d;color:#eaf0f5}a{text-decoration:none;color:inherit}.app{min-height:100vh;display:grid;grid-template-columns:245px 1fr}.side{position:sticky;top:0;height:100vh;padding:18px 14px;border-right:1px solid #1d2c3b;background:linear-gradient(180deg,#07121d,#03070b)}.brand{display:flex;align-items:center;gap:11px;padding:4px 6px 20px;border-bottom:1px solid #1d2c3b}.brand img{width:54px;height:54px;object-fit:contain;filter:drop-shadow(0 7px 13px #0009)}.brand b{font-size:15px;letter-spacing:2px}.brand small{display:block;color:#d1ad43;font-size:8px;letter-spacing:2px;margin-top:3px}.side-note{margin-top:20px;padding:14px;border:1px solid #263b50;border-radius:12px;color:#71869a;font-size:9px;line-height:1.8}.side-note strong{color:#d1ad43}.main{min-width:0;padding:20px 26px 45px}.top{display:flex;align-items:center;justify-content:space-between;gap:15px;padding-bottom:15px;border-bottom:1px solid #182938}.pcpt-title{font-size:12px;font-weight:900;letter-spacing:1.7px}.pcpt-title span{display:block;color:#d1ad43;font-size:9px;letter-spacing:1.2px;margin-top:5px}.operator{display:flex;align-items:center;gap:8px;color:#8ca0b3;font-size:9px}.online{width:7px;height:7px;border-radius:50%;background:#d1ad43;box-shadow:0 0 12px #d1ad43}.hero{position:relative;overflow:hidden;margin-top:18px;padding:27px;border:1px solid #66521e;border-radius:17px;background:linear-gradient(115deg,#0b1825,#08111a 56%,#080d13);box-shadow:inset 0 0 60px #d1ad4310}.hero:after{content:'';position:absolute;right:-100px;top:-130px;width:390px;height:390px;border-radius:50%;border:1px solid #d1ad4328;box-shadow:0 0 0 35px #d1ad4308,0 0 0 70px #d1ad4304}.eyebrow{color:#d1ad43;font-size:9px;letter-spacing:2.3px;font-weight:900}.hero h1{margin:8px 0 7px;font-size:37px;letter-spacing:1px}.hero p{margin:0;color:#788da1;font-size:11px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px}.stat{padding:14px;border:1px solid #273c50;border-radius:12px;background:#07111b}.stat span{font-size:8px;color:#71869a;letter-spacing:1.2px}.stat b{display:block;margin-top:7px;font-size:27px;color:#dce6ef}.stat.gold b{color:#d1ad43}.stat.blue b{color:#74aee3}.wanted{margin-top:15px;border:1px solid #253a4e;border-radius:15px;background:#060d14;overflow:hidden}.wanted-head{display:flex;align-items:center;justify-content:space-between;padding:15px 16px;border-bottom:1px solid #1c2d3d}.wanted-head b{font-size:11px;letter-spacing:1.3px;color:#e8edf2}.wanted-head span{color:#7b90a4;font-size:9px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;padding:12px}.card{min-width:0;border:1px solid #294158;border-radius:12px;background:linear-gradient(155deg,#0c1926,#060e16);overflow:hidden}.photo{height:145px;background:radial-gradient(circle,#14283b,#060d14);display:grid;place-items:center;overflow:hidden}.photo img{width:100%;height:100%;object-fit:cover;filter:saturate(.8) contrast(1.05)}.placeholder{font-size:31px;color:#c7a43d}.card-body{padding:11px}.tag{display:inline-block;padding:4px 7px;border-radius:5px;background:#3b3012;color:#e7c65f;border:1px solid #725b1d;font-size:7px;font-weight:900;letter-spacing:1px}.card h3{font-size:11px;margin:8px 0 5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{font-size:8px;color:#8296a9;line-height:1.7;min-height:39px}.details{display:block;margin-top:9px;padding:9px;border:1px solid #725b1d;border-radius:8px;text-align:center;color:#dfbe55;font-size:8px;font-weight:900;background:#171308}.access{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-top:14px;padding:17px 19px;border:1px solid #66521e;border-radius:13px;background:linear-gradient(110deg,#151208,#0b0f13)}.access strong{display:block;color:#dfbe55;font-size:12px}.access span{display:block;color:#827554;font-size:8px;margin-top:5px}.access-btn{padding:13px 18px;border-radius:9px;background:linear-gradient(135deg,#d7b54b,#8f6b17);color:#090b0d;font-size:10px;font-weight:900;white-space:nowrap}.foot{text-align:center;margin-top:20px;color:#526678;font-size:8px}.empty{padding:40px;text-align:center;color:#63788c;font-size:10px}.module-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:18px}.module{padding:20px;border:1px solid #66521e;border-radius:13px;background:linear-gradient(155deg,#0d1217,#080b0f)}.module h3{margin:0 0 8px;color:#dfbe55;font-size:13px}.module p{margin:0;color:#75899d;font-size:10px;line-height:1.6}.module a{display:block;margin-top:14px;padding:11px;text-align:center;border-radius:8px;background:#151207;border:1px solid #5f4b18;color:#dfbe55;font-size:9px;font-weight:900}.module.disabled{opacity:.68}.module.disabled a{color:#687b8d;border-color:#263746;background:#0b1117}.back{display:inline-block;color:#d0ad45;font-size:10px;margin-top:15px}@media(max-width:1100px){.grid{grid-template-columns:repeat(3,1fr)}}@media(max-width:800px){.app{display:block}.side{position:relative;height:auto;padding:12px 14px}.brand{border:0;padding-bottom:8px}.side-note{display:none}.main{padding:13px 12px 30px}.grid{grid-template-columns:repeat(2,1fr);padding:9px}.photo{height:150px}.hero{padding:21px}.hero h1{font-size:30px}.access{align-items:stretch;flex-direction:column}.access-btn{text-align:center}.module-grid{grid-template-columns:1fr 1fr}}@media(max-width:480px){.top{align-items:flex-start}.operator{font-size:0}.hero h1{font-size:27px}.stats{grid-template-columns:1fr 1fr}.grid{gap:7px}.card h3{font-size:10px}.photo{height:125px}.module-grid{grid-template-columns:1fr}}
"""


def card(row: dict[str, Any]) -> str:
    image = f'<img src="{esc(row.get("image"))}" alt="" loading="lazy">' if row.get("image") else '<div class="placeholder">◉</div>'
    dt = row.get("created")
    try:
        date = dt.astimezone().strftime("%d/%m/%Y • %H:%M")
    except Exception:
        date = "--"
    return f'''<article class="card"><div class="photo">{image}</div><div class="card-body"><span class="tag">PROCURADO</span><h3>{esc(row.get("name"))}</h3><div class="meta">Nº {esc(row.get("number"))}<br>Crime: {esc(row.get("crime"))}<br>Registro: {esc(date)}</div><a class="details" href="{esc(row.get("url") or '#')}" target="_blank" rel="noopener">VER REGISTRO&nbsp; →</a></div></article>'''


def dashboard(rows: list[dict[str, Any]], qra: str, passport: str) -> str:
    total = len(rows)
    cards = "".join(card(r) for r in rows[:12]) or '<div class="empty">Nenhum procurado ativo encontrado no Discord.</div>'
    updated = datetime.fromtimestamp(CACHE["updated"], tz=timezone.utc).astimezone().strftime("%d/%m/%Y • %H:%M") if CACHE["updated"] else "aguardando sincronização"
    body = f'''<div class="app"><aside class="side"><div class="brand">{img(DICOR_LOGO,"","DICOR")}<div><b>DICOR</b><small>INTELIGÊNCIA</small></div></div><div class="side-note"><strong>PCPT / POLÍCIA FEDERAL</strong><br><br>CONSULTA INTERNA<br>SISTEMA SOMENTE LEITURA<br><br>Fonte: Discord • Procurados</div></aside><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i>{esc(qra)} • {esc(passport)}</div></header><section class="hero"><div class="eyebrow">CENTRAL DICOR • MONITORAMENTO</div><h1>PROCURADOS</h1><p>Base sincronizada diretamente com o canal de Procurados do Discord.</p></section><section class="stats"><div class="stat gold"><span>TOTAL ATIVOS</span><b>{total}</b></div><div class="stat blue"><span>REGISTROS EXIBIDOS</span><b>{min(total,12)}</b></div><div class="stat"><span>ÚLTIMA SINCRONIZAÇÃO</span><b style="font-size:13px">{esc(updated)}</b></div></section><section class="wanted"><div class="wanted-head"><b>PROCURADOS EM DESTAQUE</b><span>DISCORD • AO VIVO</span></div><div class="grid">{cards}</div></section><a class="access" href="/funcionalidades"><div><strong>ACESSAR TODAS AS FUNCIONALIDADES</strong><span>BOLETINS • PERÍCIAS • BANCO DE DADOS • ÁRVORE • OPERAÇÕES</span></div><div class="access-btn">ACESSAR&nbsp; →</div></a><div class="foot">DICOR • INTELIGÊNCIA E OPERAÇÕES ESPECIAIS</div></main></div>'''
    return page("DICOR • Procurados", body, APP_CSS)


def functionalities(qra: str) -> str:
    modules = [
        ("PROCURADOS", "Integrado agora com o Discord e atualizado automaticamente.", "/", True),
        ("BOLETINS", "Módulo preparado para integração futura.", "#", False),
        ("PERÍCIAS", "Módulo preparado para integração futura.", "#", False),
        ("BANCO DE DADOS", "Módulo preparado para integração futura.", "#", False),
        ("ÁRVORE DE INTELIGÊNCIA", "Módulo preparado para integração futura.", "#", False),
        ("OPERAÇÕES", "Módulo preparado para integração futura.", "#", False),
    ]
    cards = "".join(f'<article class="module {"" if live else "disabled"}"><h3>{esc(name)}</h3><p>{esc(desc)}</p><a href="{esc(url)}">{("ABRIR MÓDULO" if live else "EM BREVE")}&nbsp; →</a></article>' for name, desc, url, live in modules)
    body = f'''<div class="app"><aside class="side"><div class="brand">{img(DICOR_LOGO,"","DICOR")}<div><b>DICOR</b><small>INTELIGÊNCIA</small></div></div></aside><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • TODAS AS FUNCIONALIDADES</span></div><div class="operator"><i class="online"></i>{esc(qra)}</div></header><div class="hero"><div class="eyebrow">DICOR • ACESSO OPERACIONAL</div><h1>FUNCIONALIDADES</h1><p>Todos os módulos já ficam no mesmo padrão visual DICOR.</p></div><div class="module-grid">{cards}</div><a class="back" href="/">← Voltar aos Procurados</a></main></div>'''
    return page("DICOR • Funcionalidades", body, APP_CSS)


async def start_server(client: Any) -> web.AppRunner:
    app = web.Application()

    @web.middleware
    async def errors(req: web.Request, handler):
        try:
            return await handler(req)
        except web.HTTPException:
            raise
        except Exception:
            if req.path == "/health":
                return web.json_response({"ok": False})
            return web.Response(text="Central temporariamente indisponível. Tente novamente.", status=503, content_type="text/plain")

    app.middlewares.append(errors)

    async def auth_required(req: web.Request) -> tuple[str, str]:
        session = read_session(req)
        if session:
            return session
        target = req.path
        if req.query_string:
            target += "?" + req.query_string
        raise web.HTTPFound("/cadastro-operador?next=" + quote(target, safe="/?=&"))

    async def health(req: web.Request):
        return web.json_response({"ok": True, "service": "DICOR Central V615", "source": "Discord/Procurados", "cache_age": round(time.time() - CACHE["updated"], 2) if CACHE["updated"] else None})

    async def get_login(req: web.Request):
        return web.Response(text=login_page(next_url=req.query.get("next", "/")), content_type="text/html")

    async def post_login(req: web.Request):
        data = await req.post()
        qra = clean(data.get("qra"))
        passport = clean(data.get("passaporte"))
        next_url = clean(data.get("next")) or "/"
        if not qra or not passport:
            return web.Response(text=login_page("Preencha QRA e passaporte.", next_url), content_type="text/html")
        stored = load_accounts().get(account_key(qra, passport))
        if not stored:
            return web.Response(text=password_page(qra, passport, next_url), content_type="text/html")
        body = f'''<main class="auth">{img(PF_LOGO,"logo","Polícia Federal")}<div class="pcpt">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL</div><h1>CONFIRMAR ACESSO</h1><p class="sub">Operador cadastrado. Digite sua senha para continuar.</p><form class="form" method="post" action="/entrar"><input type="hidden" name="qra" value="{esc(qra)}"><input type="hidden" name="passaporte" value="{esc(passport)}"><input type="hidden" name="next" value="{esc(next_url)}"><label>SENHA</label><input type="password" name="senha" autocomplete="current-password" placeholder="Digite sua senha" required><button class="primary">ENTRAR&nbsp; →</button></form></main>'''
        return web.Response(text=page("PCPT • Senha", body, AUTH_CSS), content_type="text/html")

    async def create_password(req: web.Request):
        data = await req.post()
        qra, passport = clean(data.get("qra")), clean(data.get("passaporte"))
        password, confirm = str(data.get("senha") or ""), str(data.get("confirmar") or "")
        next_url = clean(data.get("next")) or "/"
        if len(password) < 4 or password != confirm:
            return web.Response(text=password_page(qra, passport, next_url, "As senhas precisam ser iguais e ter pelo menos 4 caracteres."), content_type="text/html")
        accounts = load_accounts()
        accounts[account_key(qra, passport)] = password_hash(password)
        save_accounts(accounts)
        response = web.HTTPFound(next_url if next_url.startswith("/") else "/")
        response.set_cookie(COOKIE, session_cookie(qra, passport), httponly=True, samesite="Lax", max_age=30*86400, secure=False)
        raise response

    async def enter(req: web.Request):
        data = await req.post()
        qra, passport, password = clean(data.get("qra")), clean(data.get("passaporte")), str(data.get("senha") or "")
        next_url = clean(data.get("next")) or "/"
        stored = load_accounts().get(account_key(qra, passport), "")
        if not stored or not password_ok(password, stored):
            body = f'''<main class="auth">{img(PF_LOGO,"logo","Polícia Federal")}<div class="pcpt">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL</div><h1>ACESSO NEGADO</h1><p class="sub">QRA, passaporte ou senha incorretos.</p><a class="primary" style="display:block;padding-top:16px" href="/cadastro-operador">VOLTAR AO ACESSO</a></main>'''
            return web.Response(text=page("PCPT • Acesso negado", body, AUTH_CSS), status=401, content_type="text/html")
        response = web.HTTPFound(next_url if next_url.startswith("/") else "/")
        response.set_cookie(COOKIE, session_cookie(qra, passport), httponly=True, samesite="Lax", max_age=30*86400, secure=False)
        raise response

    async def dashboard_route(req: web.Request):
        qra, passport = await auth_required(req)
        return web.Response(text=dashboard(CACHE["procurados"], qra, passport), content_type="text/html")

    async def funcs(req: web.Request):
        qra, _ = await auth_required(req)
        return web.Response(text=functionalities(qra), content_type="text/html")

    async def procurados(req: web.Request):
        qra, passport = await auth_required(req)
        return web.Response(text=dashboard(CACHE["procurados"], qra, passport), content_type="text/html")

    app.router.add_get("/health", health)
    app.router.add_get("/cadastro-operador", get_login)
    app.router.add_post("/cadastro-operador", post_login)
    app.router.add_post("/criar-senha", create_password)
    app.router.add_post("/entrar", enter)
    app.router.add_get("/", dashboard_route)
    app.router.add_get("/procurados", procurados)
    app.router.add_get("/funcionalidades", funcs)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    return runner


class CentralV615:
    def __init__(self, client: Any):
        self.client = client
        self.runner: web.AppRunner | None = None
        self.task: asyncio.Task | None = None

    async def start(self):
        if self.runner is not None:
            return
        self.runner = await start_server(self.client)
        self.task = asyncio.create_task(refresh_loop(self.client))


def install(bot_module: Any) -> CentralV615:
    client = getattr(bot_module, "bot", None)
    if client is None:
        raise RuntimeError("cliente Discord ausente")
    return CentralV615(client)
