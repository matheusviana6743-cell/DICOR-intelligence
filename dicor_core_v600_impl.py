# -*- coding: utf-8 -*-
"""DICOR Core V600: one clean runtime for BO, Pericia and Dossie."""
from __future__ import annotations
import asyncio, base64, io, json, os, re, traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, UserSelect, Button
try:
    from PIL import Image
except Exception:
    Image=None
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase.pdfmetrics import stringWidth
except Exception:
    canvas=None; ImageReader=None; stringWidth=None

SOURCE_BO_ID=int(os.getenv('DICOR_BO_SOURCE_ID','1490200514837745754'))
TARGET_BO_ID=int(os.getenv('DICOR_BO_TARGET_ID','1525762770253910136'))
SOURCE_PERICIA_ID=int(os.getenv('DICOR_PERICIA_SOURCE_ID','1490200524367200297'))
LOG_ID=int(os.getenv('LOGS_CHANNEL_ID','1490205503228477610'))
DATA_DIR=Path(os.getenv('DICOR_DATA_DIR','data')); DATA_DIR.mkdir(parents=True,exist_ok=True)
STATE=DATA_DIR/'core_v600_state.json'; MEDIA=DATA_DIR/'core_v600_media'; DOCS=DATA_DIR/'dossies_v600'
MEDIA.mkdir(exist_ok=True); DOCS.mkdir(exist_ok=True)
TEMPLATE_B64=Path(__file__).with_name('dicor_template_v600.b64'); TEMPLATE=DATA_DIR/'core_v600_template.png'
AUTH_ROLE_IDS={int(x) for x in os.getenv('DICOR_AUTH_ROLE_IDS','1490200388912156692,1490200383614615725,1490200382776021132').replace(';',',').split(',') if x.strip().isdigit()}
TEAM_ROLE_IDS={int(x) for x in os.getenv('DICOR_TEAM_ROLE_IDS','1490200391239864352,1490200390426165290').replace(';',',').split(',') if x.strip().isdigit()}

def load_state():
    try:
        if STATE.exists():
            d=json.loads(STATE.read_text(encoding='utf-8')); return d if isinstance(d,dict) else {}
    except Exception: traceback.print_exc()
    return {}

def save_state(d):
    tmp=STATE.with_suffix('.tmp'); tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(STATE)

def now(): return datetime.now().strftime('%d/%m/%Y %H:%M')
def month(dt): return dt.strftime('%m/%Y')
def norm(s): return ' '.join(re.sub(r'[^0-9a-zA-ZÀ-ÿ]+',' ',str(s or '').casefold()).split())
def text_of(m):
    p=[]
    if getattr(m,'content',None): p.append(m.content)
    for e in getattr(m,'embeds',[]) or []:
        if e.title:p.append(str(e.title))
        if e.description:p.append(str(e.description))
        for f in getattr(e,'fields',[]) or []: p.extend([str(f.name or ''),str(f.value or '')])
    return '\n'.join(x for x in p if x).strip()
def authorized(m):
    return any(getattr(r,'id',0) in AUTH_ROLE_IDS for r in getattr(m,'roles',[])) or any('inspetor' in norm(getattr(r,'name','')) or 'diretor' in norm(getattr(r,'name','')) for r in getattr(m,'roles',[]))
def team_member(m):
    if any(getattr(r,'id',0) in TEAM_ROLE_IDS for r in getattr(m,'roles',[])): return True
    return any(any(k in norm(getattr(r,'name','')) for k in ('estagi','investigador','inspetor','agente','delegado','dicor','escriv')) for r in getattr(m,'roles',[]))
def extract_number(s,label):
    for p in (rf'{label}[^0-9]{{0,30}}(?:N[º°O.]?\s*)?(\d{{1,8}})',r'N[º°O.]?\s*(\d{1,8})',r'#\s*(\d{1,8})'):
        m=re.search(p,str(s or ''),re.I)
        if m:return f'{int(m.group(1)):04d}'
    return ''
def next_number(kind,mo):
    d=load_state(); c=d.setdefault('counters',{}).setdefault(kind,{}); n=int(c.get(mo,0))+1; c[mo]=n; save_state(d); return f'{n:04d}'
def records(kind):
    x=load_state().get(kind,[]); return x if isinstance(x,list) else []
