# -*- coding: utf-8 -*-
'''V165 — tela única de acesso da Central DICOR.'''
from __future__ import annotations
import html
from urllib.parse import quote

KNOWN_COOKIE = "dicor_known_v165"
KNOWN_SECONDS = 365 * 24 * 3600


def install(bot_module) -> None:
    web = bot_module.web
    old_get = bot_module.central_login_get
    old_post = bot_module.central_login_post

    def esc(v):
        return html.escape(str(v or ""))

    def account_path(path):
        p = str(path or "/").split("?", 1)[0].lower()
        return p.startswith("/boletins") or p.startswith("/pericias")

    def page(body, title):
        css = """
        *{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 50% -10%,#80651526,transparent 34%),linear-gradient(#080806,#030303);color:#f5f0df;font-family:Inter,Segoe UI,Arial}.top{height:94px;border-bottom:1px solid #40351b;display:flex;justify-content:center;align-items:center;background:#050504ee}.brand{display:flex;align-items:center;gap:15px}.brand img{width:64px;height:64px;object-fit:contain}.brand b{font:20px Georgia,serif;letter-spacing:1.6px}.brand small{display:block;color:#c9a227;font-size:9px;letter-spacing:1.6px;margin-top:4px}.wrap{max-width:700px;margin:auto;padding:44px 20px 70px}.back{color:#bfb697;text-decoration:none;font-size:13px}.card{margin-top:25px;border:1px solid #40351b;background:linear-gradient(150deg,#11100b,#080806);border-radius:19px;padding:34px;box-shadow:0 18px 55px #0009}.seal{text-align:center}.seal img{width:92px}.ey{text-align:center;color:#c9a227;font-size:9px;letter-spacing:2px}.card h1{text-align:center;font:31px Georgia,serif;margin:9px 0}.lead{text-align:center;color:#aaa38e;line-height:1.55;margin:0 auto 22px}.field{margin-top:14px}.field label{display:block;color:#d7c36f;font-size:10px;letter-spacing:1px;margin-bottom:6px}.field input,.field textarea{width:100%;padding:14px;border-radius:9px;border:1px solid #4c3e1c;background:#050504;color:white}.field textarea{min-height:90px;resize:vertical}.btn{width:100%;margin-top:19px;padding:14px;border:1px solid #e0c55a;border-radius:9px;background:linear-gradient(135deg,#f0d878,#c9a227);color:#151207;font-weight:900}.notice{border:1px solid #713632;background:#2d1412;color:#ffc8c2;padding:12px;border-radius:9px;margin:15px 0}.hint,.switch{text-align:center;color:#8f8873;font-size:12px;line-height:1.5;margin-top:15px}.switch a{color:#dfc45f;text-decoration:none}@media(max-width:620px){.card{padding:24px}.top{height:auto;padding:14px}}
        """
        return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{css}</style></head><body><header class="top"><div class="brand"><img src="/central/brasao-dicor.png"><div><b>POLÍCIA FEDERAL — DICOR</b><small>CONTROLE DE ACESSO</small></div></div></header>{body}</body></html>'

    async def login_get(request):
        nxt = str(request.query.get("next") or "/")
        if not account_path(nxt) or request.query.get("request"):
            return await old_get(request)

        err = esc(request.query.get("erro") or "")
        alert = f'<div class="notice">{err}</div>' if err else ""
        force_login = str(request.query.get("modo") or "").lower() == "entrar"
        known = request.cookies.get(KNOWN_COOKIE) == "1" or force_login

        if known:
            body = f'''<main class="wrap"><a class="back" href="/">← Voltar à Central</a><section class="card"><div class="seal"><img src="/central/brasao-dicor.png"></div><div class="ey">ACESSO AUTORIZADO</div><h1>Entrar</h1><p class="lead">Use apenas seu QRA e a senha criada no primeiro acesso.</p>{alert}<form method="post" action="/acesso"><input type="hidden" name="mode" value="account_login_v164"><input type="hidden" name="next" value="{esc(nxt)}"><div class="field"><label>QRA / NOME</label><input name="qra" maxlength="100" autocomplete="username" required autofocus></div><div class="field"><label>SENHA</label><input name="senha" type="password" autocomplete="current-password" required></div><button class="btn">ENTRAR</button></form><div class="hint">Não é necessário pedir nova autorização.</div></section></main>'''
            response = web.Response(text=page(body, "Entrar • Central DICOR"), content_type="text/html", charset="utf-8")
            if force_login:
                response.set_cookie(KNOWN_COOKIE, "1", max_age=KNOWN_SECONDS, httponly=True, secure=True, samesite="Lax", path="/")
            return response

        body = f'''<main class="wrap"><a class="back" href="/">← Voltar à Central</a><section class="card"><div class="seal"><img src="/central/brasao-dicor.png"></div><div class="ey">PRIMEIRO ACESSO</div><h1>Criar acesso</h1><p class="lead">Crie sua conta uma única vez. Depois da aprovação, Boletins e Perícias entram com QRA + senha.</p>{alert}<form method="post" action="/acesso"><input type="hidden" name="mode" value="account_register_v164"><input type="hidden" name="next" value="{esc(nxt)}"><div class="field"><label>QRA / NOME</label><input name="qra" maxlength="100" required autofocus></div><div class="field"><label>PASSAPORTE / RG FUNCIONAL</label><input name="passaporte" maxlength="50" required></div><div class="field"><label>CRIAR SENHA</label><input name="senha" type="password" minlength="6" required></div><div class="field"><label>CONFIRMAR SENHA</label><input name="confirmar" type="password" minlength="6" required></div><div class="field"><label>MOTIVO DO ACESSO</label><textarea name="motivo" maxlength="500" required></textarea></div><button class="btn">CRIAR E ENVIAR PARA APROVAÇÃO</button></form><div class="hint">A senha continua salva somente como hash criptográfico.</div><div class="switch">Já possui cadastro? <a href="/acesso?next={quote(nxt, safe='/')}&modo=entrar">Entrar com QRA + senha</a></div></section></main>'''
        return web.Response(text=page(body, "Criar acesso • Central DICOR"), content_type="text/html", charset="utf-8")

    async def login_post(request):
        form = await request.post()
        mode = str(form.get("mode") or "")
        try:
            result = await old_post(request)
        except web.HTTPException as exc:
            location = str(exc.headers.get("Location") or "")
            ok_register = mode == "account_register_v164" and "request=" in location
            ok_login = mode == "account_login_v164" and "erro=" not in location
            if ok_register or ok_login:
                exc.set_cookie(KNOWN_COOKIE, "1", max_age=KNOWN_SECONDS, httponly=True, secure=True, samesite="Lax", path="/")
            raise
        return result

    bot_module.central_login_get = login_get
    bot_module.central_login_post = login_post
    print("✅ V165 Central: primeiro acesso mostra cadastro; depois mostra somente login QRA + senha.", flush=True)
