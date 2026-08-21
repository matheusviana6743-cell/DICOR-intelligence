# -*- coding: utf-8 -*-
"""V163 — Central DICOR: visual PF, mídia real e acesso por nível."""
from __future__ import annotations
import asyncio, base64, hashlib, hmac, html, json, os, re, secrets, time
from pathlib import Path
from urllib.parse import quote

WANTED_CHANNEL = 1490200533980545097
IMG_EXTS = ('.png','.jpg','.jpeg','.webp','.gif')
COOKIE_STRATEGY = 'dicor_strategy_v163'
COOKIE_APPROVAL = 'dicor_approved_v163_'
COOKIE_TTL = 12 * 3600
REQUEST_TTL = 24 * 3600


def install(b):
    web, discord = b.web, b.discord
    data = Path(str(getattr(b, 'DATA_DIR', Path(__file__).parent/'data')))
    data.mkdir(parents=True, exist_ok=True)
    req_file = data/'central_web_access_requests.json'
    req_lock = asyncio.Lock()
    views, pericia_cache = set(), {'at':0.0,'items':[]}
    pericia_lock = asyncio.Lock()

    def env_i(n, d=0):
        try: return int(str(os.getenv(n,'') or d).strip())
        except Exception: return int(d or 0)
    def safe_next(v):
        s=str(v or '/').strip(); return s[:1200] if s.startswith('/') and not s.startswith('//') else '/'
    def module(path):
        p=str(path or '').lower()
        if 'pericia' in p: return 'pericias'
        if 'bolet' in p: return 'boletins'
        if 'arvore' in p: return 'arvore'
        if 'ficha' in p or 'banco' in p: return 'banco'
        return ''
    def label(m): return {'pericias':'Perícias','boletins':'Boletins','arvore':'Árvore de Inteligência','banco':'Banco de Dados'}.get(m,'Área restrita')
    def strategy_pass(): return str(os.getenv('CENTRAL_ESTRATEGICA_PASSWORD','') or os.getenv('CENTRAL_DICOR_PASSWORD','')).strip()
    def secret(): return str(os.getenv('CENTRAL_DICOR_COOKIE_SECRET','') or strategy_pass()).strip()
    def sign(kind, subject):
        sec=secret()
        if not sec: return ''
        raw=f'{kind}|{subject}|{int(time.time())+COOKIE_TTL}'.encode(); body=base64.urlsafe_b64encode(raw).decode().rstrip('=')
        sig=hmac.new(sec.encode(),body.encode(),hashlib.sha256).hexdigest(); return body+'.'+sig
    def verify(token, kind, subject=None):
        try:
            body,sig=str(token).rsplit('.',1); sec=secret()
            if not sec or not hmac.compare_digest(sig,hmac.new(sec.encode(),body.encode(),hashlib.sha256).hexdigest()): return False
            raw=base64.urlsafe_b64decode((body+'='*(-len(body)%4)).encode()).decode(); k,s,exp=raw.split('|',2)
            return k==kind and int(exp)>=int(time.time()) and (subject is None or s==subject)
        except Exception: return False
    def load_req():
        try:
            x=json.loads(req_file.read_text(encoding='utf-8')) if req_file.exists() else []
            if isinstance(x,dict): x=x.get('requests') or []
            return [r for r in x if isinstance(r,dict)] if isinstance(x,list) else []
        except Exception: return []
    def save_req(rows):
        tmp=req_file.with_suffix('.tmp'); tmp.write_text(json.dumps(rows[-500:],ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(tmp,req_file)
    def get_req(rid): return next((r for r in reversed(load_req()) if secrets.compare_digest(str(r.get('id') or ''),rid)),None)
    async def update_req(rid,**changes):
        async with req_lock:
            rows=load_req(); found=None
            for r in rows:
                if secrets.compare_digest(str(r.get('id') or ''),rid): r.update(changes); found=r; break
            if found: save_req(rows)
            return found
    def approver(): return env_i('CENTRAL_APROVADOR_USER_ID') or int(getattr(b,'INSPETOR_BAIANO_USER_ID',0) or 0)
    def approval_channel(): return env_i('CENTRAL_ACESSO_APROVACAO_CHANNEL_ID') or int(getattr(b,'AUTORIZACOES_CHANNEL_ID',0) or 0) or env_i('SET_APROVACAO_CHANNEL_ID') or int(getattr(b,'LOGS_CHANNEL_ID',0) or 0)
    async def channel(cid):
        bot=getattr(b,'bot',None)
        if not bot or not cid: return None
        ch=bot.get_channel(int(cid))
        if ch: return ch
        try: return await bot.fetch_channel(int(cid))
        except Exception: return None

    def approval_view(rid):
        v=discord.ui.View(timeout=None)
        yes=discord.ui.Button(label='Aprovar acesso',emoji='✅',style=discord.ButtonStyle.success,custom_id=f'dicor_web_yes:{rid}')
        no=discord.ui.Button(label='Negar acesso',emoji='⛔',style=discord.ButtonStyle.danger,custom_id=f'dicor_web_no:{rid}')
        async def decide(i,status):
            if not approver() or int(getattr(i.user,'id',0) or 0)!=approver(): return await i.response.send_message('❌ Somente o responsável autorizado pode decidir.',ephemeral=True)
            row=get_req(rid)
            if not row or row.get('status')!='pending': return await i.response.send_message('ℹ️ Solicitação já encerrada ou expirada.',ephemeral=True)
            await update_req(rid,status=status,decided_at=int(time.time()),decided_by_id=int(i.user.id))
            for x in v.children: x.disabled=True
            try: await i.response.edit_message(content='✅ ACESSO APROVADO' if status=='approved' else '⛔ ACESSO NEGADO',embed=None,view=v)
            except Exception: pass
        async def y(i): await decide(i,'approved')
        async def n(i): await decide(i,'denied')
        yes.callback=y; no.callback=n; v.add_item(yes); v.add_item(no); return v
    async def send_request(row):
        ch=await channel(approval_channel())
        if not ch or not hasattr(ch,'send'): return False
        emb=discord.Embed(title='🔐 SOLICITAÇÃO DE ACESSO — CENTRAL DICOR',description=f'<@{approver()}>\nPedido de acesso a **{label(row["module"])}**.',color=0x0B3D2E)
        emb.add_field(name='QRA',value=row['qra'],inline=True); emb.add_field(name='Passaporte',value=row['passaporte'],inline=True)
        emb.set_footer(text='Aprove ou negue pelos botões abaixo')
        try:
            msg=await ch.send(embed=emb,view=approval_view(row['id'])); await update_req(row['id'],discord_message_id=int(msg.id)); views.add(row['id']); return True
        except Exception as e: print(f'⚠️ V163 acesso: {type(e).__name__}: {e}',flush=True); return False
    async def restore_views():
        bot=getattr(b,'bot',None)
        if not bot or not hasattr(bot,'add_view'): return
        now=int(time.time())
        for r in load_req():
            rid=str(r.get('id') or '')
            if rid and rid not in views and r.get('status')=='pending' and int(r.get('expires_at') or 0)>now:
                try: bot.add_view(approval_view(rid),message_id=int(r.get('discord_message_id') or 0) or None); views.add(rid)
                except Exception: pass
    if getattr(b,'bot',None): b.bot.add_listener(restore_views,'on_ready')

    CSS=""":root{--g:#d5b45a;--pf:#0d5a45;--bg:#050b0f;--p:#0a181b;--l:#315348;--t:#f4f7f2;--m:#9ba9a3}*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#07131d,#06100f 55%,#050908);color:var(--t);font-family:Inter,Segoe UI,Arial;min-height:100vh}a{color:inherit}.stripe{height:5px;background:linear-gradient(90deg,#0d5a45 0 65%,#d5b45a 65% 79%,#183d73 79%)}.top{height:90px;padding:0 5vw;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--l);background:linear-gradient(90deg,#06131c,#073b2e,#06131c)}.brand{display:flex;gap:14px;align-items:center}.brand img{width:58px;height:58px;object-fit:contain}.brand b{display:block;font-family:Georgia,serif;font-size:20px;letter-spacing:1.5px}.brand small,.eyebrow{color:var(--g);font-size:10px;letter-spacing:1.8px}.wrap{max-width:1260px;margin:auto;padding:52px 22px 70px}.hero{display:grid;grid-template-columns:1.2fr .8fr;gap:32px;align-items:center;margin-bottom:42px}.hero h1{font:52px Georgia,serif;margin:8px 0 15px}.hero h1 span{color:var(--g)}.hero p{color:#b7c4be;line-height:1.65}.crest{min-height:230px;border:1px solid var(--l);border-radius:22px;background:linear-gradient(145deg,#0b2330,#08271f);display:grid;place-items:center}.crest img{width:150px}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}.card{position:relative;border:1px solid #2e4d43;border-radius:16px;background:linear-gradient(160deg,#0d1f25,#0a1716);padding:24px;min-height:205px}.card:before{content:'';position:absolute;inset:0 auto 0 0;width:4px;background:var(--pf)}.card.public:before{background:var(--g)}.card h3{font:22px Georgia,serif;margin:16px 0 8px}.card p{color:#aab8b2;line-height:1.55;min-height:46px}.badge{position:absolute;right:15px;top:15px;border:1px solid #6e795f;border-radius:99px;padding:5px 8px;font-size:8px;letter-spacing:1.2px;color:#d0d9d4}.card a,.btn{display:inline-flex;text-decoration:none;background:#0d5a45;border:1px solid #328068;padding:10px 14px;border-radius:8px;font-weight:800}.public a{background:#c9a844;color:#102017;border-color:#e2c96e}.box{max-width:500px;margin:55px auto;border:1px solid var(--l);background:var(--p);border-radius:18px;padding:30px}.box h1{font-family:Georgia,serif}.box p{color:#aab8b2;line-height:1.55}.box label{display:block;font-size:11px;margin-top:13px}.box input{width:100%;margin-top:7px;padding:13px;background:#061013;border:1px solid #36574d;border-radius:8px;color:white}.box button{width:100%;margin-top:18px;padding:13px;border:0;border-radius:8px;background:#0d5a45;color:white;font-weight:900}.notice{padding:11px;border:1px solid #664e28;background:#2b2412;color:#ead38a;border-radius:8px}.error{border-color:#713a36;background:#2d1514;color:#ffc8c2}.back{display:block;text-align:center;color:#9db2a9;margin-top:18px;text-decoration:none}.spin{width:34px;height:34px;margin:15px auto;border:3px solid #ffffff22;border-top-color:var(--g);border-radius:50%;animation:s 1s linear infinite}@keyframes s{to{transform:rotate(360deg)}}@media(max-width:850px){.hero{grid-template-columns:1fr}.crest{display:none}.grid{grid-template-columns:1fr}.hero h1{font-size:40px}.top{height:auto;padding:14px 18px}}"""
    def page(title,body,refresh=''):
        r=f'<meta http-equiv="refresh" content="{html.escape(refresh,quote=True)}">' if refresh else ''
        return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{r}<title>{html.escape(title)}</title><style>{CSS}</style></head><body><div class="stripe"></div><header class="top"><div class="brand"><img src="/central/brasao-dicor.png"><div><b>POLÍCIA FEDERAL — DICOR</b><small>CENTRAL DE INTELIGÊNCIA</small></div></div><div class="eyebrow">SISTEMA OPERACIONAL</div></header>{body}</body></html>'

    async def central(request):
        try:
            ref=getattr(b,'_v162_refresh_procurados_ativos',None)
            if callable(ref) and not b._v43_procurados_ativos(): await asyncio.wait_for(ref('central v163'),8)
        except Exception: pass
        try: count=len(b._v43_procurados_ativos())
        except Exception: count=0
        cards=f'''<section class="grid"><article class="card public"><span class="badge">PÚBLICO</span><div>🎯</div><h3>Procurados</h3><p>{count} registro(s) confirmado(s) no canal oficial.</p><a href="/catalogo">Consultar procurados</a></article><article class="card"><span class="badge">SENHA ESTRATÉGICA</span><div>🗃️</div><h3>Banco de Dados</h3><p>Fichas, veículos, organizações, evidências e histórico.</p><a href="/fichas">Acessar banco</a></article><article class="card"><span class="badge">SENHA ESTRATÉGICA</span><div>🧬</div><h3>Árvore de Inteligência</h3><p>Conexões entre pessoas, veículos, ocorrências e organizações.</p><a href="/arvore">Abrir inteligência</a></article><article class="card"><span class="badge">APROVAÇÃO NECESSÁRIA</span><div>📋</div><h3>Boletins</h3><p>Consulta interna de boletins e anexos operacionais.</p><a href="/boletins">Solicitar acesso</a></article><article class="card"><span class="badge">APROVAÇÃO NECESSÁRIA</span><div>🧪</div><h3>Perícias</h3><p>Relatórios e fotografias do canal oficial.</p><a href="/pericias">Solicitar acesso</a></article></section>'''
        body=f'<main class="wrap"><section class="hero"><div><div class="eyebrow">DEPARTAMENTO DE INTELIGÊNCIA E COMBATE AO CRIME ORGANIZADO</div><h1>Central Operacional <span>DICOR</span></h1><p>Ambiente unificado com acesso separado por nível de sensibilidade.</p></div><div class="crest"><img src="/central/brasao-dicor.png"></div></section>{cards}</main>'
        return web.Response(text=page('Central DICOR',body),content_type='text/html',charset='utf-8')
    b.central_portal_http=central

    async def login_get(request):
        nxt=safe_next(request.query.get('next')); m=module(nxt); rid=str(request.query.get('rid') or '')
        if rid:
            row=get_req(rid)
            if not row or int(row.get('expires_at') or 0)<int(time.time()): return web.Response(text=page('Acesso','<main class="wrap"><div class="box"><h1>Solicitação expirada</h1><a class="back" href="/">Voltar</a></div></main>'),content_type='text/html')
            status=str(row.get('status') or 'pending'); m=str(row.get('module') or m); nxt=safe_next(row.get('next'))
            if status=='approved':
                resp=web.HTTPFound(nxt); token=sign('approved:'+m,rid)
                if token: resp.set_cookie(COOKIE_APPROVAL+m,token,max_age=COOKIE_TTL,httponly=True,secure=True,samesite='Lax',path='/')
                raise resp
            if status=='denied': return web.Response(text=page('Negado',f'<main class="wrap"><div class="box"><h1>Acesso negado</h1><p>O responsável negou o acesso a {label(m)}.</p><a class="back" href="/">Voltar</a></div></main>'),content_type='text/html')
            ref=f'3;url=/acesso?next={quote(nxt,safe="/?=&")}&rid={quote(rid)}'; body=f'<main class="wrap"><div class="box" style="text-align:center"><div class="spin"></div><h1>Aguardando aprovação</h1><p>Pedido de acesso a <b>{label(m)}</b> enviado ao responsável.</p><div class="notice">QRA: {html.escape(str(row.get("qra") or ""))} • Passaporte: {html.escape(str(row.get("passaporte") or ""))}</div></div></main>'
            return web.Response(text=page('Aguardando',body,ref),content_type='text/html')
        if m in {'banco','arvore'}:
            body=f'<main class="wrap"><form class="box" method="post" action="/acesso"><div class="eyebrow">NÍVEL ESTRATÉGICO</div><h1>Senha estratégica</h1><p>Sem cadastro: acesso somente para quem recebeu a senha diretamente.</p><input type="hidden" name="mode" value="strategic"><input type="hidden" name="next" value="{html.escape(nxt,quote=True)}"><label>Senha</label><input type="password" name="senha" required autofocus><button>VALIDAR ACESSO</button><a class="back" href="/">Voltar</a></form></main>'
            return web.Response(text=page('Acesso estratégico',body),content_type='text/html')
        if m in {'pericias','boletins'}:
            body=f'<main class="wrap"><form class="box" method="post" action="/acesso"><div class="eyebrow">AUTORIZAÇÃO INDIVIDUAL</div><h1>Solicitar acesso</h1><p>O pedido será enviado ao Discord para aprovação ou recusa.</p><input type="hidden" name="mode" value="approval"><input type="hidden" name="next" value="{html.escape(nxt,quote=True)}"><label>QRA / Nome</label><input name="qra" maxlength="80" required><label>Passaporte / RG</label><input name="passaporte" maxlength="40" required><button>ENVIAR PARA APROVAÇÃO</button><a class="back" href="/">Voltar</a></form></main>'
            return web.Response(text=page('Solicitar acesso',body),content_type='text/html')
        raise web.HTTPFound('/')

    async def login_post(request):
        form=await request.post(); nxt=safe_next(form.get('next')); m=module(nxt); mode=str(form.get('mode') or '')
        if mode=='strategic' and m in {'banco','arvore'}:
            supplied=str(form.get('senha') or ''); expected=strategy_pass()
            if not expected or not hmac.compare_digest(supplied,expected): return web.Response(text=page('Senha inválida',f'<main class="wrap"><div class="box"><h1>Senha inválida</h1><div class="notice error">Acesso recusado.</div><a class="back" href="/acesso?next={quote(nxt,safe="/?=&")}">Tentar novamente</a></div></main>'),content_type='text/html',status=403)
            resp=web.HTTPFound(nxt); resp.set_cookie(COOKIE_STRATEGY,sign('strategic','central'),max_age=COOKIE_TTL,httponly=True,secure=True,samesite='Lax',path='/'); raise resp
        if mode=='approval' and m in {'pericias','boletins'}:
            qra=str(form.get('qra') or '').strip()[:80]; pas=str(form.get('passaporte') or '').strip()[:40]
            if not qra or not pas: return web.Response(text='Identificação incompleta.',status=400)
            if not approver() or not approval_channel(): return web.Response(text='Aprovação não configurada.',status=503)
            rid=secrets.token_urlsafe(24); now=int(time.time()); row={'id':rid,'module':m,'qra':qra,'passaporte':pas,'next':nxt,'status':'pending','created_at':now,'expires_at':now+REQUEST_TTL}
            async with req_lock: rows=load_req(); rows.append(row); save_req(rows)
            if not await send_request(row): await update_req(rid,status='error'); return web.Response(text='Falha ao enviar pedido.',status=503)
            raise web.HTTPFound(f'/acesso?next={quote(nxt,safe="/?=&")}&rid={quote(rid)}')
        raise web.HTTPFound('/')
    async def logout(request):
        r=web.HTTPFound('/'); r.del_cookie(COOKIE_STRATEGY,path='/')
        for m in ('pericias','boletins'): r.del_cookie(COOKIE_APPROVAL+m,path='/')
        raise r
    b.central_login_get=login_get; b.central_login_post=login_post; b.central_logout_http=logout

    async def auth_impl(request,handler):
        p=str(request.path or '/').lower()
        if p in {'/','/index.html','/catalogo','/acesso','/sair','/health','/healthz'} or p=='/central/brasao-dicor.png' or p.startswith('/uploads/'): return await handler(request)
        if p.startswith('/dossies-central'): raise web.HTTPFound('/')
        m=module(p)
        if p.startswith('/api/') and not m: m='banco'
        if m in {'banco','arvore'}:
            if verify(request.cookies.get(COOKIE_STRATEGY,''),'strategic','central'): return await handler(request)
            raise web.HTTPFound('/acesso?next='+quote(str(request.rel_url),safe='/?=&'))
        if m in {'pericias','boletins'}:
            if verify(request.cookies.get(COOKIE_APPROVAL+m,''),'approved:'+m): return await handler(request)
            raise web.HTTPFound('/acesso?next='+quote(str(request.rel_url),safe='/?=&'))
        return await handler(request)
    b.central_auth_middleware=web.middleware(auth_impl)

    def msg_id(r):
        for k in ('mensagem_id','publicacao_mensagem_id','message_id','discord_message_id'):
            try:
                if int(r.get(k) or 0): return int(r.get(k))
            except Exception: pass
        for k in ('mensagem_url','jump_url','publicacao_url','url'):
            x=re.findall(r'(?<!\d)(\d{15,25})(?!\d)',str(r.get(k) or ''))
            if x: return int(x[-1])
        return 0
    def flatten(v,d=0):
        if d>4: return []
        if isinstance(v,dict): return [str(k) for k in v]+[z for x in v.values() for z in flatten(x,d+1)]
        if isinstance(v,(list,tuple,set)): return [z for x in v for z in flatten(x,d+1)]
        return [] if v is None else [str(v)]
    def extract_bo(*vals):
        text='\n'.join(x for v in vals for x in flatten(v))
        for pat in (r'\bBO[\s._:/-]*DICOR[\s._:/-]*(\d{1,8})\b',r'\bBOLETIM[^\d]{0,30}(?:DICOR[^\d]{0,10})?(\d{1,8})\b'):
            m=re.search(pat,text,re.I)
            if m: return f'BO-DICOR-{int(m.group(1)):03d}'
        return ''
    def is_img(u,ct=''): return str(ct).lower().startswith('image/') or str(u).lower().split('?',1)[0].endswith(IMG_EXTS)
    def msg_text(msg):
        out=[str(getattr(msg,'content','') or '')]
        for e in list(getattr(msg,'embeds',[]) or []):
            out += [str(getattr(e,'title','') or ''),str(getattr(e,'description','') or '')]
            for f in list(getattr(e,'fields',[]) or []): out += [str(getattr(f,'name','') or ''),str(getattr(f,'value','') or '')]
        return '\n'.join(x for x in out if x)
    def msg_images(msg):
        out=[]
        for a in list(getattr(msg,'attachments',[]) or []):
            u=str(getattr(a,'url','') or '')
            if u and is_img(u,str(getattr(a,'content_type','') or '')): out.append(u)
        for e in list(getattr(msg,'embeds',[]) or []):
            for k in ('image','thumbnail'):
                o=getattr(e,k,None); u=str(getattr(o,'url','') or '') if o else ''
                if u: out.append(u)
        return list(dict.fromkeys(out))
    def record_images(r):
        out=[]
        def walk(v,k='',d=0):
            if d>4:return
            if isinstance(v,dict):
                for a,z in v.items(): walk(z,str(a),d+1)
            elif isinstance(v,(list,tuple)):
                for z in v: walk(z,k,d+1)
            elif isinstance(v,str):
                s=v.strip()
                if (s.startswith('http') or s.startswith('/')) and (is_img(s) or any(x in k.lower() for x in ('foto','imagem','image','rg','document'))): out.append(s)
        walk(r); return list(dict.fromkeys(out))
    async def wanted_live(records):
        ch=await channel(WANTED_CHANNEL); result={}
        if not ch or not hasattr(ch,'fetch_message'): return result
        async def one(mid):
            try:
                m=await ch.fetch_message(mid); return mid,{'images':msg_images(m),'text':msg_text(m)}
            except Exception:return mid,{}
        pairs=await asyncio.gather(*(one(x) for x in {msg_id(r) for r in records if msg_id(r)})); return dict(pairs)
    def val(r,*keys,default='Não informado'):
        for k in keys:
            v=r.get(k)
            if v not in (None,'',[],{}): return ('\n'.join(map(str,v)) if isinstance(v,(list,tuple)) else str(v))[:5000]
        return default
    def wanted_card(r,live):
        name=val(r,'nome','name',default='Nome não informado'); rg=val(r,'rg','passaporte','documento'); crimes=val(r,'crimes','crime','infracoes','infrações'); last=val(r,'ultimo_avistamento','informacoes','último_avistamento'); bo=extract_bo(r,live.get('text','')); imgs=list(dict.fromkeys(list(live.get('images') or [])+record_images(r))); person=imgs[0] if imgs else ''; doc=imgs[1] if len(imgs)>1 else ''
        def photo(u,title):
            return f'<button class="photo" data-u="{html.escape(u,quote=True)}" onclick="openP(this.dataset.u)"><img src="{html.escape(u,quote=True)}" loading="lazy"></button>' if u else f'<div class="empty">SEM IMAGEM<br><small>{title}</small></div>'
        bohtml=f'<a href="/boletins?busca={quote(bo)}">{html.escape(bo)}</a>' if bo else 'Não informado'
        return f'<article class="wanted"><div class="photos"><div><b>FOTO DO INDIVÍDUO</b>{photo(person,"FOTO")}</div><div><b>DOCUMENTO / RG</b>{photo(doc,"RG")}</div></div><section class="wi"><small>IDENTIFICAÇÃO</small><h2>{html.escape(name)}</h2><strong>RG • {html.escape(rg)}</strong><div class="danger"><small>CRIMES</small><p>{html.escape(crimes).replace(chr(10),"<br>")}</p></div><div class="info"><small>ÚLTIMO AVISTAMENTO</small><p>{html.escape(last)}</p></div><div class="info"><small>BOLETIM VINCULADO</small><p>{bohtml}</p></div></section></article>'
    async def catalog(request):
        try:
            ref=getattr(b,'_v162_refresh_procurados_ativos',None)
            if callable(ref): await asyncio.wait_for(ref('catalogo v163'),10)
        except Exception: pass
        try: rows=list(b._v43_procurados_ativos() or [])
        except Exception: rows=[]
        live=await wanted_live(rows); cards=''.join(wanted_card(r,live.get(msg_id(r),{})) for r in rows) or '<div class="none">Nenhum procurado ativo.</div>'
        extra=""".cat{max-width:1280px;margin:auto;padding:38px 18px}.cat h1{text-align:center;font-family:Georgia,serif}.wanted{border:1px solid var(--l);border-radius:16px;overflow:hidden;margin:20px 0;background:#07100f;display:grid;grid-template-columns:1.55fr .85fr}.photos{display:grid;grid-template-columns:1fr 1fr;border-right:1px solid var(--l)}.photos>div{position:relative;min-height:420px;border-right:1px solid var(--l)}.photos>div:last-child{border:0}.photos b{position:absolute;z-index:2;top:12px;left:12px;background:#06110fee;border:1px solid #7a6531;color:#e5ce7d;padding:7px;border-radius:7px;font-size:10px}.photo{width:100%;height:100%;border:0;background:#030807;padding:0;cursor:zoom-in}.photo img{width:100%;height:100%;object-fit:contain}.empty{height:100%;display:grid;place-items:center;color:#71847b}.wi{padding:26px}.wi h2{font-family:Georgia,serif;font-size:30px}.wi>strong{color:#e5ce7d}.danger,.info{margin-top:14px;padding:13px;border:1px solid #425b52;border-radius:10px}.danger{background:#24100f;border-color:#6d3631}.wi small{color:var(--g);letter-spacing:1.3px}.wi p{line-height:1.55}.light{display:none;position:fixed;inset:0;background:#000e;z-index:100;align-items:center;justify-content:center}.light.on{display:flex}.light img{max-width:95vw;max-height:92vh}@media(max-width:900px){.wanted{grid-template-columns:1fr}.photos{border-right:0;border-bottom:1px solid var(--l)}}"""
        body=f'<main class="cat"><h1>Indivíduos Procurados</h1>{cards}</main><div id="lp" class="light" onclick="this.classList.remove(\'on\')"><img id="lpi"></div><script>function openP(u){{document.getElementById("lpi").src=u;document.getElementById("lp").classList.add("on")}}</script>'
        return web.Response(text=page('Procurados',body).replace('</style>',extra+'</style>'),content_type='text/html',charset='utf-8')
    b.pagina_inicial=catalog

    async def scan_pericias():
        async with pericia_lock:
            if pericia_cache['items'] and time.monotonic()-pericia_cache['at']<30:return list(pericia_cache['items'])
            ch=await channel(int(getattr(b,'PERICIAS_CHANNEL_ID',0) or env_i('PERICIAS_CHANNEL_ID'))); items=[]
            if not ch:return []
            async def collect(th):
                texts=[]; imgs=[]; links=[]; jump=''
                try:
                    async for m in th.history(limit=150,oldest_first=True):
                        t=msg_text(m)
                        if t:texts.append(t)
                        imgs+=msg_images(m); jump=jump or str(getattr(m,'jump_url','') or '')
                        for a in list(getattr(m,'attachments',[]) or []):
                            u=str(getattr(a,'url','') or ''); n=str(getattr(a,'filename','') or 'Anexo')
                            if u and not is_img(u,str(getattr(a,'content_type','') or '')):links.append((n,u))
                except Exception:return
                if texts or imgs or links:
                    txt='\n\n'.join(texts)[:12000]; title=str(getattr(th,'name','') or 'Perícia'); items.append({'title':title,'text':txt,'images':list(dict.fromkeys(imgs))[:20],'links':links,'jump':jump,'bo':extract_bo(title,txt)})
            threads=list(getattr(ch,'threads',[]) or []); guild=getattr(ch,'guild',None)
            if guild:
                for th in list(getattr(guild,'threads',[]) or []):
                    if int(getattr(th,'parent_id',0) or 0)==int(getattr(ch,'id',0) or 0) and th not in threads:threads.append(th)
            arch=getattr(ch,'archived_threads',None)
            if callable(arch):
                try:
                    async for th in arch(limit=50):
                        if th not in threads:threads.append(th)
                except Exception:pass
            if threads: await asyncio.gather(*(collect(t) for t in threads[:100]))
            if hasattr(ch,'history'):
                try:
                    async for m in ch.history(limit=300,oldest_first=False):
                        t=msg_text(m); imgs=msg_images(m)
                        if not t and not imgs:continue
                        title=next((str(getattr(e,'title','') or '') for e in list(getattr(m,'embeds',[]) or []) if getattr(e,'title',None)),f'Perícia • {m.id}')
                        items.append({'title':title,'text':t[:12000],'images':imgs,'links':[],'jump':str(getattr(m,'jump_url','') or ''),'bo':extract_bo(title,t)})
                except Exception:pass
            seen=set(); clean=[]
            for x in items:
                k=(x.get('jump'),x.get('title'),x.get('text','')[:160])
                if k not in seen:seen.add(k);clean.append(x)
            pericia_cache.update(at=time.monotonic(),items=clean); return list(clean)
    def pericia_card(x):
        imgs=''.join(f'<button class="pi" data-u="{html.escape(u,quote=True)}" onclick="openP(this.dataset.u)"><img src="{html.escape(u,quote=True)}" loading="lazy"></button>' for u in x.get('images') or []) or '<div class="nomedia">Sem imagens anexadas.</div>'
        bo=x.get('bo') or ''; bohtml=f'<a href="/boletins?busca={quote(bo)}">{html.escape(bo)}</a>' if bo else 'Sem BO identificado'; jump=f'<a class="btn" href="{html.escape(x.get("jump") or "",quote=True)}" target="_blank">Abrir no Discord</a>' if x.get('jump') else ''
        return f'<article class="pc"><header><div><small>REGISTRO DE PERÍCIA</small><h2>{html.escape(x.get("title") or "Perícia")}</h2></div><b>{bohtml}</b></header><div class="pt">{html.escape(x.get("text") or "Sem descrição").replace(chr(10),"<br>")}</div><div class="pg">{imgs}</div>{jump}</article>'
    async def pericias(request):
        cards=''.join(pericia_card(x) for x in await scan_pericias()) or '<div class="none">Nenhuma perícia localizada.</div>'
        extra=""".per{max-width:1280px;margin:auto;padding:38px 18px}.per>h1{text-align:center;font-family:Georgia,serif}.pc{border:1px solid var(--l);border-radius:16px;overflow:hidden;background:#081413;margin:20px 0}.pc header{padding:17px 19px;background:#0a1c1b;border-bottom:1px solid var(--l);display:flex;justify-content:space-between;align-items:center;gap:15px}.pc h2{margin:5px 0;font-family:Georgia,serif}.pc small{color:var(--g)}.pt{padding:18px;line-height:1.6;color:#d0d8d4}.pg{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--l);border-top:1px solid var(--l)}.pi{border:0;padding:0;background:#020706;min-height:220px;cursor:zoom-in}.pi img{width:100%;height:100%;max-height:360px;object-fit:contain}.nomedia{grid-column:1/-1;background:#07100f;color:#71847b;text-align:center;padding:45px}.pc>.btn{margin:14px}.light{display:none;position:fixed;inset:0;background:#000e;z-index:100;align-items:center;justify-content:center}.light.on{display:flex}.light img{max-width:95vw;max-height:92vh}@media(max-width:850px){.pg{grid-template-columns:1fr 1fr}}@media(max-width:550px){.pg{grid-template-columns:1fr}.pc header{align-items:flex-start;flex-direction:column}}"""
        body=f'<main class="per"><h1>Perícias • Relatórios e Anexos</h1>{cards}</main><div id="lp" class="light" onclick="this.classList.remove(\'on\')"><img id="lpi"></div><script>function openP(u){{document.getElementById("lpi").src=u;document.getElementById("lp").classList.add("on")}}</script>'
        return web.Response(text=page('Perícias',body).replace('</style>',extra+'</style>'),content_type='text/html',charset='utf-8')
    b.central_pericias_http=pericias
    async def no_dossies(request): raise web.HTTPFound('/')
    b.central_dossies_http=no_dossies
    print('✅ V163 Central PF: mídia real, BO vinculado, acesso por aprovação/senha e Dossiês fora da Central.',flush=True)
