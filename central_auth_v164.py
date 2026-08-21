# -*- coding: utf-8 -*-
"""V164 — autenticação persistente da Central DICOR.

- Boletins/Perícias: primeiro acesso cria QRA + senha, pede aprovação uma vez e
  passa a usar login nas próximas sessões.
- Banco/Árvore: continuam usando somente a senha estratégica, sem criar conta.
- Aprovações novas são enviadas exclusivamente ao canal de teste informado.

Esta camada é instalada depois da V163 e só substitui autenticação/portal.
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
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

APPROVAL_CHANNEL_ID = 1529596208857878608
ACCOUNT_PATHS = ("/boletins", "/pericias")
STRATEGIC_PATHS = ("/fichas", "/arvore")
PUBLIC_PREFIXES = (
    "/central/", "/uploads/", "/public/", "/catalogo-media/", "/favicon",
    "/health", "/healthz",
)
ACCOUNT_COOKIE = "dicor_user_v164"
SIGNUP_COOKIE = "dicor_signup_v164"
STRATEGIC_COOKIE = "dicor_strategic_v164"
ACCOUNT_SESSION_SECONDS = 12 * 3600
STRATEGIC_SESSION_SECONDS = 20 * 60
REQUEST_SECONDS = 24 * 3600
PBKDF2_ROUNDS = 240_000


def install(bot_module) -> None:
    web = bot_module.web
    discord = bot_module.discord
    client = bot_module.bot

    data_dir = Path(str(getattr(bot_module, "DATA_DIR", Path(__file__).parent / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    accounts_file = data_dir / "central_accounts_v164.json"
    lock = asyncio.Lock()
    restored = {"done": False}

    def now() -> int:
        return int(time.time())

    def esc(value: Any) -> str:
        return html.escape(str(value or ""))

    def norm_qra(value: Any) -> str:
        text = str(value or "").strip().casefold()
        text = re.sub(r"\s+", " ", text)
        return text[:100]

    def load_accounts() -> List[Dict[str, Any]]:
        try:
            if accounts_file.exists():
                raw = json.loads(accounts_file.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    return [dict(x) for x in raw if isinstance(x, dict)]
        except Exception as exc:
            print(f"⚠️ V164 contas: leitura falhou: {type(exc).__name__}: {exc}", flush=True)
        return []

    def save_accounts(rows: List[Dict[str, Any]]) -> None:
        tmp = accounts_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows[-1000:], ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, accounts_file)

    def password_hash(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        raw_salt = base64.urlsafe_b64decode(salt.encode("ascii")) if salt else secrets.token_bytes(18)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw_salt, PBKDF2_ROUNDS)
        return base64.urlsafe_b64encode(raw_salt).decode("ascii"), base64.urlsafe_b64encode(digest).decode("ascii")

    def verify_password(password: str, salt: str, expected: str) -> bool:
        try:
            _, actual = password_hash(password, salt)
            return hmac.compare_digest(actual, str(expected or ""))
        except Exception:
            return False

    def cookie_secret() -> bytes:
        value = (
            os.getenv("CENTRAL_DICOR_COOKIE_SECRET", "").strip()
            or os.getenv("PLATAFORMA_DONO_PASSWORD", "").strip()
            or os.getenv("CENTRAL_DICOR_PASSWORD", "").strip()
            or "dicor-v164-session-fallback"
        )
        return value.encode("utf-8")

    def sign_token(kind: str, subject: str, ttl: int) -> str:
        exp = now() + ttl
        payload = f"{kind}|{subject}|{exp}"
        body = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
        sig = hmac.new(cookie_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{body}.{sig}"

    def verify_token(token: str, kind: str) -> Optional[str]:
        try:
            body, sig = str(token or "").rsplit(".", 1)
            expected = hmac.new(cookie_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                return None
            padded = body + "=" * (-len(body) % 4)
            raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
            token_kind, subject, exp_text = raw.split("|", 2)
            if token_kind != kind or int(exp_text) < now():
                return None
            return subject
        except Exception:
            return None

    async def find_account(qra: str) -> Optional[Dict[str, Any]]:
        key = norm_qra(qra)
        async with lock:
            rows = load_accounts()
        for row in reversed(rows):
            if str(row.get("qra_norm") or "") == key:
                return row
        return None

    async def find_request(request_id: str) -> Optional[Dict[str, Any]]:
        async with lock:
            rows = load_accounts()
        for row in reversed(rows):
            if str(row.get("request_id") or "") == str(request_id or ""):
                return row
        return None

    async def update_account(request_id: str, **changes: Any) -> Optional[Dict[str, Any]]:
        async with lock:
            rows = load_accounts()
            found = None
            for row in rows:
                if str(row.get("request_id") or "") == str(request_id or ""):
                    row.update(changes)
                    found = dict(row)
                    break
            if found is not None:
                save_accounts(rows)
            return found

    def approver_id() -> int:
        for value in (
            os.getenv("CENTRAL_APROVADOR_USER_ID", "").strip(),
            getattr(bot_module, "INSPETOR_BAIANO_USER_ID", 0),
        ):
            try:
                parsed = int(value or 0)
                if parsed:
                    return parsed
            except Exception:
                pass
        return 0

    def is_approver(member) -> bool:
        aid = approver_id()
        return bool(aid and int(getattr(member, "id", 0) or 0) == aid)

    async def resolve_channel(channel_id: int):
        channel = client.get_channel(int(channel_id))
        if channel is not None:
            return channel
        try:
            return await client.fetch_channel(int(channel_id))
        except Exception:
            return None

    class AccountApprovalView(discord.ui.View):
        def __init__(self, request_id: str):
            super().__init__(timeout=None)
            self.request_id = str(request_id)
            approve = discord.ui.Button(
                label="Aprovar cadastro", emoji="✅", style=discord.ButtonStyle.success,
                custom_id=f"dicor_v164_account_approve:{self.request_id}",
            )
            deny = discord.ui.Button(
                label="Negar cadastro", emoji="⛔", style=discord.ButtonStyle.danger,
                custom_id=f"dicor_v164_account_deny:{self.request_id}",
            )

            async def decide(interaction, status: str) -> None:
                if not is_approver(interaction.user):
                    return await interaction.response.send_message(
                        "❌ Somente o responsável configurado pode decidir este cadastro.", ephemeral=True
                    )
                row = await find_request(self.request_id)
                if not row:
                    return await interaction.response.send_message("❌ Cadastro não encontrado.", ephemeral=True)
                if row.get("status") != "pending":
                    return await interaction.response.send_message("ℹ️ Este cadastro já foi decidido.", ephemeral=True)
                updated = await update_account(
                    self.request_id,
                    status=status,
                    decided_at=now(),
                    decided_by_id=int(interaction.user.id),
                    decided_by=str(interaction.user),
                )
                if not updated:
                    return await interaction.response.send_message("❌ Não foi possível salvar a decisão.", ephemeral=True)
                embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else discord.Embed(title="Central DICOR")
                if status == "approved":
                    embed.color = discord.Color.green()
                    value = f"✅ CADASTRO APROVADO por {interaction.user.mention}\nO usuário poderá entrar com QRA + senha."
                else:
                    embed.color = discord.Color.red()
                    value = f"⛔ CADASTRO NEGADO por {interaction.user.mention}"
                embed.add_field(name="DECISÃO", value=value, inline=False)
                await interaction.response.edit_message(embed=embed, view=None)

            async def approve_cb(interaction):
                await decide(interaction, "approved")

            async def deny_cb(interaction):
                await decide(interaction, "denied")

            approve.callback = approve_cb
            deny.callback = deny_cb
            self.add_item(approve)
            self.add_item(deny)

    async def send_approval(row: Dict[str, Any]) -> bool:
        channel = await resolve_channel(APPROVAL_CHANNEL_ID)
        if channel is None or not hasattr(channel, "send"):
            print(f"⚠️ V164: canal de aprovação {APPROVAL_CHANNEL_ID} indisponível.", flush=True)
            return False
        embed = discord.Embed(
            title="🔐 Cadastro de acesso — Central DICOR",
            description="Primeiro acesso solicitado. A aprovação libera **Boletins e Perícias** para este usuário.",
            color=discord.Color.from_rgb(201, 162, 39),
        )
        embed.add_field(name="QRA / NOME", value=str(row.get("qra") or "Não informado")[:1024], inline=True)
        embed.add_field(name="PASSAPORTE", value=str(row.get("passaporte") or "Não informado")[:1024], inline=True)
        embed.add_field(name="MOTIVO", value=str(row.get("motivo") or "Não informado")[:1024], inline=False)
        embed.add_field(name="SEGURANÇA", value="A senha não é enviada ao Discord e não é salva em texto puro.", inline=False)
        embed.set_footer(text=f"Central DICOR • Cadastro {row['request_id']} • Canal exclusivo {APPROVAL_CHANNEL_ID}")
        try:
            message = await channel.send(embed=embed, view=AccountApprovalView(str(row["request_id"])))
        except Exception as exc:
            print(f"⚠️ V164: falha ao enviar cadastro: {type(exc).__name__}: {exc}", flush=True)
            return False
        await update_account(
            str(row["request_id"]),
            discord_message_id=int(message.id),
            approval_channel_id=int(channel.id),
        )
        return True

    def strategic_password() -> str:
        return (
            os.getenv("CENTRAL_ESTRATEGICA_PASSWORD", "").strip()
            or os.getenv("PLATAFORMA_DONO_PASSWORD", "").strip()
            or os.getenv("CENTRAL_DICOR_PASSWORD", "").strip()
        )

    def target_mode(path: str) -> Tuple[str, str]:
        clean = str(path or "/").split("?", 1)[0].lower()
        if clean.startswith("/boletins"):
            return "account", "boletins"
        if clean.startswith("/pericias"):
            return "account", "pericias"
        if clean.startswith("/fichas"):
            return "strategic", "fichas"
        if clean.startswith("/arvore"):
            return "strategic", "arvore"
        return "public", ""

    async def valid_account_cookie(request) -> Optional[Dict[str, Any]]:
        qra_norm = verify_token(request.cookies.get(ACCOUNT_COOKIE, ""), "account")
        if not qra_norm:
            return None
        row = await find_account(qra_norm)
        if not row or row.get("status") != "approved":
            return None
        return row

    def shell(body: str, title: str = "Acesso • Central DICOR") -> str:
        css = """