def append_record(kind,r):
    d=load_state(); d.setdefault(kind,[]).append(r); save_state(d)
def update_record(kind,rid,patch):
    d=load_state()
    for r in d.get(kind,[]):
        if str(r.get('id'))==str(rid): r.update(patch); save_state(d); return r
    return None
def find_source(kind,message_id): return next((r for r in records(kind) if str(r.get('source_message_id'))==str(message_id)),None)
async def ack(i):
    try:
        if not i.response.is_done(): await i.response.defer(ephemeral=True,thinking=True)
        return True
    except Exception:return False
async def respond(i,text,view=None):
    try:
        if i.response.is_done(): await i.followup.send(text,view=view,ephemeral=True)
        else: await i.response.send_message(text,view=view,ephemeral=True)
    except Exception: pass
async def log(client,text):
    try:
        ch=client.get_channel(LOG_ID)
        if ch: await ch.send(str(text)[:1900])
    except Exception: pass

class Core:
    def __init__(self,mod): self.mod=mod; self.client=mod.bot; self.bo_lock=set(); self.per_lock=set(); self.recovered=False
    async def channel(self,guild,cid):
        c=guild.get_channel(cid)
        if c is None:
            try:c=await guild.fetch_channel(cid)
            except Exception:return None
        return c
    def by_thread(self,kind,tid): return next((r for r in records(kind) if str(r.get('thread_id'))==str(tid)),None)
    async def choose(self,guild,kind,mo):
        cs=[m for m in guild.members if not m.bot and team_member(m) and not authorized(m)] or [m for m in guild.members if not m.bot and team_member(m)]
        if not cs:return None
        d=load_state(); rr=d.setdefault('round_robin',{}).setdefault(kind,{}); idx=int(rr.get(mo,0))%len(cs); rr[mo]=idx+1; save_state(d)
        return sorted(cs,key=lambda m:(m.display_name.casefold(),m.id))[idx]
    async def create_bo(self,msg):
        if not msg.guild or msg.author.bot or msg.channel.id!=SOURCE_BO_ID or msg.id in self.bo_lock:return
        self.bo_lock.add(msg.id)
        try:
            if find_source('bo',msg.id):return
            txt=text_of(msg)
            if 'boletim de ocorr' not in norm(txt) and not msg.embeds:return
            mo=month(msg.created_at); num=extract_number(txt,'boletim') or next_number('bo',mo)
            used={r.get('number') for r in records('bo') if r.get('month')==mo}
            while num in used:num=next_number('bo',mo)
            parent=await self.channel(msg.guild,TARGET_BO_ID)
            if not isinstance(parent,discord.TextChannel): raise RuntimeError(f'Canal BO {TARGET_BO_ID} não encontrado')
            agent=await self.choose(msg.guild,'bo',mo)
            th=await parent.create_thread(name=f'📋 BOLETIM DE OCORRÊNCIA — Nº {num}',type=discord.ChannelType.private_thread,invitable=False,auto_archive_duration=10080,reason='DICOR V600')
            if agent: await th.add_user(agent)
            em=discord.Embed(title='📋 BOLETIM DE OCORRÊNCIA',description=txt[:4000] or 'Sem texto.')
            em.add_field(name='Número',value=f'`{num}`',inline=True); em.add_field(name='Responsável',value=agent.mention if agent else 'Aguardando seleção',inline=True); em.add_field(name='Origem',value=msg.jump_url,inline=False)
            await th.send(content=agent.mention if agent else None,embed=em,allowed_mentions=discord.AllowedMentions(users=True,roles=False,everyone=False))
            for a in msg.attachments or []:
                try: await th.send(file=await a.to_file(use_cached=True))
                except Exception: await th.send(a.url)
            rid=f'BO-{msg.id}'; append_record('bo',{'id':rid,'number':num,'month':mo,'source_message_id':msg.id,'source_channel_id':SOURCE_BO_ID,'thread_id':th.id,'agent_id':agent.id if agent else None,'agent_name':str(agent) if agent else '','status':'EM_ATENDIMENTO' if agent else 'SEM_AGENTE','created_at':now()})
            await th.send(view=BOView(self,rid)); await log(self.client,f'✅ V600 BO criado | {num} | tópico {th.id}')
        except Exception:
            traceback.print_exc()
            try: await log(self.client,f'❌ V600 falha BO | origem {msg.id}\n{traceback.format_exc()[-1400:]}')
            except Exception: pass
        finally:self.bo_lock.discard(msg.id)
    async def create_pericia(self,msg):
        if not msg.guild or msg.author.bot or msg.channel.id!=SOURCE_PERICIA_ID or msg.id in self.per_lock:return
        self.per_lock.add(msg.id)
        try:
            if find_source('pericia',msg.id):return
            txt=text_of(msg); mo=month(msg.created_at); num=extract_number(txt,'pericia') or next_number('pericia',mo)
            parent=await self.channel(msg.guild,SOURCE_PERICIA_ID)
            if not isinstance(parent,discord.TextChannel): raise RuntimeError(f'Canal Perícia {SOURCE_PERICIA_ID} não encontrado')
            th=await parent.create_thread(name=f'🔬 PERÍCIA Nº {num} • AGUARDANDO AGENTE',type=discord.ChannelType.private_thread,invitable=False,auto_archive_duration=10080,reason='DICOR V600')
            for a in msg.attachments or []:
                try: await th.send(file=await a.to_file(use_cached=True))
                except Exception: await th.send(a.url)
            rid=f'PERICIA-{msg.id}'; append_record('pericia',{'id':rid,'number':num,'month':mo,'source_message_id':msg.id,'source_channel_id':SOURCE_PERICIA_ID,'thread_id':th.id,'agent_id':None,'status':'AGUARDANDO_AGENTE','attachments':len(msg.attachments or []),'created_at':now()})
            await th.send(embed=discord.Embed(title=f'🔬 CONTROLE DA PERÍCIA EXTERNA — Nº {num}',description='Um Inspetor+ deve selecionar o agente responsável abaixo.'),view=PericiaView(self,rid)); await log(self.client,f'✅ V600 Perícia criada | {num} | tópico {th.id}')
        except Exception:
            traceback.print_exc()
            try: await log(self.client,f'❌ V600 falha Perícia | origem {msg.id}\n{traceback.format_exc()[-1400:]}')
            except Exception: pass
        finally:self.per_lock.discard(msg.id)
    async def recover(self):
        if self.recovered:return
        self.recovered=True; await asyncio.sleep(3)
        for g in self.client.guilds:
            for cid,fn in ((SOURCE_BO_ID,self.create_bo),(SOURCE_PERICIA_ID,self.create_pericia)):
                ch=g.get_channel(cid)
                if isinstance(ch,discord.TextChannel):
                    try:
                        async for m in ch.history(limit=3000,oldest_first=True): await fn(m)
                    except Exception: traceback.print_exc()
        print('✅ V600: recuperação automática BO + Perícia concluída',flush=True)
    async def on_message(self,msg):
        if not msg.guild or msg.author.bot:return
        if msg.channel.id==SOURCE_BO_ID: await self.create_bo(msg)
        elif msg.channel.id==SOURCE_PERICIA_ID: await self.create_pericia(msg)

