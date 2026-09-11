# -*- coding: utf-8 -*-
"""DICOR Central V610 — dashboard rápido, live Discord, somente leitura."""
from __future__ import annotations
import asyncio,base64,hashlib,hmac,html,os,re,time
from datetime import timezone
from typing import Any
import discord
from aiohttp import web

BO_TARGET_ID=int(os.getenv("DICOR_BO_TARGET_ID","1525762770253910136"))
PERICIA_CHANNEL_ID=int(os.getenv("DICOR_PERICIA_SOURCE_ID","1490200524367200297"))
PROCURADOS_CHANNEL_ID=int(os.getenv("DICOR_PROCURADOS_CHANNEL_ID","1490200533980545097"))
PORT=int(os.getenv("PORT","8080"))
COOKIE="dicor_operador_v610"
SECRET=os.getenv("CENTRAL_DICOR_COOKIE_SECRET",os.getenv("DICOR_COOKIE_SECRET","dicor-central-v610"))
LOGO_URL="https://media.discordapp.net/attachments/1426821172237963375/1547778833866817596/image.png?ex=6aa4a8de&is=6aa3575e&hm=95ab0f8951a7c48c3c2aff35c5cfdec8cef0af8add90348445dc7093b7d841d3&=&format=webp&quality=lossless"

def esc(v:Any)->str:return html.escape(str(v or ""),quote=True)
def clean(v:Any)->str:return " ".join(str(v or "").split())
def msg_text(m:discord.Message)->str:
    p=[m.content or ""]
    for e in m.embeds or []:
        p += [e.title or "",e.description or ""]
        p += [f"{f.name}: {f.value}" for f in e.fields or []]
    return clean(" ".join(x for x in p if x))
def closed(name,text):
    s=clean(f"{name} {text}").casefold()
    return any(x in s for x in ("concluído","concluido","finalizado","encerrado","fechado","cancelado"))
def num(text):
    for p in (r"(?:N[º°O.]?|NO|#)\s*(\d{1,8})",r"\b(\d{4,8})\b"):
        m=re.search(p,text or "",re.I)
        if m:return f"{int(m.group(1)):04d}"
    return "S/N"
