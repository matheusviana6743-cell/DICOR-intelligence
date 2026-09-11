# -*- coding: utf-8 -*-
"""DICOR Central V613.

Central web somente leitura. O foco da home e Procurados; as demais
funcionalidades ficam em um unico acesso separado.
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

from aiohttp import web

BO_ID = 1525762770253910136
PERICIA_ID = 1490200524367200297
PROCURADOS_ID = 1490200533980545097
PORT = int(os.getenv("PORT", "8080"))
COOKIE = "dicor_operador_v613"
SECRET = os.getenv("CENTRAL_DICOR_COOKIE_SECRET", os.getenv("DICOR_COOKIE_SECRET", "dicor-central-v613"))
PF_LOGO = "https://www.gov.br/pf/pt-br/principios-fundamentais/simbolos-da-policia-federal-2/emblema.png"
DICOR_LOGO = "https://media.discordapp.net/attachments/1426821172237963375/1547778833866817596/image.png?ex=6aa4a8de&is=6aa3575e&hm=95ab0f8951a7c48c3c2aff35c5cfdec8cef0af8add90348445dc7093b7d841d3&=&format=webp&quality=lossless"
ACCOUNT_FILE = Path(os.getenv("CENTRAL_ACCOUNT_FILE", "central_accounts_v613.json"))
CACHE: dict[str, Any] = {"procurados": [], "bo": [], "pericia": [], "updated": 0.0, "busy": False}


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
    return any(x in s for x in ("capturado", "capturada", "preso", "presa", "encerrado", "encerrada", "cancelado", "cancelada", "finalizado", "finalizada"))


def number_from(text: str) -> str:
    for pattern in (r"(?:N[º°O.]?|NO|#)\s*(\d{1,8})", r"\b(\d{4,8})\b"):
        m = re.search(pattern, text or "", re.I)
        if m:
            return f"{int(m.group(1)):04d}"
    return "S/N"


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
    return f'<img class="{cls}" src="{esc(src)}" alt="{esc(alt)}" onerror="this.style.display=\'none\'">'


def page(title: str, body: str, css: str, script: str = "") -> str:
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#07111c"><title>{esc(title)}</title><style>{css}</style></head><body>{body}<script>{script}</script></body></html>'''


AUTH_CSS = """
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;color:#e9eef5}body{min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 50% 0,#16365c 0,#091321 34%,#05090f 72%);overflow-x:hidden}body:before{content:'';position:fixed;inset:0;background:linear-gradient(115deg,transparent 0 55%,#1d426d18 55% 57%,transparent 57%),linear-gradient(0deg,#0008,#0000);pointer-events:none}.auth{width:min(520px,calc(100% - 28px));position:relative;padding:34px 34px 28px;border:1px solid #34516f;border-radius:24px;background:linear-gradient(155deg,#101d2bfa,#07101bf7);box-shadow:0 35px 100px #000b,0 0 50px #0b3a681c;text-align:center}.auth .logo{width:118px;height:118px;object-fit:contain;margin:0 auto 12px;filter:drop-shadow(0 12px 18px #0008)}.pcpt{font-size:11px;font-weight:800;letter-spacing:2px;color:#aebdcd}.auth h1{font-size:27px;letter-spacing:1px;margin:8px 0 7px}.sub{font-size:12px;color:#77899c;margin:0 0 24px}.form{text-align:left}.form label{display:block;font-size:9px;letter-spacing:1.5px;color:#aebdcc;font-weight:800;margin:15px 0 7px}.form input{width:100%;height:48px;border:1px solid #263f5b;background:#0b1725;color:#f1f5f8;border-radius:11px;padding:0 14px;outline:none;font-size:14px}.form input:focus{border-color:#2f72ba;box-shadow:0 0 0 3px #1d5a9630}.primary{width:100%;height:50px;border:0;border-radius:11px;margin-top:21px;background:linear-gradient(135deg,#1d67b2,#0c3c72);color:#fff;font-weight:900;letter-spacing:.5px;cursor:pointer;box-shadow:0 10px 25px #001c3c88}.gold{background:linear-gradient(135deg,#f0ce69,#a87517);color:#080b0e}.first{margin-top:13px;text-align:center;color:#6387ab;font-size:10px}.err{padding:11px;border-radius:10px;background:#441b20;border:1px solid #8b3944;color:#ffcbd0;font-size:11px;margin:12px 0}.secure{margin-top:18px;padding:11px;border-top:1px solid #20364e;color:#63778d;font-size:9px;letter-spacing:.6px}@media(max-width:600px){.auth{padding:27px 21px 23px;border-radius:20px}.auth .logo{width:94px;height:94px}.auth h1{font-size:23px}.form input{height:52px;font-size:16px}}
"""


def login_page(error: str = "", next_url: str = "/") -> str:
    err = f'<div class="err">{esc(error)}</div>' if error else ""
    body = f'''<main class="auth">{img(PF_LOGO, "logo", "Polícia Federal")}<div class="pcpt">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL</div><h1>ACESSO AO SISTEMA</h1><p class="sub">Central de inteligência e consulta operacional</p>{err}<form class="form" method="post" action="/cadastro-operador"><input type="hidden" name="next" value="{esc(next_url)}"><label>QRA OPERACIONAL</label><input name="qra" maxlength="45" autocomplete="username" placeholder="Digite seu QRA" required><label>PASSAPORTE</label><input name="passaporte" maxlength="20" inputmode="text" placeholder="Digite seu passaporte" required><button class="primary" type="submit">ENTRAR&nbsp; →</button></form><div class="first">PRIMEIRO ACESSO? SUA SENHA SERÁ CRIADA NO CADASTRO.</div><div class="secure">PCPT • POLÍCIA CAPITAL / POLÍCIA FEDERAL</div></main>'''
    return page("PCPT • Acesso", body, AUTH_CSS)


def password_page(qra: str, passport: str, next_url: str, error: str = "") -> str:
    err = f'<div class="err">{esc(error)}</div>' if error else ""
    body = f'''<main class="auth">{img(PF_LOGO, "logo", "Polícia Federal")}<div class="pcpt">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL</div><h1>CRIAR SENHA DE ACESSO</h1><p class="sub">Primeiro cadastro identificado. Defina uma senha para este operador.</p>{err}<form class="form" method="post" action="/criar-senha"><input type="hidden" name="qra" value="{esc(qra)}"><input type="hidden" name="passaporte" value="{esc(passport)}"><input type="hidden" name="next" value="{esc(next_url)}"><label>NOVA SENHA</label><input type="password" name="senha" minlength="4" maxlength="64" placeholder="Digite uma senha" required><label>CONFIRMAR SENHA</label><input type="password" name="confirmar" minlength="4" maxlength="64" placeholder="Confirme sua senha" required><button class="primary gold" type="submit">CRIAR ACESSO&nbsp; →</button></form><div class="secure">A senha fica vinculada ao QRA + passaporte deste cadastro.</div></main>'''
    return page("PCPT • Criar senha", body, AUTH_CSS)


async def get_channel(client: Any, cid: int):
    try:
        c = client.get_channel(cid)
        return c if c is not None else await client.fetch_channel(cid)
    except Exception:
        return None


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


def extract_name(text: str) -> str:
    patterns = [r"(?:nome|indivíduo|individuo|procurado)\s*[:=-]\s*([^|•\n]+)", r"^([A-ZÀ-Ú][A-Za-zÀ-ú' -]{3,60})\s*[|•]"]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return clean(m.group(1))[:70]
    return clean(text.split("|")[0].split("•")[0])[:70] or "Indivíduo não identificado"


def extract_field(text: str, labels: tuple[str, ...]) -> str:
    label = "|".join(re.escape(x) for x in labels)
    m = re.search(rf"(?:{label})\s*[:=-]\s*([^|•\n]+)", text, re.I)
    return clean(m.group(1))[:70] if m else "Não informado"


async def collect_procurados(client: Any) -> list[dict[str, Any]]:
    channels: list[Any] = []
    main = await get_channel(client, PROCURADOS_ID)
    if main:
        channels.append(main)
    guilds = getattr(client, "guilds", []) or []
    seen: set[int] = {getattr(main, "id", 0)} if main else set()
    for g in guilds:
        for c in getattr(g, "text_channels", []) or []:
            name = clean(getattr(c, "name", "")).casefold()
            if any(x in name for x in ("procurad", "foragid", "mandado")) and getattr(c, "id", 0) not in seen:
                channels.append(c)
                seen.add(getattr(c, "id", 0))
    out: list[dict[str, Any]] = []
    for c in channels[:8]:
        try:
            async for m in c.history(limit=80):
                text = text_of(m)
                if not text or closed(text):
                    continue
                out.append({
                    "number": number_from(text),
                    "name": extract_name(text),
                    "crime": extract_field(text, ("crime", "crimes", "acusação", "acusacao")),
                    "status": extract_field(text, ("status", "situação", "situacao")),
                    "created": getattr(m, "created_at", datetime.now(timezone.utc)),
                    "url": getattr(m, "jump_url", "#"),
                    "image": media_url(m),
                    "preview": text[:260],
                })
        except Exception:
            continue
    # Dedupe por mensagem/url para não duplicar quando canais relacionados forem varridos.
    unique: dict[str, dict[str, Any]] = {}
    for row in out:
        unique[row["url"] or f"{row['number']}|{row['name']}"] = row
    return sorted(unique.values(), key=lambda r: r["created"], reverse=True)[:100]


async def collect_threads(client: Any, cid: int, kind: str) -> list[dict[str, Any]]:
    c = await get_channel(client, cid)
    if c is None:
        return []
    threads = [t for t in (getattr(c, "threads", []) or []) if not getattr(t, "archived", False) and not getattr(t, "locked", False)]
    rows: list[dict[str, Any]] = []
    for t in threads[:120]:
        try:
            msgs = [m async for m in t.history(limit=5, oldest_first=True)]
            txt = " ".join(text_of(m) for m in msgs)
            if closed(txt + " " + clean(getattr(t, "name", ""))):
                continue
            created = getattr(t, "created_at", None) or datetime.now(timezone.utc)
            gid = getattr(getattr(t, "guild", None), "id", 0)
            rows.append({"number": number_from(getattr(t, "name", "")), "name": clean(getattr(t, "name", "")), "created": created, "url": f"https://discord.com/channels/{gid}/{t.id}", "kind": kind})
        except Exception:
            pass
    return sorted(rows, key=lambda r: r["created"], reverse=True)


async def refresh(client: Any) -> None:
    if CACHE["busy"]:
        return
    CACHE["busy"] = True
    try:
        pr, bo, pe = await asyncio.gather(collect_procurados(client), collect_threads(client, BO_ID, "bo"), collect_threads(client, PERICIA_ID, "pericia"), return_exceptions=True)
        CACHE["procurados"] = pr if isinstance(pr, list) else []
        CACHE["bo"] = bo if isinstance(bo, list) else []
        CACHE["pericia"] = pe if isinstance(pe, list) else []
        CACHE["updated"] = time.time()
    finally:
        CACHE["busy"] = False


async def refresh_loop(client: Any) -> None:
    while True:
        try:
            await refresh(client)
        except Exception:
            pass
        await asyncio.sleep(20)


APP_CSS = """
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;background:#05080d;color:#e9eef4}a{text-decoration:none;color:inherit}.app{min-height:100vh;display:grid;grid-template-columns:235px 1fr}.side{position:sticky;top:0;height:100vh;padding:18px 14px;border-right:1px solid #1b2a39;background:linear-gradient(180deg,#08111b,#050a10)}.brand{display:flex;align-items:center;gap:10px;padding:4px 6px 20px;border-bottom:1px solid #1b2b3a}.brand img{width:52px;height:52px;object-fit:contain}.brand b{font-size:14px;letter-spacing:2px}.brand small{display:block;color:#c99b32;font-size:8px;letter-spacing:2px;margin-top:3px}.side-note{margin-top:auto;padding:13px;border:1px solid #1b2a39;border-radius:12px;color:#65788c;font-size:9px;line-height:1.7}.main{min-width:0;padding:20px 26px 45px}.top{display:flex;align-items:center;justify-content:space-between;gap:15px;padding-bottom:15px;border-bottom:1px solid #182737}.pcpt-title{font-size:12px;font-weight:900;letter-spacing:1.7px}.pcpt-title span{display:block;color:#60778f;font-size:9px;letter-spacing:1.1px;margin-top:5px}.operator{display:flex;align-items:center;gap:8px;color:#7f93a8;font-size:9px}.online{width:7px;height:7px;border-radius:50%;background:#35d38b;box-shadow:0 0 12px #35d38b}.hero{position:relative;overflow:hidden;margin-top:18px;padding:26px;border:1px solid #244666;border-radius:17px;background:linear-gradient(115deg,#0a1827,#091321 56%,#07101a);box-shadow:inset 0 0 60px #0a3b651c}.hero:after{content:'';position:absolute;right:-100px;top:-130px;width:390px;height:390px;border-radius:50%;border:1px solid #1b73bd33;box-shadow:0 0 0 35px #1b73bd08,0 0 0 70px #1b73bd04}.eyebrow{color:#5ea5e8;font-size:9px;letter-spacing:2.3px;font-weight:900}.hero h1{margin:8px 0 7px;font-size:36px;letter-spacing:1px}.hero p{margin:0;color:#71869b;font-size:11px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px}.stat{padding:14px;border:1px solid #1d344b;border-radius:12px;background:#08111b}.stat span{font-size:8px;color:#668099;letter-spacing:1.2px}.stat b{display:block;margin-top:7px;font-size:27px;color:#dce8f3}.stat.blue b{color:#57a8ef}.stat.red b{color:#ff6570}.stat.gold b{color:#d9af50}.wanted{margin-top:15px;border:1px solid #1c344b;border-radius:15px;background:#070e16;overflow:hidden}.wanted-head{display:flex;align-items:center;justify-content:space-between;padding:15px 16px;border-bottom:1px solid #172a3c}.wanted-head b{font-size:11px;letter-spacing:1.3px}.wanted-head span{color:#5d7891;font-size:9px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;padding:12px}.card{min-width:0;border:1px solid #1a3044;border-radius:12px;background:linear-gradient(155deg,#0c1825,#07101a);overflow:hidden}.photo{height:145px;background:linear-gradient(145deg,#172636,#0a1119);display:grid;place-items:center;overflow:hidden}.photo img{width:100%;height:100%;object-fit:cover;filter:saturate(.75) contrast(1.05)}.placeholder{font-size:31px;color:#34516d}.card-body{padding:11px}.tag{display:inline-block;padding:4px 7px;border-radius:5px;background:#174e80;color:#b9ddff;font-size:7px;font-weight:900;letter-spacing:1px}.card h3{font-size:11px;margin:8px 0 5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{font-size:8px;color:#71869a;line-height:1.7;min-height:39px}.details{display:block;margin-top:9px;padding:9px;border:1px solid #23445f;border-radius:8px;text-align:center;color:#82b8e9;font-size:8px;font-weight:800}.access{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-top:14px;padding:17px 19px;border:1px solid #8c671d;border-radius:13px;background:linear-gradient(110deg,#15130d,#0d1115)}.access strong{display:block;color:#f0cf70;font-size:12px}.access span{display:block;color:#786f59;font-size:8px;margin-top:5px}.access-btn{padding:13px 18px;border-radius:9px;background:linear-gradient(135deg,#f0cf70,#9b6b15);color:#090b0d;font-size:10px;font-weight:900;white-space:nowrap}.foot{text-align:center;margin-top:20px;color:#44586b;font-size:8px}.empty{padding:40px;text-align:center;color:#5f7285;font-size:10px}.module-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:18px}.module{padding:20px;border:1px solid #72541b;border-radius:13px;background:#0a0e13}.module h3{margin:0 0 8px;color:#e6c766;font-size:13px}.module p{margin:0;color:#718297;font-size:10px;line-height:1.6}.module a{display:block;margin-top:14px;padding:11px;text-align:center;border-radius:8px;background:#111923;color:#e4c76a;font-size:9px}.back{display:inline-block;color:#7caee0;font-size:10px;margin-top:15px}@media(max-width:1100px){.grid{grid-template-columns:repeat(3,1fr)}.stats{grid-template-columns:repeat(2,1fr)}}@media(max-width:800px){.app{display:block}.side{position:relative;height:auto;padding:12px 14px}.brand{border:0;padding-bottom:8px}.side-note{display:none}.main{padding:13px 12px 30px}.grid{grid-template-columns:repeat(2,1fr);padding:9px}.photo{height:150px}.hero{padding:21px}.hero h1{font-size:30px}.access{align-items:stretch;flex-direction:column}.access-btn{text-align:center}.module-grid{grid-template-columns:1fr 1fr}}@media(max-width:480px){.top{align-items:flex-start}.operator{font-size:0}.hero h1{font-size:27px}.stats{gap:7px}.stat{padding:11px}.stat b{font-size:23px}.grid{gap:7px}.card h3{font-size:10px}.photo{height:125px}.module-grid{grid-template-columns:1fr}}
"""


def card(row: dict[str, Any]) -> str:
    image = f'<img src="{esc(row.get("image"))}" alt="" loading="lazy">' if row.get("image") else '<div class="placeholder">◉</div>'
    dt = row.get("created")
    try:
        date = dt.astimezone().strftime("%d/%m/%Y • %H:%M")
    except Exception:
        date = "--"
    return f'''<article class="card"><div class="photo">{image}</div><div class="card-body"><span class="tag">PROCURADO</span><h3>{esc(row.get("name"))}</h3><div class="meta">Nº {esc(row.get("number"))}<br>Crime: {esc(row.get("crime"))}<br>Atualizado: {esc(date)}</div><a class="details" href="{esc(row.get("url") or '#')}" target="_blank">VER REGISTRO&nbsp; →</a></div></article>'''


def dashboard(rows: list[dict[str, Any]], qra: str, passport: str) -> str:
    total = len(rows)
    cards = "".join(card(r) for r in rows[:12]) or '<div class="empty">Nenhum procurado ativo encontrado no Discord.</div>'
    updated = datetime.now().strftime("%d/%m/%Y • %H:%M")
    body = f'''<div class="app"><aside class="side"><div class="brand">{img(DICOR_LOGO, "", "DICOR") }<div><b>DICOR</b><small>INTELIGÊNCIA</small></div></div><div class="side-note">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<br><br>CONSULTA INTERNA<br>SISTEMA SOMENTE LEITURA</div></aside><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class="operator"><i class="online"></i> {esc(qra)} • {esc(passport)}</div></header><section class="hero"><div class="eyebrow">CENTRAL DICOR • MONITORAMENTO</div><h1>PROCURADOS</h1><p>Os indivíduos em situação de procura no sistema operacional.</p></section><section class="stats"><div class="stat blue"><span>TOTAL LOCALIZADOS</span><b>{total}</b></div><div class="stat red"><span>ATIVOS</span><b>{total}</b></div><div class="stat gold"><span>MONITORADOS</span><b>0</b></div><div class="stat"><span>CAPTURADOS</span><b>0</b></div></section><section class="wanted"><div class="wanted-head"><b>PROCURADOS EM DESTAQUE</b><span>DISCORD • ATUALIZAÇÃO {esc(updated)}</span></div><div class="grid">{cards}</div></section><a class="access" href="/funcionalidades"><div><strong>ACESSAR TODAS AS FUNCIONALIDADES</strong><span>BOLETINS • PERÍCIAS • BANCO DE DADOS • ÁRVORE • OPERAÇÕES</span></div><div class="access-btn">ACESSAR&nbsp; →</div></a><div class="foot">DICOR • INTELIGÊNCIA E OPERAÇÕES ESPECIAIS</div></main></div>'''
    return page("DICOR • Procurados", body, APP_CSS)


def functionalities(qra: str) -> str:
    modules = [("BOLETINS", "Consulta dos boletins ativos e registros operacionais.", "/boletins"), ("PERÍCIAS", "Acompanhamento das perícias externas pendentes.", "/pericias"), ("BANCO DE DADOS", "Acesso aos módulos de consulta disponíveis.", "/fichas"), ("ÁRVORE DE INTELIGÊNCIA", "Estrutura de informações e vínculos.", "/arvore"), ("OPERAÇÕES", "Área de consulta das operações em andamento.", "/boletins"), ("CENTRAL", "Retornar ao painel principal de Procurados.", "/")]
    cards = "".join(f'<article class="module"><h3>{esc(a)}</h3><p>{esc(b)}</p><a href="{esc(c)}">ABRIR MÓDULO&nbsp; →</a></article>' for a,b,c in modules)
    body = f'''<div class="app"><aside class="side"><div class="brand">{img(DICOR_LOGO, "", "DICOR")}<div><b>DICOR</b><small>INTELIGÊNCIA</small></div></div></aside><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • TODAS AS FUNCIONALIDADES</span></div><div class="operator"><i class="online"></i> {esc(qra)}</div></header><div class="hero"><div class="eyebrow">DICOR • ACESSO OPERACIONAL</div><h1>FUNCIONALIDADES</h1><p>Selecione uma área para consulta.</p></div><div class="module-grid">{cards}</div><a class="back" href="/">← Voltar aos Procurados</a></main></div>'''
    return page("DICOR • Funcionalidades", body, APP_CSS)


def listing(title: str, subtitle: str, rows: list[dict[str, Any]], qra: str, kind: str) -> str:
    if kind == "procurados":
        content = "".join(card(r) for r in rows) or '<div class="empty">Nenhum registro ativo.</div>'
        inner = f'<section class="wanted"><div class="wanted-head"><b>{esc(title)}</b><span>{esc(subtitle)}</span></div><div class="grid">{content}</div></section>'
    else:
        content = "".join(f'<div class="item"><b>Nº {esc(r.get("number"))}</b><span>{esc(r.get("name"))}</span><a href="{esc(r.get("url") or "#")}" target="_blank">DISCORD →</a></div>' for r in rows) or '<div class="empty">Nenhum registro ativo.</div>'
        inner = f'<section class="wanted"><div class="wanted-head"><b>{esc(title)}</b><span>{esc(subtitle)}</span></div>{content}</section>'
    body = f'''<div class="app"><aside class="side"><div class="brand">{img(DICOR_LOGO, "", "DICOR")}<div><b>DICOR</b><small>INTELIGÊNCIA</small></div></div></aside><main class="main"><header class="top"><div class="pcpt-title">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CONSULTA INTERNA</span></div><div class="operator"><i class="online"></i> {esc(qra)}</div></header><div class="hero"><div class="eyebrow">CENTRAL DICOR</div><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div>{inner}<a class="back" href="/funcionalidades">← Todas as funcionalidades</a></main></div>'''
    return page("DICOR • " + title, body, APP_CSS)


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

    async def auth_required(req: web.Request) -> tuple[str, str] | web.StreamResponse:
        session = read_session(req)
        if session:
            return session
        target = req.path
        if req.query_string:
            target += "?" + req.query_string
        raise web.HTTPFound("/cadastro-operador?next=" + web.URLEncode(target))

    async def health(req: web.Request):
        return web.json_response({"ok": True, "service": "DICOR Central V613", "cache_age": round(time.time() - CACHE["updated"], 2) if CACHE["updated"] else None})

    async def get_login(req: web.Request):
        return web.Response(text=login_page(next_url=req.query.get("next", "/")), content_type="text/html")

    async def post_login(req: web.Request):
        data = await req.post()
        qra = clean(data.get("qra"))
        passport = clean(data.get("passaporte"))
        next_url = clean(data.get("next")) or "/"
        if not qra or not passport:
            return web.Response(text=login_page("Preencha QRA e passaporte.", next_url), content_type="text/html")
        accounts = load_accounts()
        key = account_key(qra, passport)
        stored = accounts.get(key)
        if not stored:
            return web.Response(text=password_page(qra, passport, next_url), content_type="text/html")
        # Se já existe, a segunda etapa é autenticação por senha.
        body = f'''<main class="auth">{img(PF_LOGO, "logo", "Polícia Federal")}<div class="pcpt">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL</div><h1>CONFIRMAR ACESSO</h1><p class="sub">Operador cadastrado. Digite sua senha para continuar.</p><form class="form" method="post" action="/entrar"><input type="hidden" name="qra" value="{esc(qra)}"><input type="hidden" name="passaporte" value="{esc(passport)}"><input type="hidden" name="next" value="{esc(next_url)}"><label>SENHA</label><input type="password" name="senha" autocomplete="current-password" placeholder="Digite sua senha" required><button class="primary gold">ENTRAR&nbsp; →</button></form></main>'''
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
            body = f'''<main class="auth">{img(PF_LOGO, "logo", "Polícia Federal")}<div class="pcpt">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL</div><h1>ACESSO NEGADO</h1><p class="sub">QRA, passaporte ou senha incorretos.</p><a class="primary gold" style="display:block;text-decoration:none;padding-top:16px" href="/cadastro-operador">VOLTAR AO ACESSO</a></main>'''
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

    async def boletins(req: web.Request):
        qra, _ = await auth_required(req)
        return web.Response(text=listing("BOLETINS", "Boletins ativos consultados diretamente do Discord.", CACHE["bo"], qra, "bo"), content_type="text/html")

    async def pericias(req: web.Request):
        qra, _ = await auth_required(req)
        return web.Response(text=listing("PERÍCIAS", "Perícias externas ativas consultadas diretamente do Discord.", CACHE["pericia"], qra, "pe"), content_type="text/html")

    async def fichas(req: web.Request):
        qra, _ = await auth_required(req)
        return web.Response(text=listing("BANCO DE DADOS", "Módulo de consulta integrado à Central.", [], qra, "db"), content_type="text/html")

    async def arvore(req: web.Request):
        qra, _ = await auth_required(req)
        return web.Response(text=listing("ÁRVORE DE INTELIGÊNCIA", "Estrutura de vínculos e informações.", [], qra, "tree"), content_type="text/html")

    app.router.add_get("/health", health)
    app.router.add_get("/cadastro-operador", get_login)
    app.router.add_post("/cadastro-operador", post_login)
    app.router.add_post("/criar-senha", create_password)
    app.router.add_post("/entrar", enter)
    app.router.add_get("/", dashboard_route)
    app.router.add_get("/funcionalidades", funcs)
    app.router.add_get("/boletins", boletins)
    app.router.add_get("/pericias", pericias)
    app.router.add_get("/fichas", fichas)
    app.router.add_get("/arvore", arvore)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    return runner


class CentralV613:
    def __init__(self, client: Any):
        self.client = client
        self.runner: web.AppRunner | None = None
        self.task: asyncio.Task | None = None

    async def start(self):
        if self.runner is not None:
            return
        self.runner = await start_server(self.client)
        self.task = asyncio.create_task(refresh_loop(self.client))


def install(bot_module: Any) -> CentralV613:
    client = getattr(bot_module, "bot", None)
    if client is None:
        raise RuntimeError("cliente Discord ausente")
    return CentralV613(client)