:root{--g:#c9a227;--g2:#f0d878;--bg:#050505;--p:#0b0b08;--l:#443718;--t:#f5f0df;--m:#aaa38e;--bad:#8f302b}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 50% -12%,#82671925,transparent 34%),linear-gradient(#080806,#030303);color:var(--t);font-family:Inter,Segoe UI,Arial}.top{height:92px;border-bottom:1px solid var(--l);display:flex;align-items:center;justify-content:center;background:#050504ed}.brand{display:flex;align-items:center;gap:15px}.brand img{width:62px;height:62px;object-fit:contain}.brand b{font-family:Georgia,serif;letter-spacing:1.6px;font-size:19px}.brand small{display:block;color:var(--g);font-size:9px;letter-spacing:1.5px;margin-top:4px}.wrap{max-width:980px;margin:auto;padding:44px 20px 70px}.back{color:#bfb697;text-decoration:none;font-size:13px}.access-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:25px}.card{border:1px solid #40351b;background:linear-gradient(150deg,#11100b,#080806);border-radius:18px;padding:28px;box-shadow:0 18px 55px #0008}.card h2{font-family:Georgia,serif;font-size:28px;margin:9px 0}.ey{color:var(--g);font-size:9px;letter-spacing:2px}.card p{color:var(--m);line-height:1.55}.field{margin-top:13px}.field label{display:block;color:#d7c36f;font-size:10px;letter-spacing:1px;margin-bottom:6px}.field input,.field textarea{width:100%;padding:13px;border-radius:9px;border:1px solid #4c3e1c;background:#050504;color:white;outline:none}.field textarea{min-height:85px;resize:vertical}.btn{width:100%;margin-top:17px;padding:13px;border:1px solid #e0c55a;border-radius:9px;background:linear-gradient(135deg,var(--g2),var(--g));color:#151207;font-weight:900;cursor:pointer}.notice{border:1px solid #664f23;background:#201a0c;color:#ebd481;padding:12px;border-radius:9px;margin:12px 0;line-height:1.45}.danger{border-color:#713632;background:#2d1412;color:#ffc8c2}.ok{border-color:#315b39;background:#0e2313;color:#bfe8c4}.seal{text-align:center;margin-bottom:12px}.seal img{width:92px}.center{text-align:center}.single{max-width:520px;margin:28px auto}.hint{font-size:12px;color:#8f8873;margin-top:10px}.split{height:1px;background:#342b16;margin:20px 0}@media(max-width:780px){.access-grid{grid-template-columns:1fr}.top{height:auto;padding:14px}.wrap{padding-top:28px}}
"""
        return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{css}</style></head><body><header class="top"><div class="brand"><img src="/central/brasao-dicor.png"><div><b>POLÍCIA FEDERAL — DICOR</b><small>CONTROLE DE ACESSO</small></div></div></header>{body}</body></html>'''

    original_portal = getattr(bot_module, "central_portal_http", None)

    async def portal(request):
        if callable(original_portal):
            response = await original_portal(request)
            try:
                text = str(response.text or "")
                text = text.replace("AUTORIZAÇÃO", "QRA + SENHA")
                text = text.replace("Solicitar acesso", "Entrar / cadastrar")
                response.text = text
            except Exception:
                pass
            return response
        return web.Response(text="Central DICOR", content_type="text/plain")

    async def login_get(request):
        next_path = str(request.query.get("next") or "/")
        mode, module = target_mode(next_path)
        if mode == "public":
            raise web.HTTPFound(next_path)

        if mode == "strategic":
            if verify_token(request.cookies.get(STRATEGIC_COOKIE, ""), "strategic"):
                raise web.HTTPFound(next_path)
            err = esc(request.query.get("erro") or "")
            alert = f'<div class="notice danger">{err}</div>' if err else ""
            body = f'''<main class="wrap"><a class="back" href="/">← Voltar à Central</a><section class="card single"><div class="seal"><img src="/central/brasao-dicor.png"></div><div class="ey center">COFRE ESTRATÉGICO</div><h2 class="center">Senha reservada</h2><p class="center">Banco de Dados e Árvore não criam usuário. A senha estratégica não é gravada; apenas uma sessão curta é liberada para navegação.</p>{alert}<form method="post" action="/acesso"><input type="hidden" name="mode" value="strategic_v164"><input type="hidden" name="next" value="{esc(next_path)}"><div class="field"><label>SENHA ESTRATÉGICA</label><input name="senha" type="password" autocomplete="off" required autofocus></div><button class="btn" type="submit">ENTRAR</button></form><div class="hint center">A sessão expira automaticamente e a senha não é armazenada.</div></section></main>'''
            return web.Response(text=shell(body, "Senha estratégica • DICOR"), content_type="text/html", charset="utf-8")

        if await valid_account_cookie(request):
            raise web.HTTPFound(next_path)

        request_id = str(request.query.get("request") or "")
        if request_id:
            row = await find_request(request_id)
            signup_token = request.cookies.get(SIGNUP_COOKIE, "")
            token_subject = verify_token(signup_token, "signup")
            if row and token_subject == request_id:
                status = str(row.get("status") or "pending")
                if status == "approved":
                    response = web.HTTPFound(next_path)
                    response.set_cookie(ACCOUNT_COOKIE, sign_token("account", str(row.get("qra_norm") or ""), ACCOUNT_SESSION_SECONDS), httponly=True, secure=True, samesite="Lax", path="/")
                    response.del_cookie(SIGNUP_COOKIE, path="/")
                    raise response
                if status == "denied":
                    body = '''<main class="wrap"><section class="card single center"><div class="seal"><img src="/central/brasao-dicor.png"></div><div class="notice danger">⛔ Seu cadastro foi negado.</div><a class="back" href="/">Voltar à Central</a></section></main>'''
                    return web.Response(text=shell(body, "Cadastro negado • DICOR"), content_type="text/html", charset="utf-8")
                if status == "error":
                    body = '''<main class="wrap"><section class="card single center"><div class="notice danger">Não foi possível enviar o cadastro para aprovação.</div><a class="back" href="/">Voltar</a></section></main>'''
                    return web.Response(text=shell(body, "Falha • DICOR"), content_type="text/html", charset="utf-8")
                body = f'''<main class="wrap"><section class="card single center"><div class="seal"><img src="/central/brasao-dicor.png"></div><div class="ey">CADASTRO ENVIADO</div><h2>Aguardando sua aprovação</h2><p>O cadastro de <b>{esc(row.get('qra'))}</b> foi enviado exclusivamente para o canal de teste configurado.</p><div class="notice">Quando você aprovar no Discord, esta página entra automaticamente.</div><div class="hint">Canal: {APPROVAL_CHANNEL_ID}</div><script>setTimeout(()=>location.reload(),3000)</script></section></main>'''
                return web.Response(text=shell(body, "Aguardando aprovação • DICOR"), content_type="text/html", charset="utf-8")

        err = esc(request.query.get("erro") or "")
        alert = f'<div class="notice danger">{err}</div>' if err else ""
        body = f'''<main class="wrap"><a class="back" href="/">← Voltar à Central</a>{alert}<section class="access-grid"><article class="card"><div class="ey">JÁ AUTORIZADO</div><h2>Entrar</h2><p>Se seu cadastro já foi aprovado, use apenas seu QRA e a senha que você criou.</p><form method="post" action="/acesso"><input type="hidden" name="mode" value="account_login_v164"><input type="hidden" name="next" value="{esc(next_path)}"><div class="field"><label>QRA / NOME</label><input name="qra" maxlength="100" autocomplete="username" required></div><div class="field"><label>SENHA</label><input name="senha" type="password" autocomplete="current-password" required></div><button class="btn" type="submit">ENTRAR</button></form></article><article class="card"><div class="ey">PRIMEIRO ACESSO</div><h2>Criar acesso</h2><p>Crie sua senha uma única vez. Depois da aprovação, Boletins e Perícias ficam disponíveis nas próximas sessões usando QRA + senha.</p><form method="post" action="/acesso"><input type="hidden" name="mode" value="account_register_v164"><input type="hidden" name="next" value="{esc(next_path)}"><div class="field"><label>QRA / NOME</label><input name="qra" maxlength="100" autocomplete="username" required></div><div class="field"><label>PASSAPORTE / RG FUNCIONAL</label><input name="passaporte" maxlength="50" required></div><div class="field"><label>CRIAR SENHA</label><input name="senha" type="password" minlength="6" autocomplete="new-password" required></div><div class="field"><label>CONFIRMAR SENHA</label><input name="confirmar" type="password" minlength="6" autocomplete="new-password" required></div><div class="field"><label>MOTIVO DO ACESSO</label><textarea name="motivo" maxlength="500" required></textarea></div><button class="btn" type="submit">CRIAR E ENVIAR PARA APROVAÇÃO</button></form><div class="hint">Sua senha é armazenada somente como hash criptográfico; o bot não consegue ler a senha original.</div></article></section></main>'''
        return web.Response(text=shell(body, "Entrar • Central DICOR"), content_type="text/html", charset="utf-8")

    async def login_post(request):
        data = await request.post()
        mode = str(data.get("mode") or "")
        next_path = str(data.get("next") or "/")
        target, _module = target_mode(next_path)

        if mode == "strategic_v164" and target == "strategic":
            supplied = str(data.get("senha") or "")
            expected = strategic_password()
            if not expected or not hmac.compare_digest(supplied, expected):
                raise web.HTTPFound(f"/acesso?next={quote(next_path, safe='/')}&erro={quote('Senha estratégica inválida.')}")
            response = web.HTTPFound(next_path)
            response.set_cookie(STRATEGIC_COOKIE, sign_token("strategic", "ok", STRATEGIC_SESSION_SECONDS), httponly=True, secure=True, samesite="Lax", path="/")
            response.del_cookie("dicor_strategic", path="/")
            raise response

        if mode == "account_login_v164" and target == "account":
            qra = str(data.get("qra") or "").strip()
            password = str(data.get("senha") or "")
            row = await find_account(qra)
            if not row:
                raise web.HTTPFound(f"/acesso?next={quote(next_path, safe='/')}&erro={quote('QRA não cadastrado. Use Primeiro acesso.')}")
            status = str(row.get("status") or "pending")
            if status == "pending":
                raise web.HTTPFound(f"/acesso?next={quote(next_path, safe='/')}&erro={quote('Seu cadastro ainda aguarda aprovação.')}")
            if status != "approved":
                raise web.HTTPFound(f"/acesso?next={quote(next_path, safe='/')}&erro={quote('Cadastro não autorizado.')}")
            if not verify_password(password, str(row.get("password_salt") or ""), str(row.get("password_hash") or "")):
                raise web.HTTPFound(f"/acesso?next={quote(next_path, safe='/')}&erro={quote('QRA ou senha incorretos.')}")
            await update_account(str(row.get("request_id") or ""), last_login_at=now())
            response = web.HTTPFound(next_path)
            response.set_cookie(ACCOUNT_COOKIE, sign_token("account", str(row.get("qra_norm") or ""), ACCOUNT_SESSION_SECONDS), httponly=True, secure=True, samesite="Lax", path="/")
            response.del_cookie("dicor_approval", path="/")
            raise response

        if mode == "account_register_v164" and target == "account":
            qra = str(data.get("qra") or "").strip()[:100]
            qra_key = norm_qra(qra)
            passaporte = str(data.get("passaporte") or "").strip()[:50]
            password = str(data.get("senha") or "")
            confirm = str(data.get("confirmar") or "")
            motivo = str(data.get("motivo") or "").strip()[:500]
            if len(qra_key) < 2 or not passaporte:
                raise web.HTTPFound(f"/acesso?next={quote(next_path, safe='/')}&erro={quote('Preencha QRA e passaporte.')}")
            if len(password) < 6:
                raise web.HTTPFound(f"/acesso?next={quote(next_path, safe='/')}&erro={quote('A senha precisa ter pelo menos 6 caracteres.')}")
            if password != confirm:
                raise web.HTTPFound(f"/acesso?next={quote(next_path, safe='/')}&erro={quote('As senhas não coincidem.')}")
            existing = await find_account(qra)
            if existing:
                status = str(existing.get("status") or "pending")
                if status == "approved":
                    raise web.HTTPFound(f"/acesso?next={quote(next_path, safe='/')}&erro={quote('Este QRA já possui acesso. Use a opção Entrar.')}")
                if status == "pending":
                    raise web.HTTPFound(f"/acesso?next={quote(next_path, safe='/')}&erro={quote('Já existe um cadastro pendente para este QRA.')}")
            salt, digest = password_hash(password)
            request_id = secrets.token_hex(6).upper()
            record = {
                "request_id": request_id,
                "qra": qra,
                "qra_norm": qra_key,
                "passaporte": passaporte,
                "password_salt": salt,
                "password_hash": digest,
                "motivo": motivo,
                "status": "pending",
                "created_at": now(),
                "requested_from": next_path,
            }
            async with lock:
                rows = load_accounts()
                rows = [x for x in rows if str(x.get("qra_norm") or "") != qra_key]
                rows.append(record)
                save_accounts(rows)
            sent = await send_approval(record)
            if not sent:
                await update_account(request_id, status="error")
                raise web.HTTPFound(f"/acesso?next={quote(next_path, safe='/')}&erro={quote('Não foi possível enviar ao canal de aprovação.')}")
            response = web.HTTPFound(f"/acesso?next={quote(next_path, safe='/')}&request={request_id}")
            response.set_cookie(SIGNUP_COOKIE, sign_token("signup", request_id, REQUEST_SECONDS), httponly=True, secure=True, samesite="Lax", path="/")
            raise response

        raise web.HTTPFound("/")

    async def logout(request):
        response = web.HTTPFound("/")
        for name in (ACCOUNT_COOKIE, SIGNUP_COOKIE, STRATEGIC_COOKIE, "dicor_approval", "dicor_strategic"):
            response.del_cookie(name, path="/")
        raise response

    @web.middleware
    async def auth_middleware(request, handler):
        path = str(request.path or "/")
        if path in {"/", "/index.html", "/catalogo", "/acesso", "/sair"} or path.startswith(PUBLIC_PREFIXES):
            return await handler(request)
        if path.startswith("/dossies-central"):
            return web.Response(status=404, text="Módulo removido da Central DICOR.")

        mode, _module = target_mode(path)
        if mode == "account":
            if await valid_account_cookie(request):
                return await handler(request)
            raise web.HTTPFound(f"/acesso?next={quote(path, safe='/')}")
        if mode == "strategic":
            if verify_token(request.cookies.get(STRATEGIC_COOKIE, ""), "strategic"):
                return await handler(request)
            raise web.HTTPFound(f"/acesso?next={quote(path, safe='/')}")

        if path.startswith("/api/"):
            low = path.casefold()
            if "pericia" in low or "bolet" in low:
                if await valid_account_cookie(request):
                    return await handler(request)
                return web.json_response({"ok": False, "erro": "Login com QRA e senha necessário."}, status=401)
            if verify_token(request.cookies.get(STRATEGIC_COOKIE, ""), "strategic"):
                return await handler(request)
            return web.json_response({"ok": False, "erro": "Senha estratégica necessária."}, status=401)
        return await handler(request)

    async def restore_pending() -> None:
        if restored["done"]:
            return
        restored["done"] = True
        for row in load_accounts():
            if row.get("status") != "pending":
                continue
            message_id = int(row.get("discord_message_id") or 0)
            if not message_id:
                continue
            try:
                client.add_view(AccountApprovalView(str(row.get("request_id") or "")), message_id=message_id)
            except Exception:
                pass

    async def on_ready() -> None:
        await restore_pending()
        print(f"✅ V164 Central: aprovação exclusiva no canal {APPROVAL_CHANNEL_ID}; contas QRA+senha ativas.", flush=True)

    if hasattr(client, "add_listener"):
        client.add_listener(on_ready, "on_ready")

    bot_module.central_portal_http = portal
    bot_module.central_login_get = login_get
    bot_module.central_login_post = login_post
    bot_module.central_logout_http = logout
    bot_module.central_auth_middleware = auth_middleware

    print(
        f"✅ V164 instalada — Boletins/Perícias lembram usuário por QRA+senha após 1 aprovação; "
        f"aprovações -> {APPROVAL_CHANNEL_ID}; Banco/Árvore usam só senha estratégica sem conta persistente.",
        flush=True,
    )
