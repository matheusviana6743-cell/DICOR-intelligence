# -*- coding: utf-8 -*-
"""DICOR Central V700 - painel seguro, autorização, registros, FiveM e IMAP."""
from __future__ import annotations
import asyncio,base64,email,email.header,hashlib,hmac,html,imaplib,json,mimetypes,os,re,secrets,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
from aiohttp import web
import central_discord_v613 as source
try: import discord
except Exception: discord=None

PORT=int(os.getenv("PORT","8080") or 8080); ACCESS_CHANNEL=1548072610447884399; COOKIE="dicor_central_v700"; MAX_AGE=30*86400; ONLINE=180; REFRESH=max(30,int(os.getenv("CENTRAL_REFRESH_SECONDS","60") or 60)); MAX_IMAGE=10*1024*1024
DATA=Path(os.getenv("DICOR_DATA_DIR",getattr(source,"BASE_DIR",Path(__file__).parent))); USERS=DATA/"central_users_v700.json"; LOG=DATA/"central_access_logs_v700.json"; SECRET_FILE=DATA/"central_session_secret_v700.txt"
LOGO=str(os.getenv("DICOR_LOGO_URL","https://raw.githubusercontent.com/matheusviana6743-cell/DICOR-intelligence/main/marca_dagua_dicor.png")).strip(); ADMIN_QRA=str(os.getenv("CENTRAL_ADMIN_QRA","")).strip().casefold(); ADMIN_PASS=str(os.getenv("CENTRAL_ADMIN_PASSAPORTE","")).strip().casefold(); ADMIN_DISCORD=int(os.getenv("CENTRAL_ADMIN_DISCORD_ID","0") or 0); OPS_CHANNEL=int(os.getenv("DICOR_OPERACOES_CHANNEL_ID","0") or 0)
MAIL_HOST=str(os.getenv("DICOR_MAIL_HOST","")).strip(); MAIL_PORT=int(os.getenv("DICOR_MAIL_PORT","993") or 993); MAIL_USER=str(os.getenv("DICOR_MAIL_USER","")).strip(); MAIL_PASS=str(os.getenv("DICOR_MAIL_PASSWORD","")); MAIL_FOLDER=str(os.getenv("DICOR_MAIL_FOLDER","INBOX")).strip() or "INBOX"; MAIL_LIMIT=max(20,min(250,int(os.getenv("DICOR_MAIL_LIMIT","120") or 120)))
C={"procurados":[],"boletins":[],"pericias":[],"operacoes":[],"updated":0.0,"refreshing":False}; CLIENT=None; TASK=None; STARTED=False; VIEW=False