def cookie(q,p):
    payload=f"{clean(q)[:45]}|{clean(p)[:12]}|{int(time.time())}"
    raw=base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig=hmac.new(SECRET.encode(),payload.encode(),hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"
def operator(req):
    token=req.cookies.get(COOKIE,"")
    if "." not in token:return None
    try:
        raw,sig=token.rsplit(".",1); payload=base64.urlsafe_b64decode(raw+"="*(-len(raw)%4)).decode()
        if not hmac.compare_digest(sig,hmac.new(SECRET.encode(),payload.encode(),hashlib.sha256).hexdigest()):return None
        q,p,issued=payload.split("|",2)
        return (q,p) if time.time()-int(issued)<=30*86400 else None
    except Exception:return None

LOGIN_CSS="""*{box-sizing:border-box}body{margin:0;min-height:100vh;background:#050606;color:#f4f0e4;font-family:Inter,Arial;display:grid;place-items:center}body:before{content:"";position:fixed;inset:0;background:radial-gradient(circle at 50% 0,#6c501b2b,transparent 42%);pointer-events:none}.login{position:relative;width:min(470px,calc(100% - 34px));padding:34px;border:1px solid #6b5524;border-radius:24px;background:linear-gradient(145deg,#11130fef,#080a09f5);box-shadow:0 35px 100px #000d}.logo{width:100px;height:100px;object-fit:contain;display:block;margin:0 auto 14px;filter:drop-shadow(0 0 18px #d7a93d2a)}.k{text-align:center;color:#d7a93d;font-size:10px;letter-spacing:3px;font-weight:800}.login h1{text-align:center;font-size:27px;margin:7px 0}.login p{text-align:center;color:#8e8d83;font-size:13px}label{display:block;color:#cfc7ae;font-size:11px;letter-spacing:1.4px;margin:18px 0 7px}input{width:100%;padding:14px;border-radius:12px;border:1px solid #34362e;background:#050706;color:#fff;font-size:15px;outline:none}input:focus{border-color:#d7a93d}.login button{width:100%;margin-top:22px;padding:14px;border:0;border-radius:12px;background:linear-gradient(135deg,#f1d078,#d7a93d);color:#111;font-weight:900;cursor:pointer}.note{margin-top:15px;padding:10px 12px;border-left:2px solid #d7a93d;background:#d7a93d0d;color:#777;font-size:11px}.err{padding:10px;border-radius:10px;background:#401919;color:#ffcaca;font-size:12px}"""
def login_page(next_url="/",error=""):
    e=f'<div class="err">{esc(error)}</div>' if error else ""
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DICOR • Identificação</title><style>{LOGIN_CSS}</style></head><body><form class="login" method="post" action="/cadastro-operador"><img class="logo" src="{LOGO_URL}" alt="DICOR"><div class="k">POLÍCIA FEDERAL • DICOR</div><h1>CENTRAL DE INTELIGÊNCIA</h1><p>Identificação operacional para acesso ao painel interno.</p>{e}<input type="hidden" name="next" value="{esc(next_url)}"><label>QRA OPERACIONAL</label><input name="qra" maxlength="45" placeholder="Digite seu QRA" required><label>PASSAPORTE</label><input name="passaporte" maxlength="12" inputmode="numeric" placeholder="Digite seu passaporte" required><div class="note">Sessão vinculada ao operador informado.</div><button>ACESSAR CENTRAL</button></form></body></html>"""

async def channel(client,cid):
    c=client.get_channel(cid)
    if c:return c
    try:return await client.fetch_channel(cid)
    except Exception:return None
async def threads(parent):
    if not isinstance(parent,discord.TextChannel):return []
    out=list(getattr(parent,"threads",[]) or []); seen={t.id for t in out}
    try:
        async for t in parent.archived_threads(limit=100):
            if t.id not in seen:out.append(t);seen.add(t.id)
    except Exception:pass
    return out
async def live_threads(client,cid,kind):
    parent=await channel(client,cid)
    if not parent:return []
    out=[]
    for t in await threads(parent):
        if t.archived or t.locked:continue
        try:msgs=[m async for m in t.history(limit=8,oldest_first=True)]
        except Exception:continue
        text=" ".join(msg_text(m) for m in msgs)
        if closed(t.name,text):continue
        agent="Aguardando responsável" if kind=="bo" else "Aguardando agente"
        for m in msgs:
            x=re.search(r"(?:Responsável|Responsavel|Agente)\s*:\s*(?:<@!?(\d+)>|([^|\n]+))",msg_text(m),re.I)
            if x:agent=x.group(1) or clean(x.group(2));break
        dt=t.created_at;gid=getattr(getattr(t,"guild",None),"id",0)
        out.append({"number":num(t.name),"name":clean(t.name),"agent":agent,"created":dt,"url":f"https://discord.com/channels/{gid}/{t.id}","kind":kind})
    out.sort(key=lambda x:x["created"],reverse=True);return out
async def live_procurados(client):
    ids=[PROCURADOS_CHANNEL_ID]
    for g in getattr(client,"guilds",[]):
        for c in getattr(g,"text_channels",[]):
            n=clean(getattr(c,"name","")).casefold()
            if any(k in n for k in ("procurad","foragid","mandado")) and c.id not in ids:ids.append(c.id)
    out=[]
    for cid in ids:
        c=await channel(client,cid)
        if not c:continue
        try:
            async for m in c.history(limit=80):
                text=msg_text(m)
                if text and not closed("",text):out.append({"number":num(text),"name":text[:150],"agent":str(m.author),"created":m.created_at,"url":m.jump_url,"kind":"proc"})
        except Exception:pass
    out.sort(key=lambda x:x["created"],reverse=True);return out[:40]
def serial(rows):
    out=[]
    for r in rows:
        d=r["created"]
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        out.append({**r,"created":d.isoformat()})
    return out

CSS="""\
:root{--g:#d7a93d;--g2:#f4d477;--bg:#050707;--line:#26302c;--text:#edf0e9;--muted:#7f8982;--green:#42d58a;--red:#ff4d55;--purple:#a879ff}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 50% -10%,#6a4e171c,transparent 34%),linear-gradient(180deg,#050706,#070a09 55%,#050606);color:var(--text);font-family:Inter,Segoe UI,Arial;min-height:100vh}a{color:inherit;text-decoration:none}.shell{display:grid;grid-template-columns:240px 1fr;min-height:100vh}.side{position:sticky;top:0;height:100vh;border-right:1px solid #1d2522;background:linear-gradient(180deg,#080b0a,#060807);padding:18px 13px;display:flex;flex-direction:column}.brand{display:flex;align-items:center;gap:9px;padding:3px 7px 18px;border-bottom:1px solid #1c2421}.brand img{width:54px;height:54px;object-fit:contain;filter:drop-shadow(0 0 12px #d7a93d20)}.brand b{display:block;letter-spacing:2px}.brand span{display:block;color:var(--g);font-size:9px;letter-spacing:2px}.nav{padding-top:16px;display:grid;gap:5px}.nav a{display:flex;gap:11px;align-items:center;padding:12px;border:1px solid transparent;border-radius:10px;color:#9ba49e;font-size:12px}.nav a:hover,.nav a.active{color:#f5df9c;border-color:#58481f;background:#d7a93d18}.nav i{font-style:normal;width:19px;text-align:center;font-size:15px}.bottom{margin-top:auto;padding:11px;border:1px solid #202823;border-radius:11px;background:#0a0e0c}.online{color:#8d978f;font-size:10px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--green);margin-right:6px;box-shadow:0 0 12px #42d58a77}.op{margin-top:7px;color:var(--g);font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.main{min-width:0;padding:20px 26px 40px}.top{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1d2522;padding-bottom:16px;margin-bottom:18px}.title{display:flex;align-items:center;gap:11px}.title img{width:47px;height:47px;object-fit:contain}.title b{font-size:15px;letter-spacing:1.5px}.title span{display:block;color:#77817a;font-size:9px;letter-spacing:1.4px;margin-top:4px}.clock{color:#7e8881;font-size:9px;text-align:right}.hero{position:relative;overflow:hidden;border:1px solid #5a4820;border-radius:15px;padding:25px 27px;background:linear-gradient(110deg,#11150f,#0a0e0c 58%,#0b0d0c);box-shadow:inset 0 -1px #d7a93d55}.heroLogo{position:absolute;right:35px;top:4px;width:165px;height:150px;object-fit:contain;opacity:.82;filter:drop-shadow(0 0 25px #d7a93d22)}.eyebrow{color:var(--g);font-size:10px;letter-spacing:2.5px;font-weight:800}.hero h1{font-size:31px;margin:8px 0 5px;letter-spacing:1px}.hero p{margin:0;color:#89928c;font-size:12px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin:15px 0}.stat{border:1px solid var(--line);border-radius:11px;background:#0b100e;padding:14px}.stat .lab{color:#79847d;font-size:9px;letter-spacing:1.2px}.stat .r{display:flex;justify-content:space-between;align-items:end;margin-top:7px}.stat strong{font-size:28px}.stat em{font-style:normal;color:var(--green);font-size:8px}.layout{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(250px,.7fr);gap:14px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:14px}.panel{border:1px solid var(--line);border-radius:13px;background:linear-gradient(145deg,#0c1110,#080c0b);overflow:hidden}.ph{display:flex;justify-content:space-between;align-items:center;padding:13px 14px;border-bottom:1px solid #1d2522}.ph b{font-size:10px;letter-spacing:1.2px}.ph a{color:var(--g2);font-size:8px}.list{padding:3px 9px}.item{display:grid;grid-template-columns:7px 1fr auto;gap:10px;align-items:center;padding:11px 4px;border-bottom:1px solid #17201d}.item:last-child{border:0}.bar{width:3px;height:33px;border-radius:3px;background:var(--g)}.bar.red{background:var(--red)}.bar.purple{background:var(--purple)}.item h3{margin:0;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.item p{margin:4px 0 0;color:#68736c;font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.num{color:#d9c47c;font-size:8px}.right{display:grid;gap:14px;align-content:start}.q{display:flex;justify-content:space-between;padding:12px 14px;border-bottom:1px solid #18211e;color:#aeb6b0;font-size:10px}.q:last-child{border:0}.q span{color:var(--g2)}.mini{padding:13px}.mr{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid #18211e;color:#7d8880;font-size:9px}.mr:last-child{border:0}.mr b{color:#e4e8e1}.pagehead{display:flex;justify-content:space-between;align-items:end;margin:12px 0 16px}.pagehead h1{margin:0;font-size:23px}.pagehead p{margin:5px 0 0;color:#6f7972;font-size:10px}.tag{border:1px solid #59491f;color:#d9bf69;border-radius:20px;padding:4px 7px;font-size:8px}.cards{display:grid;grid-template-columns:repeat(2,1fr);gap:11px}.card{border:1px solid var(--line);border-radius:12px;background:#0b100e;padding:14px}.card h3{margin:10px 0;font-size:14px}.meta{display:flex;justify-content:space-between;gap:10px;border-top:1px solid #18211e;padding:8px 0;font-size:8px}.meta span{color:#68736c}.meta b{max-width:72%;text-align:right;overflow:hidden;text-overflow:ellipsis}.open{display:inline-block;margin-top:7px;color:#111;background:linear-gradient(135deg,var(--g2),var(--g));padding:8px 10px;border-radius:7px;font-size:8px;font-weight:900}.empty{padding:35px;text-align:center;color:#68736c;border:1px dashed #26302c;border-radius:12px;grid-column:1/-1}.footer{text-align:right;color:#4e5852;font-size:8px;padding-top:14px}@media(max-width:1050px){.shell{grid-template-columns:76px 1fr}.brand div,.nav span,.bottom .op{display:none}.brand{justify-content:center}.nav a{justify-content:center}.layout{grid-template-columns:1fr}.right{grid-template-columns:1fr 1fr}}@media(max-width:760px){.shell{display:block}.side{position:static;height:auto;padding:9px}.brand{border:0;padding:0}.brand div,.bottom{display:none}.nav{display:flex;overflow:auto;padding:7px 0}.nav a{white-space:nowrap}.nav span{display:inline}.main{padding:13px}.stats{grid-template-columns:1fr 1fr}.columns,.cards{grid-template-columns:1fr}.right{grid-template-columns:1fr}.heroLogo{display:none}}"""

class CentralV610:
    def __init__(self,bot):
        self.bot=bot;self.cache={"bo":[],"pe":[],"proc":[],"updated":0.0,"busy":False};self.runner=None;self.task=None;self.request=None
    async def refresh(self):
        if self.cache["busy"]:return
        self.cache["busy"]=True
        try:
            bo,pe,pr=await asyncio.gather(live_threads(self.bot,BO_TARGET_ID,"bo"),live_threads(self.bot,PERICIA_CHANNEL_ID,"pe"),live_procurados(self.bot),return_exceptions=True)
            if not isinstance(bo,Exception):self.cache["bo"]=bo
            if not isinstance(pe,Exception):self.cache["pe"]=pe
            if not isinstance(pr,Exception):self.cache["proc"]=pr
            self.cache["updated"]=time.time()
        finally:self.cache["busy"]=False
    async def loop(self):
        await self.refresh()
        while True:
            await asyncio.sleep(12);await self.refresh()
    def counts(self):
        b,p,e=len(self.cache["bo"]),len(self.cache["proc"]),len(self.cache["pe"]);return {"bo":b,"proc":p,"pe":e,"total":b+p+e}
    def shell(self,title,active,body):
        op=operator(self.request) or ("—","—")
        links=[("⌂","Dashboard","/"),("▤","Boletins","/boletins"),("◎","Procurados","/procurados"),("⚗","Perícias","/pericias"),("▦","Banco de Dados","/fichas"),("⌘","Árvore de Inteligência","/arvore")]
        nav="".join(f'<a class="{"active" if active==u else ""}" href="{u}"><i>{i}</i><span>{n}</span></a>' for i,n,u in links)
        return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} • DICOR</title><style>{CSS}</style></head><body><div class="shell"><aside class="side"><div class="brand"><img src="{LOGO_URL}" alt="DICOR"><div><b>DICOR</b><span>INTELIGÊNCIA</span></div></div><nav class="nav">{nav}</nav><div class="bottom"><div class="online"><span class="dot"></span>CENTRAL ONLINE</div><div class="op">QRA {esc(op[0])} • PASS {esc(op[1])}</div></div></aside><main class="main"><div class="top"><div class="title"><img src="{LOGO_URL}" alt=""><div><b>CENTRAL DE INTELIGÊNCIA</b><span>POLÍCIA FEDERAL • DICOR • CONSULTA OPERACIONAL</span></div></div><div class="clock">SISTEMA LIVE<br><span id="clock">--:--:--</span></div></div>{body}<div class="footer">DICOR • CENTRAL DE INTELIGÊNCIA • SOMENTE LEITURA</div></main></div><script>function t(){{document.getElementById('clock').textContent=new Date().toLocaleTimeString('pt-BR')}}t();setInterval(t,1000)</script></body></html>"""
    def item(self,r,k):
        label="PROCURADO" if k=="proc" else "PERÍCIA" if k=="pe" else "BOLETIM";bar="red" if k=="proc" else "purple" if k=="pe" else ""
        return f'<a class="item" href="{esc(r["url"])}" target="_blank"><span class="bar {bar}"></span><div><h3>{esc(r["name"][:78])}</h3><p>{label} • {esc(r["agent"])}</p></div><span class="num">#{esc(r["number"])}</span></a>'
    def cards(self,rows,k):
        if not rows:return '<div class="empty">Nenhum registro ativo encontrado no Discord.</div>'
        out=[]
        for r in rows:
            dt=r["created"]
            if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
            label="PROCURADO" if k=="proc" else "PERÍCIA" if k=="pe" else "BOLETIM"
            out.append(f'<article class="card"><span class="tag">{label}</span><h3>Nº {esc(r["number"])}</h3><div class="meta"><span>Registro</span><b>{esc(r["name"][:90])}</b></div><div class="meta"><span>Responsável</span><b>{esc(r["agent"])}</b></div><div class="meta"><span>Data</span><b>{dt.astimezone().strftime("%d/%m/%Y %H:%M")}</b></div><a class="open" href="{esc(r["url"])}" target="_blank">ABRIR NO DISCORD →</a></article>')
        return "".join(out)
    def dashboard(self):
        c=self.counts();bo=self.cache["bo"][:6];pr=self.cache["proc"][:5];pe=self.cache["pe"][:5]
        bi="".join(self.item(x,"bo") for x in bo) or '<div class="empty">Nenhum BO ativo.</div>';pi="".join(self.item(x,"proc") for x in pr) or '<div class="empty">Nenhum procurado ativo.</div>';ei="".join(self.item(x,"pe") for x in pe) or '<div class="empty">Nenhuma perícia pendente.</div>'
        return f"""<section class="hero"><div><div class="eyebrow">DICOR • OPERAÇÕES ESPECIAIS</div><h1>PAINEL OPERACIONAL</h1><p>Visão consolidada dos registros ativos, diretamente do Discord.</p></div><img class="heroLogo" src="{LOGO_URL}" alt="DICOR"></section><section class="stats"><a class="stat" href="/boletins"><div class="lab">BOLETINS ATIVOS</div><div class="r"><strong>{c["bo"]}</strong><em>LIVE</em></div></a><a class="stat" href="/procurados"><div class="lab">PROCURADOS ATIVOS</div><div class="r"><strong>{c["proc"]}</strong><em>LIVE</em></div></a><a class="stat" href="/pericias"><div class="lab">PERÍCIAS PENDENTES</div><div class="r"><strong>{c["pe"]}</strong><em>LIVE</em></div></a><div class="stat"><div class="lab">TOTAL DE REGISTROS</div><div class="r"><strong>{c["total"]}</strong><em>SYNC</em></div></div></section><div class="layout"><div class="columns"><section class="panel"><div class="ph"><b>▤ BOLETINS RECENTES</b><a href="/boletins">VER TODOS →</a></div><div class="list">{bi}</div></section><section class="panel"><div class="ph"><b>◎ PROCURADOS RECENTES</b><a href="/procurados">VER TODOS →</a></div><div class="list">{pi}</div></section><section class="panel"><div class="ph"><b>⚗ PERÍCIAS RECENTES</b><a href="/pericias">VER TODAS →</a></div><div class="list">{ei}</div></section><section class="panel"><div class="ph"><b>⌘ ÁRVORE DE INTELIGÊNCIA</b><a href="/arvore">ABRIR →</a></div><div class="mini"><div class="mr"><span>BOs ativos</span><b>{c["bo"]}</b></div><div class="mr"><span>Procurados</span><b>{c["proc"]}</b></div><div class="mr"><span>Perícias</span><b>{c["pe"]}</b></div></div></section></div><aside class="right"><section class="panel"><div class="ph"><b>⚡ ACESSO RÁPIDO</b></div><a class="q" href="/boletins">Consultar boletins <span>→</span></a><a class="q" href="/procurados">Consultar procurados <span>→</span></a><a class="q" href="/pericias">Consultar perícia <span>→</span></a><a class="q" href="/fichas">Banco de dados <span>→</span></a><a class="q" href="/arvore">Árvore de inteligência <span>→</span></a></section><section class="panel"><div class="ph"><b>◈ INFORMAÇÕES OPERACIONAIS</b></div><div class="mini"><div class="mr"><span>Fonte</span><b>DISCORD LIVE</b></div><div class="mr"><span>Atualização</span><b>12s</b></div><div class="mr"><span>Modo</span><b>SOMENTE LEITURA</b></div><div class="mr"><span>Operador</span><b>{esc(operator(self.request)[0] if operator(self.request) else "—")}</b></div></div></section></aside></div>"""
    async def auth(self,request,handler):
        if request.path in ("/health","/cadastro-operador") or request.path.startswith("/api/"):return await handler(request)
        if not operator(request):raise web.HTTPFound("/cadastro-operador?next="+(request.path or "/"))
        return await handler(request)
    async def index(self,request):
        self.request=request;return web.Response(text=self.shell("Dashboard","/",self.dashboard()),content_type="text/html")
    async def listing(self,request,k):
        self.request=request;label={"bo":"BOLETINS","pe":"PERÍCIAS","proc":"PROCURADOS"}[k];active={"bo":"/boletins","pe":"/pericias","proc":"/procurados"}[k]
        body=f'<div class="pagehead"><div><h1>{label}</h1><p>Registros ativos sincronizados diretamente do Discord.</p></div><div class="tag">{len(self.cache[k])} ATIVOS</div></div><div class="cards">{self.cards(self.cache[k],k)}</div>'
        return web.Response(text=self.shell(label,active,body),content_type="text/html")
    async def placeholder(self,request,title,active):
        self.request=request;c=self.counts();body=f'<div class="pagehead"><div><h1>{title}</h1><p>Módulo integrado ao painel DICOR.</p></div></div><section class="panel"><div class="mini"><div class="mr"><span>Boletins ativos</span><b>{c["bo"]}</b></div><div class="mr"><span>Procurados ativos</span><b>{c["proc"]}</b></div><div class="mr"><span>Perícias pendentes</span><b>{c["pe"]}</b></div></div></section>'
        return web.Response(text=self.shell(title,active,body),content_type="text/html")
    async def api(self,request):return web.json_response({"ok":True,"updated":self.cache["updated"],"counts":self.counts(),"bo":serial(self.cache["bo"][:20]),"pe":serial(self.cache["pe"][:20]),"proc":serial(self.cache["proc"][:20])})
    async def cadastro(self,request):
        if request.method=="GET":return web.Response(text=login_page(request.query.get("next","/")),content_type="text/html")
        d=await request.post();q=clean(d.get("qra",""));p=clean(d.get("passaporte",""))
        if not q or not p:return web.Response(text=login_page(d.get("next","/"),"Informe QRA e passaporte."),content_type="text/html",status=400)
        target=str(d.get("next","/"));target=target if target.startswith("/") else "/";r=web.Response(status=303,headers={"Location":target});r.set_cookie(COOKIE,cookie(q,p),max_age=30*86400,httponly=True,samesite="Lax",secure=False,path="/");return r
    async def start(self):
        if self.runner:return
        self.app=web.Application(middlewares=[self.auth])
        self.app.router.add_get("/health",lambda r:web.json_response({"ok":True,"service":"dicor-central-v610","cache_updated":self.cache["updated"]}))
        self.app.router.add_get("/cadastro-operador",self.cadastro);self.app.router.add_post("/cadastro-operador",self.cadastro);self.app.router.add_get("/",self.index);self.app.router.add_get("/boletins",lambda r:self.listing(r,"bo"));self.app.router.add_get("/procurados",lambda r:self.listing(r,"proc"));self.app.router.add_get("/pericias",lambda r:self.listing(r,"pe"));self.app.router.add_get("/fichas",lambda r:self.placeholder(r,"BANCO DE DADOS","/fichas"));self.app.router.add_get("/arvore",lambda r:self.placeholder(r,"ÁRVORE DE INTELIGÊNCIA","/arvore"));self.app.router.add_get("/api/data",self.api)
        self.runner=web.AppRunner(self.app);await self.runner.setup();await web.TCPSite(self.runner,"0.0.0.0",PORT).start();self.task=asyncio.create_task(self.loop());print(f"🌐 Central V610 online na porta {PORT}",flush=True)

def install(bot):
    c=CentralV610(bot.bot if hasattr(bot,"bot") else bot);bot.central_v610=c;return c
