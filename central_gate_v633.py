"""DICOR Central V633 - camada de autorização, perfis, cargos e auditoria."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
import central_visual_v632 as visual
import central_discord_v613 as base
import central_procurados_v626 as v625
try:
    import discord
except Exception:
    discord = None
ACCESS_CHANNEL = 1548072610447884399
LOG_FILE = Path(os.getenv("CENTRAL_LOG_FILE", "central_access_logs_v633.json"))
ADMIN_QRA = os.getenv("CENTRAL_ADMIN_QRA", "").strip().casefold()
ADMIN_PASS = os.getenv("CENTRAL_ADMIN_PASSAPORTE", "").strip().casefold()
ROLES = ("Oficial", "Polícia Federal", "DICOR")
_CLIENT = None

def esc(v):
    import html
    return html.escape(str(v or ""), quote=True)

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")

def accounts():
    data = base.load_accounts(); changed = False
    for key, user in data.items():
        if not isinstance(user, dict): continue
        defaults = {"authorized": False, "access_request_pending": False, "role": "Oficial", "profile_photo": "", "qra": key.split("|", 1)[0], "passaporte": key.split("|", 1)[-1]}
        for name, value in defaults.items():
            if name not in user: user[name] = value; changed = True
    if changed: base.save_accounts(data)
    return data

def current(req):
    session = base.read_session(req)
    if not session: return "", "", None
    qra, passport = session; data = accounts(); key = base.account_key(qra, passport); user = data.get(key)
    if isinstance(user, dict): user.update(qra=qra, passaporte=passport); data[key] = user; base.save_accounts(data)
    return qra, passport, user if isinstance(user, dict) else None

def is_admin(qra, passport, user):
    if ADMIN_QRA and ADMIN_PASS: return qra.casefold() == ADMIN_QRA and passport.casefold() == ADMIN_PASS
    return bool(user and user.get("is_admin"))

def audit(qra, passport, action, path="", target=""):
    try: rows = json.loads(LOG_FILE.read_text(encoding="utf-8")) if LOG_FILE.exists() else []
    except Exception: rows = []
    if not isinstance(rows, list): rows = []
    rows.append({"time": now(), "qra": qra, "passaporte": passport, "action": action, "path": path, "target": target})
    LOG_FILE.write_text(json.dumps(rows[-10000:], ensure_ascii=False, indent=2), encoding="utf-8")

async def request_access(req):
    qra, passport, user = current(req)
    if not user: raise base.web.HTTPFound("/cadastro-operador")
    if user.get("authorized"): raise base.web.HTTPFound("/funcionalidades")
    data = accounts(); key = base.account_key(qra, passport); data[key]["access_request_pending"] = True; data[key]["access_requested_at"] = now(); base.save_accounts(data); audit(qra, passport, "SOLICITOU_AUTORIZACAO", req.path)
    try:
        channel = await base.get_channel(_CLIENT, ACCESS_CHANNEL)
        if channel and discord:
            embed = discord.Embed(title="SOLICITAÇÃO DE ACESSO • DICOR", description=f"QRA: {qra}\nPassaporte: {passport}\nCargo: {user.get('role', 'Oficial')}", color=0xD6AD4E)
            await channel.send(embed=embed, view=ApprovalView(key))
    except Exception as exc: print(f"⚠️ V633 autorização: {type(exc).__name__}: {exc}", flush=True)
    body = "<main class='auth'><h1>Solicitação enviada</h1><p class='sub'>Seu pedido foi enviado ao canal interno de autorização.</p><a class='primary gold' href='/'>VOLTAR À CENTRAL</a></main>"
    return base.web.Response(text=base.page("DICOR • Solicitação", body, base.AUTH_CSS), content_type="text/html")

if discord:
    class ApprovalView(discord.ui.View):
        def __init__(self, key): super().__init__(timeout=None); self.key = key
        @discord.ui.button(label="APROVAR ACESSO", style=discord.ButtonStyle.success, custom_id="dicor_v633_approve")
        async def approve(self, interaction, button):
            if not interaction.user.guild_permissions.manage_guild: return await interaction.response.send_message("Sem permissão para aprovar.", ephemeral=True)
            data = accounts(); user = data.get(self.key)
            if isinstance(user, dict): user["authorized"] = True; user["access_request_pending"] = False; user["authorized_at"] = now(); data[self.key] = user; base.save_accounts(data); audit(user.get("qra", ""), user.get("passaporte", ""), "AUTORIZACAO_APROVADA", "/admin", str(interaction.user))
            await interaction.response.edit_message(content="✅ Acesso aprovado.", embed=None, view=None)
        @discord.ui.button(label="RECUSAR", style=discord.ButtonStyle.danger, custom_id="dicor_v633_reject")
        async def reject(self, interaction, button):
            if not interaction.user.guild_permissions.manage_guild: return await interaction.response.send_message("Sem permissão para recusar.", ephemeral=True)
            data = accounts(); user = data.get(self.key)
            if isinstance(user, dict): user["access_request_pending"] = False; data[self.key] = user; base.save_accounts(data); audit(user.get("qra", ""), user.get("passaporte", ""), "AUTORIZACAO_RECUSADA", "/admin")
            await interaction.response.edit_message(content="❌ Solicitação recusada.", embed=None, view=None)

def user_by_qra(qra):
    for user in accounts().values():
        if isinstance(user, dict) and str(user.get("qra", "")).casefold() == str(qra).casefold(): return user, str(user.get("passaporte", ""))
    return {}, ""

def guarded_functions(qra):
    user, passport = user_by_qra(qra)
    if not user.get("authorized"):
        body = "<main class='auth'><h1>Área protegida</h1><p class='sub'>Solicite autorização para acessar Boletins, Perícias e Operações.</p><a class='primary gold' href='/solicitar-acesso'>SOLICITAR AUTORIZAÇÃO</a></main>"
        return base.page("DICOR • Acesso", body, base.AUTH_CSS)
    cards = ''.join(f"<article class='module'><h3>{title}</h3><p>{desc}</p><a href='{href}'>ABRIR MÓDULO →</a></article>" for title, desc, href in (("BOLETINS", "Somente registros completos.", "/boletins"), ("PERÍCIAS", "Somente registros completos.", "/pericias"), ("OPERAÇÕES", "Área operacional autorizada.", "/operacoes")))
    body = f"<div class='app'><main class='main'><header class='top'><div class='pcpt-title'>PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<span>DICOR • CENTRAL DE INTELIGÊNCIA</span></div><div class='operator'>{esc(qra)} • {esc(passport)}</div></header><section class='hero'><div class='eyebrow'>DICOR • ACESSO OPERACIONAL</div><h1>FUNCIONALIDADES</h1></section><div class='module-grid'>{cards}</div></main></div>"
    return base.page("DICOR • Funcionalidades", body, base.APP_CSS)

async def profile(req):
    qra, passport, user = current(req)
    if not user: raise base.web.HTTPFound("/cadastro-operador")
    photo = esc(user.get("profile_photo", "")); avatar = f"<img src='{photo}' alt='Foto'>" if photo else f"<span style='font-size:35px'>{esc(qra[:1])}</span>"
    body = f"<main class='auth'><div class='profile-photo'>{avatar}</div><h1>{esc(qra)}</h1><p class='sub'>PASSAPORTE {esc(passport)} • {esc(user.get('role'))}</p><form class='form' method='post' action='/perfil/upload' enctype='multipart/form-data'><label>FOTO DE PERFIL</label><input type='file' name='foto' accept='image/*' required><button class='primary gold' type='submit'>ATUALIZAR FOTO</button></form></main>"
    audit(qra, passport, "ABRIU_PERFIL", req.path)
    return base.web.Response(text=base.page("DICOR • Perfil", body, base.AUTH_CSS), content_type="text/html")

async def profile_upload(req):
    qra, passport, user = current(req)
    if not user: raise base.web.HTTPFound("/cadastro-operador")
    reader = await req.multipart(); part = await reader.next(); data = await part.read(decode=False) if part else b""; filename = os.path.basename(part.filename or "perfil.png") if part else "perfil.png"
    if not part or len(data) > 10 * 1024 * 1024: raise base.web.HTTPBadRequest(text="Imagem inválida.")
    try:
        url = await v625.v625.upload_to_fivemanage(data, filename); data = accounts(); data[base.account_key(qra, passport)]["profile_photo"] = url; base.save_accounts(data); audit(qra, passport, "ALTEROU_FOTO_PERFIL", req.path); raise base.web.HTTPFound("/perfil")
    except base.web.HTTPException: raise
    except Exception: raise base.web.HTTPBadGateway(text="Não foi possível atualizar a foto.")

async def admin_page(req):
    qra, passport, user = current(req)
    if not user or not is_admin(qra, passport, user): raise base.web.HTTPForbidden(text="Acesso administrativo restrito.")
    users=[]
    for key,item in accounts().items():
        if not isinstance(item,dict): continue
        opts=''.join(f"<option {'selected' if item.get('role')==role else ''}>{esc(role)}</option>" for role in ROLES)
        users.append(f"<div class='module'><b>{esc(item.get('qra'))}</b><p>Passaporte {esc(item.get('passaporte'))} • {esc(item.get('role'))}</p><form method='post' action='/admin/role'><input type='hidden' name='key' value='{esc(key)}'><select name='role'>{opts}</select><button class='primary gold' type='submit'>SALVAR CARGO</button></form></div>")
    try: logs=json.loads(LOG_FILE.read_text(encoding='utf-8')) if LOG_FILE.exists() else []
    except Exception: logs=[]
    log_html=''.join(f"<div class='module'><b>{esc(x.get('action'))}</b><p>{esc(x.get('time'))} • {esc(x.get('qra'))} • Passaporte {esc(x.get('passaporte'))}</p></div>" for x in logs[-300:][::-1])
    body=f"<main class='auth' style='width:min(1100px,calc(100% - 28px))'><h1>PAINEL ADMIN</h1><p class='sub'>Usuários, cargos, autorizações e logs.</p><div class='module-grid'>{''.join(users)}</div><h2 style='margin-top:25px'>LOGS</h2><div class='module-grid'>{log_html or '<p>Nenhum log.</p>'}</div></main>"
    audit(qra,passport,"ABRIU_PAINEL_ADMIN",req.path)
    return base.web.Response(text=base.page("DICOR • Admin",body,base.AUTH_CSS),content_type="text/html")

async def admin_role(req):
    qra, passport, user = current(req)
    if not user or not is_admin(qra, passport, user): raise base.web.HTTPForbidden(text="Acesso administrativo restrito.")
    post=await req.post(); data=accounts(); target=data.get(str(post.get("key",""))); role=str(post.get("role",""))
    if not isinstance(target,dict) or role not in ROLES: raise base.web.HTTPBadRequest(text="Dados inválidos.")
    target["role"]=role; data[str(post.get("key"))]=target; base.save_accounts(data); audit(qra,passport,"CARGO_ALTERADO","/admin",role); raise base.web.HTTPFound("/admin")

async def operations(req):
    qra, passport, user = current(req)
    if not user or not user.get("authorized"): return base.web.Response(text=guarded_functions(qra),status=403,content_type="text/html")
    body=f"<main class='auth'><h1>OPERAÇÕES</h1><p class='sub'>Acesso autorizado para {esc(qra)}.</p><span>ACESSO LIBERADO</span></main>"
    audit(qra,passport,"ABRIU_OPERACOES",req.path)
    return base.web.Response(text=base.page("DICOR • Operações",body,base.AUTH_CSS),content_type="text/html")

def install(bot_module):
    global _CLIENT
    central=visual.install(bot_module); base.functionalities=guarded_functions
    async def start(client):
        global _CLIENT
        _CLIENT=client; v625._CLIENT=client
        original_init=v625.ApplicationPatch.__init__
        def init(self,*args,**kwargs):
            kwargs["client_max_size"]=12*1024*1024; original_init(self,*args,**kwargs)
            self.router.add_get("/solicitar-acesso",request_access,name="v633_access")
            self.router.add_get("/perfil",profile,name="v633_profile")
            self.router.add_post("/perfil/upload",profile_upload,name="v633_profile_upload")
            self.router.add_get("/admin",admin_page,name="v633_admin")
            self.router.add_post("/admin/role",admin_role,name="v633_role")
            self.router.add_get("/operacoes",operations,name="v633_operations")
        v625.ApplicationPatch.__init__=init
        return await v625.start_server_v626(client)
    base.start_server=start
    return central