class BOAgentSelect(UserSelect):
    def __init__(self,core): super().__init__(placeholder='Inspetor+: selecione o agente responsável',min_values=1,max_values=1,custom_id='dicor_v600_bo_agent'); self.core=core
    async def callback(self,i):
        if not isinstance(i.user,discord.Member) or not authorized(i.user):return await respond(i,'❌ Apenas Inspetor+ pode alterar o responsável.')
        if not await ack(i):return
        r=self.core.by_thread('bo',getattr(i.channel,'id',0)); m=self.values[0] if self.values else None
        if not r or not isinstance(m,discord.Member) or not team_member(m):return await respond(i,'❌ Atendimento ou membro inválido.')
        update_record('bo',r['id'],{'agent_id':m.id,'agent_name':str(m),'status':'EM_ATENDIMENTO'})
        try: await i.channel.add_user(m); await i.channel.send(f'📌 {m.mention} foi definido como responsável pelo BO **{r["number"]}**.')
        except Exception:pass
        await respond(i,f'✅ {m.mention} agora é o responsável pelo BO **{r["number"]}**.')
class BOView(View):
    def __init__(self,core,rid=''):
        super().__init__(timeout=None); self.core=core; self.rid=rid; self.add_item(BOAgentSelect(core)); b=Button(label='Finalizar BO',emoji='✅',style=discord.ButtonStyle.success,custom_id='dicor_v600_bo_done'); b.callback=self.done; self.add_item(b)
    async def done(self,i):
        if not await ack(i):return
        if not isinstance(i.user,discord.Member) or not authorized(i.user):return await respond(i,'❌ Apenas Inspetor+ pode finalizar.')
        r=self.core.by_thread('bo',getattr(i.channel,'id',0))
        if r:update_record('bo',r['id'],{'status':'FINALIZADO','closed_at':now()}); await respond(i,'✅ BO finalizado.')