def clean(v): return " ".join(str(v or "").split())
def esc(v): return html.escape(str(v or ""),quote=True)
def iso(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def now(): return int(time.time())
def k(q,p): return f"{clean(q).casefold()}|{clean(p).casefold()}"
def aw(path,obj): path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8"); os.replace(tmp,path)
def users():
    try:
        x=json.loads(USERS.read_text(encoding="utf-8")) if USERS.exists() else {}; return x if isinstance(x,dict) else {}
    except Exception:return {}
def save_users(x): aw(USERS,x)
def audit(action,u=None,target=""):
    try:
        x=json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else []; x=x if isinstance(x,list) else []; x.append({"time":iso(),"action":action,"qra":str((u or {}).get("qra","")),"passaporte":str((u or {}).get("passaporte","")),"target":target}); aw(LOG,x[-10000:])
    except Exception: pass

def secret():
    v=str(os.getenv("CENTRAL_DICOR_COOKIE_SECRET","")).strip()
    if v:return v
    try:
        if SECRET_FILE.exists() and len((v:=SECRET_FILE.read_text(encoding="utf-8").strip()))>=48:return v
        DATA.mkdir(parents=True,exist_ok=True); v=secrets.token_urlsafe(64); t=SECRET_FILE.with_suffix(".tmp"); t.write_text(v,encoding="utf-8"); os.replace(t,SECRET_FILE); return v
    except Exception:return secrets.token_urlsafe(64)
SECRET=secret()
def csrf(u): return hmac.new(SECRET.encode(),("csrf|"+k(u.get("qra"),u.get("passaporte"))).encode(),hashlib.sha256).hexdigest()
def session(kv):
    raw=base64.urlsafe_b64encode(f"{kv}|{now()}".encode()).decode().rstrip("="); return raw+"."+hmac.new(SECRET.encode(),raw.encode(),hashlib.sha256).hexdigest()
def current(req):
    t=req.cookies.get(COOKIE,"")
    try:
        raw,sig=t.rsplit(".",1); exp=hmac.new(SECRET.encode(),raw.encode(),hashlib.sha256).hexdigest()
        if not t or not hmac.compare_digest(sig,exp):return None
        kv,issued=base64.urlsafe_b64decode(raw+"="*(-len(raw)%4)).decode().rsplit("|",1)
        if now()-int(issued)>MAX_AGE:return None
        u=users().get(kv); return u if isinstance(u,dict) else None
    except Exception:return None
def is_admin(u):
    if not u:return False
    return bool(u.get("is_admin")) or bool(ADMIN_QRA and ADMIN_PASS and str(u.get("qra","")).casefold()==ADMIN_QRA and str(u.get("passaporte","")).casefold()==ADMIN_PASS)
def touch(u):
    x=users(); kk=k(u.get("qra"),u.get("passaporte")); z=x.get(kk)
    if not isinstance(z,dict):return u
    z["last_seen"]=now(); z["updated_at"]=iso();
    if ADMIN_QRA and ADMIN_PASS and str(z.get("qra","")).casefold()==ADMIN_QRA and str(z.get("passaporte","")).casefold()==ADMIN_PASS:z["is_admin"]=True
    x[kk]=z; save_users(x); u.update(z); return u
def online(u):
    try:return now()-int(u.get("last_seen",0) or 0)<=ONLINE
    except:return False

BOILER=(re.compile(r"^\s*(?:📌\s*)?TAREFA\s+PENDENTE\b.*$",re.I),re.compile(r"^\s*ATENDIMENTO\s*:.*$",re.I),re.compile(r"^\s*REGISTRE\s+NO\s+PAINEL\b.*$",re.I),re.compile(r"^\s*ENVOLVIDO\s+PEGAD[OA]\s+PELO\s+PAINEL\b.*$",re.I),re.compile(r"^\s*RESPONSÁVEL\s*:\s*@\[.*$",re.I))
def clean_source(v):
    s=str(v or ""); s=re.sub(r"\[([^\]]*)\]\((?:https?://|/)[^)]*\)",r"\1",s); s=re.sub(r"https?://(?:discord\.com|cdn\.discordapp\.com|media\.discordapp\.net)[^\s)>]*","",s,flags=re.I); s=s.replace("**","").replace("__","").replace("`",""); out=[]
    for ln in re.split(r"\r?\n+",s):
        ln=clean(ln)
        if not ln or any(p.search(ln) for p in BOILER) or re.search(r"^tópico\s*🟠",ln,re.I):continue
        out.append(ln)
    return "\n".join(out)
def field(t,labels):
    p="|".join(re.escape(x) for x in labels); m=re.search(rf"(?:{p})\s*[:=-]\s*(.+)",t or "",re.I); return clean_source(m.group(1))[:260] if m else "Não informado"
def number(t):
    m=re.search(r"(?:N[º°O.]?|NO|#)\s*(\d{1,8})",t or "",re.I); return f"{int(m.group(1)):04d}" if m else "S/N"
def img_url(t):
    m=re.search(r"https?://[^\s)]+\.(?:png|jpe?g|webp|gif)(?:\?[^\s)]*)?",t or "",re.I); return m.group(0) if m else ""
def discord_row(kind,r):
    full=clean_source(r.get("full_text") or r.get("preview") or r.get("content")); name=clean_source(r.get("name")) or field(full,("nome","indivíduo","individuo","procurado","envolvido")) or "Indivíduo não identificado"; fs={"Número do registro":r.get("number") or number(full),"Nome":name,"RG / Passaporte":r.get("rg") or field(full,("rg","passaporte","rg/passaporte")),"Crimes":r.get("crime") or field(full,("crime","crimes","acusação","acusacao")),"Localização":r.get("last_seen") or r.get("location") or field(full,("localização","localizacao","local","último avistamento","ultimo avistamento")),"Situação":r.get("status") or field(full,("status","situação","situacao"))}
    return {"id":str(r.get("id") or r.get("source_id") or hashlib.sha256(full.encode()).hexdigest()[:20]),"number":clean(r.get("number")) or number(full),"name":name,"kind":kind,"source":"DISCORD","subject":"","date":str(r.get("created") or ""),"image":str(r.get("image") or img_url(full)),"url":str(r.get("url") or ""),"fields":{x:clean_source(y) or "Não informado" for x,y in fs.items()},"full_text":full or "Sem informações adicionais."}

def dh(v):
    if not v:return ""
    out=[]
    for a,c in email.header.decode_header(str(v)):out.append(a.decode(c or "utf-8",errors="replace") if isinstance(a,bytes) else str(a))
    return clean("".join(out))
def mail_body(msg):
    parts=[]; files=[]
    for part in msg.walk() if msg.is_multipart() else [msg]:
        fn=part.get_filename()
        if fn:files.append(dh(fn))
        if "attachment" in str(part.get("Content-Disposition","")).lower():continue
        if part.get_content_type().lower() not in ("text/plain","text/html"):continue
        b=part.get_payload(decode=True)
        if not b:continue
        s=b.decode(part.get_content_charset() or "utf-8",errors="replace"); parts.append(re.sub(r"<[^>]+>","\n",html.unescape(s)) if part.get_content_type().lower()=="text/html" else s)
    return "\n".join(parts),files
def mail_kind(sub,body):
    t=f"{sub}\n{body}".casefold()
    if any(x in t for x in ("procurado","foragido","mandado")):return "procurados"
    if any(x in t for x in ("boletim","b.o.","ocorrência","ocorrencia")):return "boletins"
    if any(x in t for x in ("perícia","pericia","laudo pericial")):return "pericias"
    if any(x in t for x in ("operação","operacao")):return "operacoes"
    return None
def mail_row(kind,msg,uid,body,files):
    sub=dh(msg.get("Subject", "")); full=clean_source(body); mid=clean(msg.get("Message-ID", "")) or f"{uid}|{sub}|{msg.get('Date','')}"; name=field(full,("nome","indivíduo","individuo","procurado","envolvido","autor")) or next((x for x in full.splitlines() if x),"Indivíduo não identificado"); fs={"Assunto":sub or "Sem assunto","Remetente":dh(msg.get("From", "")) or "Não informado","Data do e-mail":dh(msg.get("Date", "")) or "Não informado","Número do registro":number(f"{sub}\n{full}"),"Nome":name,"RG / Passaporte":field(full,("rg","passaporte","rg/passaporte")),"Crimes":field(full,("crime","crimes","acusação","acusacao")),"Localização":field(full,("localização","localizacao","local","último avistamento","ultimo avistamento")),"Situação":field(full,("status","situação","situacao","resultado"))}
    if files:fs["Anexos do e-mail"]=", ".join(files)
    for ln in full.splitlines():
        m=re.match(r"^([^:]{2,70})\s*:\s*(.+)$",clean(ln))
        if m:fs.setdefault(clean(m.group(1)).strip("•-"),clean(m.group(2)))
    return {"id":hashlib.sha256(mid.encode()).hexdigest()[:20],"number":fs["Número do registro"],"name":clean(name),"kind":kind,"source":"E-MAIL","subject":sub,"date":dh(msg.get("Date", "")),"image":img_url(full),"url":"","fields":fs,"full_text":full or "Sem informações adicionais."}
def poll_mail_sync():
    out={x:[] for x in ("procurados","boletins","pericias","operacoes")}
    if not(MAIL_HOST and MAIL_USER and MAIL_PASS):return out
    c=None
    try:
        c=imaplib.IMAP4_SSL(MAIL_HOST,MAIL_PORT,timeout=20); c.login(MAIL_USER,MAIL_PASS); ok,_=c.select(MAIL_FOLDER,readonly=True)
        if ok!="OK":return out
        ok,data=c.uid("search",None,"ALL")
        if ok!="OK" or not data or not data[0]:return out
        for uid in reversed(data[0].split()[-MAIL_LIMIT:]):
            ok,f=c.uid("fetch",uid,"(BODY.PEEK[])"); raw=b"".join(z[1] for z in f or [] if isinstance(z,tuple) and isinstance(z[1],bytes))
            if ok!="OK" or not raw:continue
            msg=email.message_from_bytes(raw); body,files=mail_body(msg); kind=mail_kind(dh(msg.get("Subject","")),body)
            if kind:out[kind].append(mail_row(kind,msg,uid,body,files))
        return out
    finally:
        if c:
            try:c.logout()
            except Exception:pass
async def poll_mail():
    try:return await asyncio.to_thread(poll_mail_sync)
    except Exception as e:print(f"⚠️ [CENTRAL MAIL] {type(e).__name__}",flush=True); return {x:[] for x in ("procurados","boletins","pericias","operacoes")}
async def ops_discord():
    if not(OPS_CHANNEL and CLIENT and getattr(CLIENT,"is_ready",lambda:False)()):return []
    try:
        ch=CLIENT.get_channel(OPS_CHANNEL) or await CLIENT.fetch_channel(OPS_CHANNEL); out=[]
        async for m in ch.history(limit=120):
            t=clean_source(source.text_of(m))
            if t:out.append({"id":str(getattr(m,"id","")),"number":number(t),"name":field(t,("operação","operacao","nome")) or "Operação","kind":"operacoes","source":"DISCORD","subject":"","date":str(getattr(m,"created_at","")),"image":source.media_url(m),"url":str(getattr(m,"jump_url","")),"fields":{"Número do registro":number(t)},"full_text":t})
        return out
    except Exception:return []
async def refresh_data():
    if C["refreshing"]:return
    C["refreshing"]=True
    try:
        if CLIENT and getattr(CLIENT,"is_ready",lambda:False)():
            try:await source.refresh(CLIENT)
            except Exception:pass
        d={"procurados":[discord_row("procurados",r) for r in source.CACHE.get("procurados",[]) if isinstance(r,dict)],"boletins":[discord_row("boletins",r) for r in source.CACHE.get("bo",[]) if isinstance(r,dict)],"pericias":[discord_row("pericias",r) for r in source.CACHE.get("pericia",[]) if isinstance(r,dict)],"operacoes":await ops_discord()}; m=await poll_mail()
        for x in d:C[x]=m.get(x) or d[x] or C.get(x) or []
        C["updated"]=time.time()
    finally:C["refreshing"]=False
async def loop():
    while True:
        try:await refresh_data()
        except asyncio.CancelledError:raise
        except Exception as e:print(f"⚠️ [CENTRAL V700] {type(e).__name__}",flush=True)
        await asyncio.sleep(REFRESH)

def can_approve(i):return bool(ADMIN_DISCORD and int(getattr(getattr(i,"user",None),"id",0) or 0)==ADMIN_DISCORD)
def approval_user(i):
    try:
        es=getattr(i.message,"embeds",[]) or []; ft=str(getattr(getattr(es[0],"footer",None),"text","") or "") if es else ""; m=re.search(r"DICOR700\|([A-Za-z0-9_-]{12,90})",ft); token=m.group(1) if m else ""
        return next((u for u in users().values() if isinstance(u,dict) and u.get("approval_token")==token),None)
    except Exception:return None
if discord:
    class ApprovalView(discord.ui.View):
        def __init__(self):super().__init__(timeout=None)
        @discord.ui.button(label="APROVAR ACESSO",style=discord.ButtonStyle.success,custom_id="dicor700:approve")
        async def approve(self,i,b):
            if not can_approve(i):return await i.response.send_message("Sem autorização para aprovar este pedido.",ephemeral=True)
            u=approval_user(i)
            if not u:return await i.response.send_message("Pedido não localizado.",ephemeral=True)
            x=users(); kk=k(u.get("qra"),u.get("passaporte")); z=x.get(kk)
            if not isinstance(z,dict):return await i.response.send_message("Usuário não encontrado.",ephemeral=True)
            z.update(authorized=True,access_request_pending=False,authorized_at=iso(),approval_token="");x[kk]=z;save_users(x);audit("AUTORIZACAO_APROVADA",z,str(i.user.id));await i.response.edit_message(content="✅ ACESSO DICOR APROVADO",embed=None,view=None)
        @discord.ui.button(label="RECUSAR",style=discord.ButtonStyle.danger,custom_id="dicor700:reject")
        async def reject(self,i,b):
            if not can_approve(i):return await i.response.send_message("Sem autorização para recusar este pedido.",ephemeral=True)
            u=approval_user(i)
            if not u:return await i.response.send_message("Pedido não localizado.",ephemeral=True)
            x=users(); kk=k(u.get("qra"),u.get("passaporte")); z=x.get(kk)
            if not isinstance(z,dict):return await i.response.send_message("Usuário não encontrado.",ephemeral=True)
            z.update(access_request_pending=False,approval_token="");x[kk]=z;save_users(x);audit("AUTORIZACAO_RECUSADA",z,str(i.user.id));await i.response.edit_message(content="❌ SOLICITAÇÃO RECUSADA",embed=None,view=None)
async def request_access(u):
    if not(CLIENT and discord):return False
    try:
        ch=CLIENT.get_channel(ACCESS_CHANNEL) or await CLIENT.fetch_channel(ACCESS_CHANNEL)
        if not ch:return False
        x=users(); kk=k(u.get("qra"),u.get("passaporte")); z=x.get(kk); token=str(z.get("approval_token") or secrets.token_urlsafe(18)); z["approval_token"]=token;z["access_request_pending"]=True;z["access_requested_at"]=iso();x[kk]=z;save_users(x);e=discord.Embed(title="SOLICITAÇÃO DE ACESSO • CENTRAL DICOR",description="Operador solicitou acesso à área restrita.",color=0xD6AD4E); e.add_field(name="QRA",value=str(z.get("qra","")),inline=True);e.add_field(name="PASSAPORTE",value=str(z.get("passaporte","")),inline=True);e.add_field(name="NOME",value=str(z.get("nome","") or "Não informado"),inline=False);e.add_field(name="CARGO",value=str(z.get("cargo","") or "Não informado"),inline=False);e.set_thumbnail(url=LOGO);e.set_footer(text=f"DICOR700|{token}");await ch.send(embed=e,view=ApprovalView(),allowed_mentions=discord.AllowedMentions.none());audit("SOLICITOU_AUTORIZACAO",z,str(ACCESS_CHANNEL));return True
    except Exception as e:print(f"⚠️ [CENTRAL ACCESS] {type(e).__name__}",flush=True);return False

CSS=r'''*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;background:radial-gradient(circle at 85% -10%,#113858 0,#07131e 34%,#03080e 74%);color:#eef4f8}body{overflow-x:hidden}a{text-decoration:none;color:inherit}button,input{font:inherit}.top{position:sticky;top:0;z-index:50;display:flex;align-items:center;gap:18px;min-height:70px;padding:9px 22px;background:#04101aee;border-bottom:1px solid #19384d;backdrop-filter:blur(16px)}.brand{display:flex;align-items:center;gap:9px;min-width:285px}.brand img{width:42px;height:42px;object-fit:contain}.brand b{display:block;font-size:9px;letter-spacing:1.2px}.brand span{display:block;color:#d9b554;font-size:10px;letter-spacing:3px;font-weight:900;margin-top:3px}.nav{display:flex;gap:16px;margin-left:auto}.nav a{color:#7c95a7;font-size:7px;font-weight:900;letter-spacing:1px}.nav a:hover{color:#fff}.top-actions{display:flex;align-items:center;gap:12px}.user{display:flex;align-items:center;gap:7px}.dot{width:7px;height:7px;border-radius:50%;background:#58d49a;box-shadow:0 0 10px #58d49a}.user b{font-size:8px}.user small{display:block;color:#647d91;font-size:6px;margin-top:2px}.logout{border:1px solid #29495f;background:#071722;color:#8da4b4;border-radius:7px;padding:7px 9px;font-size:7px;font-weight:900;cursor:pointer}.wrap{position:relative;z-index:1;width:min(1450px,calc(100% - 30px));margin:auto;padding:25px 0 45px}.panel{border:1px solid #18384f;border-radius:17px;background:linear-gradient(145deg,#0b1927f7,#06111af7);box-shadow:0 18px 60px #0008;padding:28px}.hero{display:grid;grid-template-columns:1.1fr .9fr;gap:15px}.copy{min-height:305px}.k{color:#4da7dc;font-size:7px;font-weight:900;letter-spacing:2px}.hero h1{font-size:43px;line-height:1.03;margin:9px 0}.hero h1 span{color:#e0bd55}.sub{color:#7890a4;font-size:10px;line-height:1.7;margin:0}.mark{display:grid;place-items:center;min-height:305px;position:relative;overflow:hidden;background:radial-gradient(circle,#123b5c,#081723 54%,#06101a)}.mark:before{content:"";width:230px;height:230px;border:1px solid #4ba5dc55;border-radius:50%;box-shadow:0 0 0 32px #4ba5dc0c,0 0 0 64px #4ba5dc06;position:absolute}.mark img{width:145px;height:145px;object-fit:contain;position:relative}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:20px}.stat{padding:11px;border:1px solid #18384e;border-radius:9px;background:#07131e}.stat small{color:#628099;font-size:6px;font-weight:900;letter-spacing:1px}.stat b{display:block;margin-top:5px;font-size:21px}.stat.gold b{color:#f0d270}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:19px}.btn{display:inline-flex;align-items:center;justify-content:center;min-height:41px;padding:0 14px;border:1px solid #285a79;border-radius:8px;background:#0a1c2b;color:#a9cae0;font-size:7px;font-weight:950;letter-spacing:1px;cursor:pointer}.btn.gold{border:0;background:linear-gradient(135deg,#f0d16d,#a67418);color:#080b0e}.btn.lock{background:#121b24;color:#c2cbd2}.head{display:flex;justify-content:space-between;align-items:end;gap:10px;margin:24px 2px 11px}.head span{display:block;color:#4ca4da;font-size:6px;font-weight:900;letter-spacing:1.7px}.head h2{margin:5px 0 0;font-size:15px;letter-spacing:1.2px}.head a{font-size:7px;color:#82b2d2;font-weight:900}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:13px}.card{border:1px solid #18384f;border-radius:14px;overflow:hidden;background:#07131e}.photo{height:220px;background:#03080d;display:grid;place-items:center;position:relative}.photo img{width:100%;height:100%;object-fit:cover}.tag{position:absolute;top:9px;left:9px;background:#050b11dd;border:1px solid #d8b55455;color:#eed478;border-radius:6px;padding:5px 7px;font-size:6px;font-weight:900}.body{padding:14px}.body h3{margin:0 0 8px;font-size:15px}.body p{margin:0;color:#71899d;font-size:8px;line-height:1.55;min-height:36px}.line{display:flex;justify-content:space-between;gap:10px;border-top:1px solid #143146;margin-top:9px;padding-top:8px}.line span{font-size:6px;color:#58738a;letter-spacing:1px}.line b{max-width:70%;font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.notice{display:flex;align-items:center;justify-content:space-between;gap:15px;margin-top:16px;padding:15px;border:1px solid #73591f;border-radius:11px;background:linear-gradient(110deg,#15130e,#08111a)}.notice strong{display:block;color:#f0d270;font-size:11px}.notice small{display:block;color:#887a58;font-size:7px;margin-top:3px}.status{margin-top:8px;padding:8px;border:1px solid #1b3a50;border-radius:8px;color:#85a0b3;font-size:8px}.status.ok{border-color:#2b6a53;color:#83dcae}.status.pend{border-color:#73581e;color:#e1c25f}.quick{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}.qcard{padding:15px;border:1px solid #18384f;border-radius:12px;background:#07131e}.qcard h3{margin:0 0 6px;font-size:11px}.qcard p{margin:0;color:#7890a4;font-size:8px;line-height:1.6}.login{max-width:530px;margin:40px auto}.login .panel{text-align:center}.logo{width:92px;height:92px;object-fit:contain}.form{display:grid;gap:10px;text-align:left;margin-top:18px}.field label{display:block;font-size:7px;color:#8197a8;font-weight:900;letter-spacing:1.1px;margin-bottom:5px}.field input{width:100%;height:45px;border:1px solid #24465e;border-radius:8px;background:#06111a;color:#eef4f8;padding:0 11px;outline:none;font-size:11px}.field input:focus{border-color:#dbb653;box-shadow:0 0 0 3px #dbb65320}.modules,.records{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:17px}.module,.record{padding:15px;border:1px solid #18384f;border-radius:12px;background:#07131e}.module h3{margin:0 0 6px;font-size:11px}.module p{margin:0;color:#7890a4;font-size:8px;line-height:1.6}.module .btn{width:100%;margin-top:11px}.rhead{display:flex;justify-content:space-between;gap:8px}.rhead b{font-size:10px}.badge{font-size:6px;font-weight:900;padding:4px 6px;border-radius:6px;background:#103550;color:#82c0e5}.meta{margin-top:6px;color:#6b8498;font-size:6px}.fields{display:grid;gap:7px;margin-top:10px}.f{border-top:1px solid #132f42;padding-top:7px}.f label{display:block;color:#58738a;font-size:6px;font-weight:900;letter-spacing:.8px;margin-bottom:3px}.f div{font-size:8px;line-height:1.45;overflow-wrap:anywhere;color:#d0dce4}.full{white-space:pre-wrap;margin-top:12px;padding:10px;border:1px solid #17364c;border-radius:8px;background:#050d15;color:#9db0bd;font-size:8px;line-height:1.65}.upload{margin-top:15px;padding:19px;text-align:center;border:1px dashed #315c78;border-radius:11px;background:#07131e}.upload input{max-width:100%;margin:10px auto;color:#91a8b9}.copy{display:flex;gap:7px;margin-top:9px}.copy input{flex:1;height:38px;border:1px solid #24465d;border-radius:7px;background:#06111a;color:#dbe7ef;padding:0 8px;font-size:8px}.users{display:grid;gap:9px;margin-top:17px}.urow{display:grid;grid-template-columns:1.1fr .9fr 1.3fr;gap:12px;padding:13px;border:1px solid #18384f;border-radius:11px;background:#07131e}.urow b{font-size:10px}.urow small{display:block;color:#668097;font-size:6px;margin-top:3px}.pill{display:inline-block;padding:4px 6px;border-radius:6px;font-size:6px;font-weight:900;margin-right:3px}.pill.o{background:#0e2e25;color:#83ddb0}.pill.x{background:#1b2127;color:#8193a0}.pill.a{background:#173345;color:#8fc9e9}.pill.p{background:#2c2013;color:#e0bd5a}.uform{display:grid;grid-template-columns:1fr 1fr auto;gap:6px;margin-top:8px}.uform input{height:34px;border:1px solid #24445b;background:#06111a;color:#e9f0f4;border-radius:7px;padding:0 7px;font-size:8px}.uform button{border:0;border-radius:7px;background:#d9b554;color:#080b0e;font-size:6px;font-weight:950;padding:0 10px}.empty{grid-column:1/-1;padding:40px;text-align:center;border:1px dashed #274d67;border-radius:12px;color:#6f8799;font-size:8px}.footer{text-align:center;border-top:1px solid #102a3d;color:#496275;font-size:7px;padding:17px}@media(max-width:1050px){.nav{gap:9px}.brand{min-width:230px}.hero{grid-template-columns:1fr}.wanted,.records,.modules{grid-template-columns:repeat(2,1fr)}.urow{grid-template-columns:1fr 1fr}}@media(max-width:700px){.top{flex-wrap:wrap}.brand{min-width:0;flex:1}.nav{order:3;width:100%;overflow:auto}.top-actions{margin-left:auto}.wrap{width:calc(100% - 18px);padding-top:12px}.hero,.wanted,.records,.modules,.quick{grid-template-columns:1fr}.hero h1{font-size:33px}.stats{grid-template-columns:1fr 1fr 1fr}.notice{align-items:stretch;flex-direction:column}.urow{grid-template-columns:1fr}.uform{grid-template-columns:1fr}.copy{flex-direction:column}}
'''

def shell(title,body,u=None,admin=False):
    nav='<nav class="nav"><a href="/">CENTRAL</a><a href="/procurados">PROCURADOS</a><a href="/fotos">FOTO → FIVE M</a><a href="/central">ÁREA RESTRITA</a>'+('<a href="/admin">USUÁRIOS</a>' if admin else '')+'</nav>'
    who='' if not u else '<div class="user"><i class="dot"></i><div><b>'+esc(u.get("qra"))+'</b><small>PASSAPORTE '+esc(u.get("passaporte"))+'</small></div></div><form method="post" action="/logout"><input type="hidden" name="csrf" value="'+esc(csrf(u))+'"><button class="logout">SAIR</button></form>'
    csp="default-src 'self';img-src 'self' data: https:;connect-src 'self';style-src 'self' 'unsafe-inline';script-src 'self' 'unsafe-inline';frame-ancestors 'none';base-uri 'self';form-action 'self';object-src 'none'"
    return '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="'+esc(csp)+'"><title>'+esc(title)+'</title><style>'+CSS+'</style></head><body><header class="top"><a class="brand" href="/"><img src="'+esc(LOGO)+'" alt="DICOR"><div><b>PCPT POLICIA MORADA - POLICIA FEDERAL</b><span>DICOR</span></div></a>'+nav+'<div class="top-actions">'+who+'</div></header><main class="wrap">'+body+'</main><footer class="footer">DICOR • CENTRAL DE INTELIGÊNCIA | PCPT POLICIA MORADA - POLICIA FEDERAL</footer><script>setInterval(function(){fetch("/api/heartbeat",{method:"POST",credentials:"same-origin",cache:"no-store"}).catch(function(){});},60000);function cp(v,b){if(navigator.clipboard){navigator.clipboard.writeText(v).then(function(){var x=b.innerText;b.innerText="COPIADO";setTimeout(function(){b.innerText=x;},1000);});}}</script></body></html>'

def login(err=''):
    body=f'<div class="login"><section class="panel"><img class="logo" src="{esc(LOGO)}" alt="DICOR"><div class="k">PCPT POLICIA MORADA - POLICIA FEDERAL</div><h1>ACESSO À CENTRAL</h1><p class="sub">Informe QRA e passaporte para entrar no ambiente DICOR.</p>{f"<div class=\\\"status pend\\\">{esc(err)}</div>" if err else ""}<form class="form" method="post" action="/cadastro-operador"><div class="field"><label>QRA</label><input name="qra" maxlength="45" required placeholder="Digite seu QRA"></div><div class="field"><label>PASSAPORTE</label><input name="passaporte" maxlength="20" required placeholder="Digite seu passaporte"></div><button class="btn gold" type="submit">ENTRAR NA CENTRAL →</button></form></section></div>'
    return shell("DICOR • Acesso",body)

def home(u):
    cards=[]
    for r in list(C.get("procurados",[]) or [])[:3]:
        img=f'<img src="{esc(r.get("image"))}" alt="Foto" loading="lazy">' if r.get("image") else '<span class="muted">SEM FOTO</span>'; fs=r.get("fields") or {}
        cards.append(f'<article class="card"><div class="photo">{img}<span class="tag">PROCURADO ATIVO</span></div><div class="body"><h3>{esc(r.get("name") or "Indivíduo não identificado")}</h3><p>{esc((r.get("full_text") or "").splitlines()[0][:180])}</p><div class="line"><span>REGISTRO</span><b>{esc(r.get("number") or "S/N")}</b></div><div class="line"><span>CRIMES</span><b>{esc(fs.get("Crimes","Não informado"))}</b></div></div></article>')
    auth=bool(u.get("authorized")); pend=bool(u.get("access_request_pending"));
    access='<a class="btn gold" href="/central">ABRIR TODA A CENTRAL →</a>' if auth else ('<a class="btn lock" href="/central">SOLICITAÇÃO EM ANÁLISE</a>' if pend else f'<form method="post" action="/abrir-central"><input type="hidden" name="csrf" value="{esc(csrf(u))}"><button class="btn gold">ABRIR TODA A CENTRAL →</button></form>')
    st='<div class="status ok">Acesso operacional liberado.</div>' if auth else ('<div class="status pend">Pedido enviado. Aguarde aprovação no canal interno.</div>' if pend else '<div class="status">Boletins, Perícias e Operações exigem aprovação.</div>')
    bo=len(C.get("boletins",[]) or []) if auth else "—"; pe=len(C.get("pericias",[]) or []) if auth else "—"
    body=f'<section class="hero"><article class="panel hero copy"><div class="k">SISTEMA INTEGRADO DE INTELIGÊNCIA • DICOR</div><h1>CENTRAL<br><span>DE INTELIGÊNCIA</span></h1><p class="sub">Consulta rápida, Procurados em destaque e ferramentas operacionais. Mensagens automáticas do Discord são filtradas para manter a Central limpa.</p><div class="stats"><div class="stat"><small>PROCURADOS</small><b>{len(C.get("procurados",[]) or [])}</b></div><div class="stat gold"><small>BOLETINS</small><b>{bo}</b></div><div class="stat"><small>PERÍCIAS</small><b>{pe}</b></div></div><div class="actions"><a class="btn" href="/procurados">VER PROCURADOS</a><a class="btn" href="/fotos">GERAR LINK FIVE M</a></div></article><article class="panel mark"><img src="{esc(LOGO)}" alt="Brasão DICOR"></article></section><div class="head"><div><span>MONITORAMENTO</span><h2>PROCURADOS EM DESTAQUE</h2></div><a href="/procurados">ABRIR TODOS →</a></div><section class="cards">{"".join(cards) or '<div class=\\\"empty\\\">Nenhum Procurado ativo.</div>'}</section><section class="notice"><div><strong>ACESSO OPERACIONAL</strong><small>Boletins • Perícias • Operações</small>{st}</div><div>{access}</div></section><section class="quick"><a class="qcard" href="/fotos"><h3>FOTO → FIVE M</h3><p>Envie uma imagem e receba um link direto pronto para uso no FiveM.</p></a><a class="qcard" href="/procurados"><h3>CONSULTA DE PROCURADOS</h3><p>Três destaques na home e a lista completa na consulta.</p></a></section>'
    return shell("DICOR • Central",body,u,is_admin(u))

def restricted(u):
    if not u.get("authorized"):
        body=f'<section class="panel hero copy"><div class="k">DICOR • CONTROLE DE ACESSO</div><h1>ÁREA <span>RESTRITA</span></h1><p class="sub">Boletins, Perícias e Operações só ficam disponíveis após aprovação.</p>{"<div class=\\\"status pend\\\">Solicitação enviada. Aguarde aprovação.</div>" if u.get("access_request_pending") else "<div class=\\\"status\\\">Use o botão da Central para solicitar autorização.</div>"}<div class="actions"><a class="btn" href="/">← VOLTAR</a></div></section>'; return shell("DICOR • Restrito",body,u,is_admin(u))
    ms=[("BOLETINS","Registros completos recebidos pela Central.","/boletins"),("PERÍCIAS","Registros periciais e atendimentos.","/pericias"),("OPERAÇÕES","Registros operacionais disponíveis.","/operacoes"),("PROCURADOS","Catálogo completo.","/procurados"),("FOTO → FIVE M","Enviar imagem e copiar link.","/fotos")]
    body=f'<section class="panel"><div class="k">DICOR • ACESSO OPERACIONAL</div><h1>TODA A CENTRAL</h1><p class="sub">Usuário autorizado: {esc(u.get("qra"))} • Passaporte {esc(u.get("passaporte"))}</p><section class="modules">{"".join(f"<article class=\\\"module\\\"><h3>{esc(t)}</h3><p>{esc(d)}</p><a class=\\\"btn\\\" href=\\\"{esc(h)}\\\">ABRIR MÓDULO →</a></article>" for t,d,h in ms)}</section></section>'; return shell("DICOR • Área restrita",body,u,is_admin(u))

def record_card(r,href):
    fs=r.get("fields") or {}; vals=list(fs.items())[:6]; return f'<article class="record"><div class="rhead"><b>{esc(r.get("name") or r.get("subject") or "Registro")}</b><span class="badge">{esc(r.get("source"))}</span></div><div class="meta">Nº {esc(r.get("number") or "S/N")} • {esc(r.get("date"))}</div><div class="fields">{"".join(f"<div class=\\\"f\\\"><label>{esc(a)}</label><div>{esc(b)}</div></div>" for a,b in vals)}</div><div class="actions"><a class="btn" href="{esc(href)}">ABRIR TUDO →</a></div></article>'
def list_page(u,kind,title,desc):
    rs=list(C.get(kind,[]) or []); cards=[]
    for r in rs: cards.append(record_card(r,'/registro/'+kind+'/'+quote(str(r.get('id')))))
    body=f'<section class="panel"><div class="k">DICOR • {esc(title).upper()}</div><h1>{esc(title)}</h1><p class="sub">{esc(desc)}</p><div class="head"><div><span>REGISTROS</span><h2>{len(rs)} ITEM(NS)</h2></div><a href="/central">← ÁREA RESTRITA</a></div><section class="records">'+(''.join(cards) or '<div class="empty">Nenhum registro disponível.</div>')+'</section></section>'
    return shell('DICOR • '+title,body,u,is_admin(u))
def detail(u,kind,rid):
    r=next((x for x in C.get(kind,[]) if str(x.get("id"))==rid),None)
    if kind!="procurados" and not u.get("authorized"):return restricted(u)
    if not r:return shell("DICOR • Registro",'<section class="panel"><h1>REGISTRO NÃO ENCONTRADO</h1></section>',u,is_admin(u))
    fs=r.get("fields") or {}; fields=''.join(f'<div class="f"><label>{esc(a)}</label><div>{esc(b)}</div></div>' for a,b in fs.items()); im=f'<img src="{esc(r.get("image"))}" style="max-width:100%;max-height:320px;border-radius:9px;margin-top:14px">' if r.get("image") else ''; org=f'<a class="btn" href="{esc(r.get("url"))}" target="_blank" rel="noopener">ABRIR ORIGEM →</a>' if r.get("url") else ''
    body=f'<section class="panel"><div class="k">DICOR • REGISTRO COMPLETO</div><h1>{esc(r.get("name") or r.get("subject") or "Registro")}</h1><p class="sub">{esc(kind.upper())} • {esc(r.get("source"))} • Nº {esc(r.get("number") or "S/N")}</p>{im}<div class="fields" style="margin-top:18px">{fields}</div><div class="full">{esc(r.get("full_text"))}</div><div class="actions"><a class="btn" href="/{esc(kind)}">← VOLTAR</a>{org}</div></section>'; return shell("DICOR • Registro",body,u,is_admin(u))
def photos(u,result="",error=""):
    res=f'<section class="panel" style="margin-top:14px"><div class="k">FOTO ENVIADA</div><h2>LINK DIRETO PARA FIVE M</h2><p class="sub">Copie a URL abaixo.</p><div class="copy"><input id="five" readonly value="{esc(result)}"><button class="btn gold" onclick="cp(document.getElementById(\'five\').value,this)">COPIAR</button></div></section>' if result else ''
    body=f'<section class="panel"><div class="k">DICOR • ARQUIVO VISUAL</div><h1>FOTO → FIVE M</h1><p class="sub">PNG, JPG, WEBP ou GIF de até 10 MB.</p>{f"<div class=\\\"status pend\\\">{esc(error)}</div>" if error else ""}<form class="upload" method="post" action="/fotos/upload" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{esc(csrf(u))}"><input type="file" name="foto" accept="image/png,image/jpeg,image/webp,image/gif" required><button class="btn gold">ENVIAR FOTO E GERAR LINK →</button></form></section>{res}'; return shell("DICOR • Foto",body,u,is_admin(u))
def admin_page(u):
    rs=sorted(users().values(),key=lambda x:str(x.get("updated_at","")),reverse=True); items=[]
    for r in rs:
        st='<span class="pill o">ONLINE</span>' if online(r) else '<span class="pill x">OFFLINE</span>'; au='<span class="pill a">AUTORIZADO</span>' if r.get("authorized") else '<span class="pill x">BLOQUEADO</span>'; pe='<span class="pill p">PENDENTE</span>' if r.get("access_request_pending") else ''; kk=k(r.get("qra"),r.get("passaporte"))
        items.append(f'<article class="urow"><div><b>{esc(r.get("nome") or r.get("qra"))}</b><small>QRA {esc(r.get("qra"))} • PASSAPORTE {esc(r.get("passaporte"))}</small></div><div><small>CARGO</small><div>{esc(r.get("cargo") or "Não definido")}</div><div style="margin-top:5px">{st}{au}{pe}</div></div><div><small>ÚLTIMO ACESSO</small><div>{esc(r.get("last_seen") or "Nunca")}</div><form class="uform" method="post" action="/admin/user"><input type="hidden" name="csrf" value="{esc(csrf(u))}"><input type="hidden" name="key" value="{esc(kk)}"><input name="nome" value="{esc(r.get("nome") or "")}" maxlength="100" placeholder="Nome"><input name="cargo" value="{esc(r.get("cargo") or "")}" maxlength="100" placeholder="Cargo"><button>SALVAR</button></form></div></article>')
    body=f'<section class="panel"><div class="k">DICOR • ADMINISTRAÇÃO</div><h1>USUÁRIOS DA CENTRAL</h1><p class="sub">Todos os cadastros, presença, autorização e cargo definido pelo administrador.</p><div class="stats"><div class="stat"><small>TODOS</small><b>{len(rs)}</b></div><div class="stat"><small>ONLINE</small><b>{sum(1 for x in rs if online(x))}</b></div><div class="stat gold"><small>AUTORIZADOS</small><b>{sum(1 for x in rs if x.get("authorized"))}</b></div></div><section class="users">{"".join(items) or "<div class=\\\"empty\\\">Nenhum usuário cadastrado.</div>"}</section></section>'; return shell("DICOR • Usuários",body,u,True)

@web.middleware
async def security(req,handler):
    try:r=await handler(req)
    except web.HTTPException as e:r=e
    r.headers["X-Content-Type-Options"]="nosniff";r.headers["X-Frame-Options"]="DENY";r.headers["Referrer-Policy"]="no-referrer";r.headers["Permissions-Policy"]="camera=(),microphone=(),geolocation=()";r.headers["Cache-Control"]="no-store";return r
async def health(req):return web.json_response({"ok":True,"central":"v700","discord_ready":bool(CLIENT and getattr(CLIENT,"is_ready",lambda:False)()),"records":{x:len(C.get(x,[]) or []) for x in ("procurados","boletins","pericias","operacoes")}})
async def home_route(req):
    u=current(req); return web.Response(text=login() if not u else home(touch(u)),content_type="text/html")
async def login_route(req):
    if req.method=="GET":return web.Response(text=login(),content_type="text/html")
    p=await req.post(); q=clean(p.get("qra"))[:45]; pas=clean(p.get("passaporte"))[:20]
    if not q or not pas:return web.Response(text=login("Informe QRA e passaporte."),status=400,content_type="text/html")
    kk=k(q,pas); x=users(); u=x.get(kk)
    if not isinstance(u,dict):u={"qra":q,"passaporte":pas,"nome":q,"cargo":"","authorized":False,"access_request_pending":False,"approval_token":"","is_admin":bool(ADMIN_QRA and ADMIN_PASS and q.casefold()==ADMIN_QRA and pas.casefold()==ADMIN_PASS),"created_at":iso(),"updated_at":iso(),"last_seen":now()};x[kk]=u;save_users(x);audit("CADASTRO_NOVO_USUARIO",u)
    else:u["last_seen"]=now();u["updated_at"]=iso();x[kk]=u;save_users(x);audit("LOGIN_CENTRAL",u)
    r=web.HTTPFound("/"); r.set_cookie(COOKIE,session(kk),max_age=MAX_AGE,httponly=True,samesite="Lax",secure=req.secure or str(req.headers.get("X-Forwarded-Proto","")).split(",",1)[0].strip().casefold()=="https",path="/"); return r
async def open_route(req):
    u=current(req)
    if not u:return web.HTTPFound("/cadastro-operador")
    p=await req.post()
    if not hmac.compare_digest(str(p.get("csrf","")),csrf(u)):raise web.HTTPForbidden(text="Token de segurança inválido.")
    if u.get("authorized"):return web.HTTPFound("/central")
    if not u.get("access_request_pending") and not await request_access(touch(u)):raise web.HTTPBadGateway(text="Não foi possível enviar o pedido agora.")
    return web.HTTPFound("/")
async def central_route(req):
    u=current(req)
    if not u:return web.HTTPFound("/cadastro-operador")
    return web.Response(text=restricted(touch(u)),status=200 if u.get("authorized") else 403,content_type="text/html")
async def module_route(req,kind,title,desc):
    u=current(req)
    if not u:return web.HTTPFound("/cadastro-operador")
    u=touch(u)
    if not u.get("authorized"):return web.Response(text=restricted(u),status=403,content_type="text/html")
    return web.Response(text=list_page(u,kind,title,desc),content_type="text/html")
async def procurados_route(req):
    u=current(req)
    if not u:return web.HTTPFound("/cadastro-operador")
    u=touch(u); q=clean(req.query.get("q","")).casefold(); rs=list(C.get("procurados",[]) or [])
    if q:rs=[x for x in rs if q in json.dumps(x,ensure_ascii=False).casefold()]
    cards=''.join(record_card(x,f'/registro/procurados/{quote(str(x.get("id")))}') for x in rs) or '<div class="empty">Nenhum Procurado encontrado.</div>'; body=f'<section class="panel"><div class="k">DICOR • BANCO DE PROCURADOS</div><h1>PROCURADOS</h1><p class="sub">Consulta limpa dos registros ativos.</p><form class="actions" method="get" action="/procurados"><div class="field" style="flex:1"><input name="q" value="{esc(req.query.get("q", ""))}" placeholder="Nome, RG ou crime..."></div><button class="btn gold">PESQUISAR</button></form><section class="records">{cards}</section></section>'; return web.Response(text=shell("DICOR • Procurados",body,u,is_admin(u)),content_type="text/html")
async def upload_route(req):
    u=current(req)
    if not u:return web.HTTPFound("/cadastro-operador")
    rd=await req.multipart(); token=""; data=b""; filename="foto.png"
    while True:
        part=await rd.next()
        if part is None:break
        if part.name=="csrf":token=(await part.text())[:200]
        elif part.name=="foto":filename=Path(part.filename or "foto.png").name; data=await part.read(decode=False)
    if not hmac.compare_digest(token,csrf(u)):raise web.HTTPForbidden(text="Token de segurança inválido.")
    ext=Path(filename).suffix.lower(); valid=(ext==".png" and data.startswith(b"\x89PNG\r\n\x1a\n")) or (ext in {".jpg",".jpeg"} and data.startswith(b"\xff\xd8\xff")) or (ext==".gif" and data.startswith((b"GIF87a",b"GIF89a"))) or (ext==".webp" and len(data)>=12 and data[:4]==b"RIFF" and data[8:12]==b"WEBP")
    if not data or len(data)>MAX_IMAGE:return web.Response(text=photos(u,error="A imagem deve ter até 10 MB."),status=413,content_type="text/html")
    if not valid:return web.Response(text=photos(u,error="Arquivo de imagem inválido."),status=400,content_type="text/html")
    try:
        import aiohttp; safe=re.sub(r"[^A-Za-z0-9._-]+","_",filename)[:120]; f=aiohttp.FormData(); f.add_field("file",data,filename=safe,content_type=mimetypes.guess_type(safe)[0] or "application/octet-stream");f.add_field("filename",safe);f.add_field("path","dicor-central");f.add_field("retentionExempt","true")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
            async with s.post("https://api.fivemanage.com/api/v3/file",headers={"Authorization":str(os.getenv("FIVEMANAGE_API_KEY","")).strip()},data=f) as rr:
                text=await rr.text(); payload=json.loads(text) if rr.status<500 else {}; obj=payload.get("data") if isinstance(payload,dict) else {}; url=str((obj or {}).get("url") or (obj or {}).get("originalUrl") or "").strip()
                if not 200<=rr.status<300 or not url:raise RuntimeError()
        audit("UPLOAD_FIVEMANAGE",u,filename); return web.Response(text=photos(u,result=url),content_type="text/html")
    except Exception as e:print(f"⚠️ [CENTRAL FOTO] {type(e).__name__}",flush=True);return web.Response(text=photos(u,error="Não foi possível gerar o link agora."),status=502,content_type="text/html")
async def admin_route(req):
    u=current(req)
    if not u or not is_admin(u):raise web.HTTPForbidden(text="Acesso administrativo restrito.")
    return web.Response(text=admin_page(touch(u)),content_type="text/html")
async def admin_save(req):
    u=current(req)
    if not u or not is_admin(u):raise web.HTTPForbidden(text="Acesso administrativo restrito.")
    p=await req.post()
    if not hmac.compare_digest(str(p.get("csrf","")),csrf(u)):raise web.HTTPForbidden(text="Token de segurança inválido.")
    x=users(); z=x.get(str(p.get("key","")))
    if not isinstance(z,dict):raise web.HTTPNotFound(text="Usuário não encontrado.")
    z["nome"]=clean(p.get("nome", ""))[:100] or z.get("qra","");z["cargo"]=clean(p.get("cargo", ""))[:100];z["updated_at"]=iso();x[str(p.get("key"))]=z;save_users(x);audit("ATUALIZOU_USUARIO",u,str(p.get("key")));return web.HTTPFound("/admin")
async def heartbeat(req):
    u=current(req)
    if not u:return web.json_response({"ok":False},status=401)
    touch(u);return web.json_response({"ok":True})
async def logout(req):
    u=current(req);p=await req.post()
    if u and not hmac.compare_digest(str(p.get("csrf","")),csrf(u)):raise web.HTTPForbidden(text="Token de segurança inválido.")
    if u:audit("LOGOUT",u)
    r=web.HTTPFound("/cadastro-operador");r.del_cookie(COOKIE,path="/");return r

class CentralV700:
    def __init__(self,client):self.client=client;self.runner=None
    async def start(self):
        global CLIENT,STARTED,TASK,VIEW
        CLIENT=self.client
        if discord and not VIEW:
            try:self.client.add_view(ApprovalView());VIEW=True
            except Exception:pass
        if STARTED:return self
        app=web.Application(client_max_size=12*1024*1024,middlewares=[security]); app.router.add_get("/health",health);app.router.add_get("/",home_route);app.router.add_get("/cadastro-operador",login_route);app.router.add_post("/cadastro-operador",login_route);app.router.add_post("/abrir-central",open_route);app.router.add_get("/central",central_route);app.router.add_get("/procurados",procurados_route);app.router.add_get("/boletins",lambda r:module_route(r,"boletins","Boletins","Registros completos da fonte configurada."));app.router.add_get("/pericias",lambda r:module_route(r,"pericias","Perícias","Registros completos de perícias."));app.router.add_get("/operacoes",lambda r:module_route(r,"operacoes","Operações","Registros operacionais disponíveis."));app.router.add_get("/registro/{kind}/{rid}",record_handler);app.router.add_get("/fotos",fotos_handler);app.router.add_post("/fotos/upload",upload_route);app.router.add_get("/admin",admin_route);app.router.add_post("/admin/user",admin_save);app.router.add_post("/api/heartbeat",heartbeat);app.router.add_post("/logout",logout)
        self.runner=web.AppRunner(app,access_log=None);await self.runner.setup();await web.TCPSite(self.runner,"0.0.0.0",PORT).start();STARTED=True
        if TASK is None or TASK.done():TASK=asyncio.create_task(loop(),name="dicor-central-v700")
        print(f"✅ [CENTRAL V700] ativa na porta {PORT} | refresh={REFRESH}s",flush=True);return self
async def record_handler(req):
    u=current(req)
    if not u:return web.HTTPFound("/cadastro-operador")
    return web.Response(text=detail(touch(u),str(req.match_info.get("kind")),str(req.match_info.get("rid"))),content_type="text/html")
async def fotos_handler(req):
    u=current(req)
    if not u:return web.HTTPFound("/cadastro-operador")
    return web.Response(text=photos(touch(u)),content_type="text/html")
def install(bot_module):
    c=getattr(bot_module,"bot",None)
    if c is None:raise RuntimeError("cliente Discord não encontrado")
    return CentralV700(c)