class PericiaAgentSelect(UserSelect):
    def __init__(self,core): super().__init__(placeholder='Inspetor+: selecione o agente responsável',min_values=1,max_values=1,custom_id='dicor_v600_pericia_agent'); self.core=core
    async def callback(self,i):
        if not isinstance(i.user,discord.Member) or not authorized(i.user):return await respond(i,'❌ Apenas Inspetor+ pode escolher o responsável.')
        if not await ack(i):return
        r=self.core.by_thread('pericia',getattr(i.channel,'id',0)); m=self.values[0] if self.values else None
        if not r or not isinstance(m,discord.Member) or not team_member(m):return await respond(i,'❌ Perícia ou membro inválido.')
        update_record('pericia',r['id'],{'agent_id':m.id,'agent_name':str(m),'status':'PENDENTE'})
        try: await i.channel.add_user(m); await i.channel.send(f'📌 {m.mention}\n**TAREFA DE PERÍCIA ATRIBUÍDA**\nVocê é o responsável pela Perícia Nº {r["number"]}.')
        except Exception:pass
        await respond(i,f'✅ {m.mention} foi definido como responsável pela Perícia Nº **{r["number"]}**.')
class PericiaView(View):
    def __init__(self,core,rid=''):
        super().__init__(timeout=None); self.core=core; self.rid=rid; self.add_item(PericiaAgentSelect(core)); b=Button(label='Marcar concluída',emoji='✅',style=discord.ButtonStyle.success,custom_id='dicor_v600_pericia_done'); b.callback=self.done; self.add_item(b)
    async def done(self,i):
        if not await ack(i):return
        if not isinstance(i.user,discord.Member) or not authorized(i.user):return await respond(i,'❌ Apenas Inspetor+ pode concluir.')
        r=self.core.by_thread('pericia',getattr(i.channel,'id',0));
        if r:update_record('pericia',r['id'],{'status':'CONCLUIDA','closed_at':now()}); await respond(i,'✅ Perícia concluída.')

DOC_SECTIONS=[('01','Painel da organização'),('02','Fotos dos membros'),('03','Localização'),('04','Foto de cima da organização'),('05','Materiais que vendem'),('06','Registro de compra'),('07','Informante'),('08','Baú de membros'),('09','Baú de líder'),('10','Local de fabricação'),('11','Local de produção'),('12','Informações gerais'),('13','Assinaturas'),('14','Análise consolidada'),('15','Evidências adicionais'),('16','Cronologia'),('17','Conclusões'),('18','Encerramento')]
def template_png():
    if TEMPLATE.exists() and TEMPLATE.stat().st_size>10000:return TEMPLATE
    raw=''.join(TEMPLATE_B64.read_text(encoding='utf-8').split()); data=base64.b64decode(raw,validate=True); TEMPLATE.write_bytes(data)
    if Image:
        try:
            with Image.open(io.BytesIO(data)) as im: im.convert('RGB').save(TEMPLATE,'PNG')
        except Exception:pass
    return TEMPLATE
def wrap(txt,size,width):
    txt=re.sub(r'(?:/tmp|/mnt)/[^\s]+','',str(txt or '')).strip(); out=[]; cur=''
    for w in txt.split():
        cand=w if not cur else cur+' '+w
        if stringWidth(cand,'Courier',size)<=width:cur=cand
        else:
            if cur:out.append(cur)
            cur=w
    if cur:out.append(cur)
    return out
def draw_text(c,txt,x,y,w,size=9.5,bold=False,lines=18):
    f='Courier-Bold' if bold else 'Courier'; c.setFont(f,size)
    for line in wrap(txt,size,w)[:lines]: c.drawString(x,y,line); y-=size*1.42
    return y
def section_code(text):
    n=norm(text); rules={'01':('painel','lideran'),'02':('fotos dos membros','membros','integrantes'),'03':('localizacao','coordenadas','endereco'),'04':('foto de cima','visao aerea','aerea'),'05':('material','ingrediente','produto'),'06':('registrar compra','compra'),'07':('informante',),'08':('bau de membros',),'09':('bau de lider',),'10':('fabricacao','farm'),'11':('producao',),'12':('informacoes gerais','radio','crime')}
    for k,vals in rules.items():
        if any(norm(v) in n for v in vals):return k
    return '15'
async def collect_dossier(channel):
    threads=[]
    if isinstance(channel,discord.Thread):threads=[channel]
    else:
        try:a=list(channel.threads); b=[t async for t in channel.archived_threads(limit=None)]; seen={t.id for t in a}; threads=a+[t for t in b if t.id not in seen]
        except Exception:threads=[]
    by=defaultdict(list)
    for t in threads:
        try:
            async for m in t.history(limit=None,oldest_first=True):
                by[section_code(t.name+' '+text_of(m))].append({'thread':t.name,'thread_id':t.id,'author':str(m.author),'date':m.created_at.strftime('%d/%m/%Y %H:%M'),'content':text_of(m),'attachments':[{'url':a.url,'filename':a.filename} for a in m.attachments]})
        except Exception:traceback.print_exc()
    return by
async def generate_doc(channel):
    if canvas is None or ImageReader is None:raise RuntimeError('ReportLab não disponível')
    by=await collect_dossier(channel); bg=template_png(); W,H=A4; out=DOCS/f'PF-DICOR-{channel.id}-{datetime.now().strftime("%Y%m%d-%H%M%S")}.pdf'; c=canvas.Canvas(str(out),pagesize=A4)
    for idx,(code,title) in enumerate(DOC_SECTIONS,1):
        c.drawImage(ImageReader(str(bg)),0,0,width=W,height=H,preserveAspectRatio=False,mask='auto'); y=H-(218 if idx==1 else 154)
        if idx==1:
            y=draw_text(c,f'Nº do Pedido de Pacificação:   PF-DICOR-{channel.id%1000000:06d}',45,y,W-90,10.8,True,1)-16; y=draw_text(c,f'Data de Expedição:      {now()}',45,y,W-90,10.5,False,1)-16; y=draw_text(c,f'Nº do Processo:   PF-DICOR-{channel.id}',45,y,W-90,10.5,True,1)-22
        c.setFont('Courier-Bold',11.5); c.drawString(45,y,f'{code}. {title.upper()}'); y-=23; rows=by.get(code,[])
        if not rows:y=draw_text(c,'Nenhum registro encontrado nesta seção.',45,y,W-90,9.3,False,3)
        else:
            for r in rows[:18]:
                y=draw_text(c,f'[{r["date"]}] {r["author"]}',45,y,W-90,7.8,True,1)-2; y=draw_text(c,r['content'] or '[mídia sem texto]',55,y,W-100,8.8,False,5)-5
                if y<105:break
        c.showPage()
    c.save(); return out

def install(bot):
    core=Core(bot)
    client=bot.bot
    client.add_listener(core.on_message,'on_message')
    try:
        client.add_view(BOView(core,''))
        client.add_view(PericiaView(core,''))
    except Exception:
        traceback.print_exc()
    async def ready():
        if not core.recovered: asyncio.create_task(core.recover(),name='dicor-v600-recover')
    client.add_listener(ready,'on_ready')
    async def dossie(i):
        if not await ack(i):return
        try:
            p=await generate_doc(i.channel); await respond(i,f'✅ Dossiê V600 gerado: `{p.name}`')
            if isinstance(i.channel,(discord.TextChannel,discord.Thread)): await i.channel.send(file=discord.File(str(p)))
        except Exception as e:
            traceback.print_exc(); await respond(i,f'❌ Falha no dossiê: {type(e).__name__}: {e}')
    try: client.tree.add_command(app_commands.Command(name='dossiev600',description='Gera o dossiê operacional da mesa atual',callback=dossie))
    except Exception as e: print(f'⚠️ V600 comando dossiev600: {type(e).__name__}: {e}',flush=True)
