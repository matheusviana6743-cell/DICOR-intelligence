# -*- coding: utf-8 -*-
"""DICOR Core V600: BO, Pericia e Dossie sem depender dos patches antigos."""
from __future__ import annotations
import asyncio, base64, io, json, os, re, traceback, urllib.request
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
    Image = None
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase.pdfmetrics import stringWidth
except Exception:
    canvas = None; ImageReader = None; stringWidth = None

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
def safe_name(s): return re.sub(r'[^0-9A-Za-zÀ-ÿ._ -]','_',str(s or 'arquivo'))[:100]
def text_of(m):
    p=[]
    if getattr(m,'content',None): p.append(m.content)
    for e in getattr(m,'embeds',[]) or []:
        if e.title:p.append(e.title)
        if e.description:p.append(e.description)
        for f in getattr(e,'fields',[]) or []: p.extend([str(f.name or ''),str(f.value or '')])
    return '\n'.join(x for x in p if x).strip()
def authorized(member):
    return any(getattr(r,'id',0) in AUTH_ROLE_IDS for r in getattr(member,'roles',[])) or any('inspetor' in norm(getattr(r,'name','')) or 'diretor' in norm(getattr(r,'name','')) for r in getattr(member,'roles',[]))
def team_member(member):
    if any(getattr(r,'id',0) in TEAM_ROLE_IDS for r in getattr(member,'roles',[])): return True
    keys=('estagi','investigador','inspetor','agente','delegado','dicor','escriv')
    return any(any(k in norm(getattr(r,'name','')) for k in keys) for r in getattr(member,'roles',[]))
def extract_number(s,label):
    for p in (rf'{label}[^0-9]{{0,30}}(?:N[º°O.]?\s*)?(\d{{1,8}})',r'N[º°O.]?\s*(\d{1,8})',r'#\s*(\d{1,8})'):
        m=re.search(p,str(s or ''),re.I)
        if m:return f'{int(m.group(1)):04d}'
    return ''
def next_number(kind,mo):
    d=load_state(); c=d.setdefault('counters',{}).setdefault(kind,{}); n=int(c.get(mo,0))+1; c[mo]=n; save_state(d); return f'{n:04d}'
def records(kind):
    d=load_state(); x=d.get(kind,[]); return x if isinstance(x,list) else []
def append_record(kind,r):
    d=load_state(); d.setdefault(kind,[]).append(r); save_state(d)
def update_record(kind,rid,patch):
    d=load_state()
    for r in d.get(kind,[]):
        if str(r.get('id'))==str(rid): r.update(patch); save_state(d); return r
    return None
def find_source(kind,message_id): return next((r for r in records(kind) if str(r.get('source_message_id'))==str(message_id)),None)
async def log(bot,msg):
    try:
        ch=bot.get_channel(LOG_ID)
        if ch: await ch.send(str(msg)[:1900])
    except Exception: pass
async def respond(i,content,view=None):
    try:
        if i.response.is_done(): await i.followup.send(content,view=view,ephemeral=True)
        else: await i.response.send_message(content,view=view,ephemeral=True)
    except Exception: pass
async def ack(i):
    try:
        if not i.response.is_done(): await i.response.defer(ephemeral=True,thinking=True)
        return True
    except Exception:return False

class Core:
    def __init__(self,bot): self.bot=bot; self.bo_locks=set(); self.pericia_locks=set(); self.running=False
    async def channel(self,guild,cid):
        c=guild.get_channel(cid)
        if c is None:
            try:c=await guild.fetch_channel(cid)
            except Exception:return None
        return c
    async def choose_agent(self,guild,kind):
        cs=[m for m in guild.members if not m.bot and team_member(m) and not authorized(m)] or [m for m in guild.members if not m.bot and team_member(m)]
        if not cs:return None
        d=load_state(); key=f'{kind}_rr'; cur=d.setdefault(key,{}); mo=datetime.now().strftime('%m/%Y'); idx=int(cur.get(mo,0))%len(cs); cur[mo]=idx+1; save_state(d)
        return sorted(cs,key=lambda m:(m.display_name.casefold(),m.id))[idx]
    async def bo(self,msg):
        if not msg.guild or msg.author.bot or msg.channel.id!=SOURCE_BO_ID or msg.id in self.bo_locks:return
        self.bo_locks.add(msg.id)
        try:
            if find_source('bo',msg.id):return
            txt=text_of(msg)
            if 'boletim de ocorr' not in norm(txt) and not msg.embeds:return
            mo=month(msg.created_at); num=extract_number(txt,'boletim') or next_number('bo',mo)
            used={r.get('number') for r in records('bo') if r.get('month')==mo}
            while num in used:num=next_number('bo',mo)
            parent=await self.channel(msg.guild,TARGET_BO_ID)
            if not isinstance(parent,discord.TextChannel):raise RuntimeError('canal de atendimento de BO não encontrado')
            agent=await self.choose_agent(msg.guild,'bo')
            th=await parent.create_thread(name=f'📋 BOLETIM DE OCORRÊNCIA — Nº {num}',type=discord.ChannelType.private_thread,invitable=False,auto_archive_duration=10080,reason='DICOR V600 BO')
            if agent: await th.add_user(agent)
            em=discord.Embed(title='📋 BOLETIM DE OCORRÊNCIA',description=txt[:4000] or 'Sem texto.')
            em.add_field(name='Número',value=f'`{num}`',inline=True); em.add_field(name='Responsável',value=agent.mention if agent else 'Aguardando seleção',inline=True); em.add_field(name='Origem',value=msg.jump_url,inline=False)
            await th.send(content=agent.mention if agent else None,embed=em,allowed_mentions=discord.AllowedMentions(users=True,roles=False,everyone=False))
            for a in msg.attachments or []:
                try: await th.send(file=await a.to_file(use_cached=True))
                except Exception: await th.send(a.url)
            rid=f'BO-{msg.id}'; append_record('bo',{'id':rid,'number':num,'month':mo,'source_message_id':msg.id,'source_channel_id':SOURCE_BO_ID,'thread_id':th.id,'agent_id':agent.id if agent else None,'status':'EM_ATENDIMENTO' if agent else 'SEM_AGENTE','created_at':now()})
            await th.send(view=BOView(self,rid)); await log(self.bot,f'✅ V600 BO criado: {num} -> {th.id}')
        finally:self.bo_locks.discard(msg.id)
    async def pericia(self,msg):
        if not msg.guild or msg.author.bot or msg.channel.id!=SOURCE_PERICIA_ID or msg.id in self.pericia_locks:return
        self.pericia_locks.add(msg.id)
        try:
            if find_source('pericia',msg.id):return
            txt=text_of(msg); mo=month(msg.created_at); num=extract_number(txt,'pericia') or next_number('pericia',mo)
            parent=await self.channel(msg.guild,SOURCE_PERICIA_ID)
            if not isinstance(parent,discord.TextChannel):raise RuntimeError('canal de perícia externa não encontrado')
            th=await parent.create_thread(name=f'🔬 PERÍCIA Nº {num} • AGUARDANDO AGENTE',type=discord.ChannelType.private_thread,invitable=False,auto_archive_duration=10080,reason='DICOR V600 Perícia')
            for a in msg.attachments or []:
                try:await th.send(file=await a.to_file(use_cached=True))
                except Exception:await th.send(a.url)
            rid=f'PERICIA-{msg.id}'; append_record('pericia',{'id':rid,'number':num,'month':mo,'source_message_id':msg.id,'source_channel_id':SOURCE_PERICIA_ID,'thread_id':th.id,'agent_id':None,'status':'AGUARDANDO_AGENTE','attachments':len(msg.attachments or []),'created_at':now()})
            await th.send(embed=discord.Embed(title=f'🔬 CONTROLE DA PERÍCIA EXTERNA — Nº {num}',description='Um Inspetor+ deve selecionar o agente responsável abaixo.'),view=PericiaView(self,rid)); await log(self.bot,f'✅ V600 Perícia criada: {num} -> {th.id}')
        finally:self.pericia_locks.discard(msg.id)
    async def recover(self):
        if self.running:return
        self.running=True; await asyncio.sleep(4)
        for g in self.bot.guilds:
            for cid,fn in ((SOURCE_BO_ID,self.bo),(SOURCE_PERICIA_ID,self.pericia)):
                ch=g.get_channel(cid)
                if isinstance(ch,discord.TextChannel):
                    try:
                        async for m in ch.history(limit=3000,oldest_first=True): await fn(m)
                    except Exception:traceback.print_exc()
        print('✅ DICOR V600: recuperação concluída',flush=True)
    async def on_message(self,msg):
        if msg.guild and not msg.author.bot:
            if msg.channel.id==SOURCE_BO_ID: await self.bo(msg)
            elif msg.channel.id==SOURCE_PERICIA_ID: await self.pericia(msg)

class BOView(View):
    def __init__(self,core,rid):
        super().__init__(timeout=None); self.core=core; self.rid=rid; self.add_item(BOAgentSelect(core,rid)); b=Button(label='Finalizar BO',emoji='✅',style=discord.ButtonStyle.success,custom_id='dicor_v600_bo_done'); b.callback=self.done; self.add_item(b)
    async def done(self,i):
        if not await ack(i):return
        if not isinstance(i.user,discord.Member) or not authorized(i.user):return await respond(i,'❌ Apenas Inspetor+ pode finalizar.')
        r=self.core._find_live('bo',self.rid)
        if r:update_record('bo',self.rid,{'status':'FINALIZADO','closed_at':now()}); await respond(i,'✅ BO finalizado.')
class BOAgentSelect(UserSelect):
    def __init__(self,core,rid):super().__init__(placeholder='Inspetor+: selecione o agente',min_values=1,max_values=1,custom_id='dicor_v600_bo_agent'); self.core=core; self.rid=rid
    async def callback(self,i):
        if not isinstance(i.user,discord.Member) or not authorized(i.user):return await respond(i,'❌ Apenas Inspetor+ pode alterar o responsável.')
        if not await ack(i):return
        m=self.values[0] if self.values else None
        if not isinstance(m,discord.Member) or not team_member(m):return await respond(i,'❌ Membro inválido.')
        r=self.core._find_by_thread('bo',getattr(i.channel,'id',0))
        if not r:return await respond(i,'❌ Atendimento não encontrado.')
        update_record('bo',r['id'],{'agent_id':m.id,'agent_name':str(m),'status':'EM_ATENDIMENTO'})
        try: await i.channel.add_user(m); await i.channel.send(f'📌 {m.mention} foi definido como responsável.')
        except Exception:pass
        await respond(i,f'✅ {m.mention} agora é o responsável.')
class PericiaView(View):
    def __init__(self,core,rid):
        super().__init__(timeout=None); self.core=core; self.rid=rid; self.add_item(PericiaAgentSelect(core,rid)); b=Button(label='Marcar concluída',emoji='✅',style=discord.ButtonStyle.success,custom_id='dicor_v600_pericia_done'); b.callback=self.done; self.add_item(b)
    async def done(self,i):
        if not await ack(i):return
        if not isinstance(i.user,discord.Member) or not authorized(i.user):return await respond(i,'❌ Apenas Inspetor+ pode concluir.')
        r=self.core._find_by_thread('pericia',getattr(i.channel,'id',0))
        if r:update_record('pericia',r['id'],{'status':'CONCLUIDA','closed_at':now()}); await respond(i,'✅ Perícia concluída.')
class PericiaAgentSelect(UserSelect):
    def __init__(self,core,rid):super().__init__(placeholder='Inspetor+: selecione o agente responsável',min_values=1,max_values=1,custom_id='dicor_v600_pericia_agent'); self.core=core; self.rid=rid
    async def callback(self,i):
        if not isinstance(i.user,discord.Member) or not authorized(i.user):return await respond(i,'❌ Apenas Inspetor+ pode escolher o responsável.')
        if not await ack(i):return
        m=self.values[0] if self.values else None
        if not isinstance(m,discord.Member) or not team_member(m):return await respond(i,'❌ Selecione um membro da equipe DICOR.')
        r=self.core._find_by_thread('pericia',getattr(i.channel,'id',0))
        if not r:return await respond(i,'❌ Perícia não encontrada.')
        update_record('pericia',r['id'],{'agent_id':m.id,'agent_name':str(m),'status':'PENDENTE'})
        try: await i.channel.add_user(m); await i.channel.send(f'📌 {m.mention}\n**TAREFA DE PERÍCIA ATRIBUÍDA**\nVocê é o responsável pela Perícia Nº {r["number"]}.')
        except Exception:pass
        await respond(i,f'✅ {m.mention} foi definido como responsável pela Perícia Nº **{r["number"]}**.')

DOC_SECTIONS=[('01','Painel da organização'),('02','Fotos dos membros'),('03','Localização'),('04','Foto de cima da organização'),('05','Materiais que vendem'),('06','Registro de compra'),('07','Informante'),('08','Baú de membros'),('09','Baú de líder'),('10','Local de fabricação'),('11','Local de produção'),('12','Informações gerais'),('13','Assinaturas'),('14','Análise consolidada'),('15','Evidências adicionais'),('16','Cronologia'),('17','Conclusões'),('18','Encerramento')]
def template_png():
    if TEMPLATE.exists() and TEMPLATE.stat().st_size>10000:return TEMPLATE
    raw=''.join(TEMPLATE_B64.read_text(encoding='utf-8').split()); data=base64.b64decode(raw,validate=True); TEMPLATE.write_bytes(data); return TEMPLATE
def wrap(txt,size,width):
    txt=re.sub(r'(?:/tmp|/mnt)/[^\s]+','',str(txt or '')).strip(); out=[]; cur=''
    for w in txt.split():
        c=w if not cur else cur+' '+w
        if stringWidth(c,'Courier',size)<=width:cur=c
        else:
            if cur:out.append(cur)
            cur=w
    if cur:out.append(cur)
    return out
def draw_text(c,txt,x,y,w,size=9.5,bold=False,lines=18):
    font='Courier-Bold' if bold else 'Courier'; c.setFont(font,size)
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
                r={'thread':t.name,'thread_id':t.id,'author':str(m.author),'date':m.created_at.strftime('%d/%m/%Y %H:%M'),'content':text_of(m),'attachments':[{'url':a.url,'filename':a.filename} for a in m.attachments]}
                by[section_code(t.name+' '+r['content'])].append(r)
        except Exception:traceback.print_exc()
    return by
async def generate_doc(bot,channel):
    if canvas is None:raise RuntimeError('ReportLab indisponível')
    by=await collect_dossier(channel); bg=template_png(); out=DOCS/f'PF-DICOR-{channel.id}-{datetime.now().strftime("%Y%m%d-%H%M%S")}.pdf'; W,H=A4; c=canvas.Canvas(str(out),pagesize=A4)
    for idx,(code,title) in enumerate(DOC_SECTIONS,1):
        c.drawImage(ImageReader(str(bg)),0,0,width=W,height=H,preserveAspectRatio=False,mask='auto'); y=H-(220 if idx==1 else 155)
        if idx==1:
            y=draw_text(c,f'Nº do Pedido de Pacificação:   PF-DICOR-{channel.id%1000000:06d}',45,y,W-90,11,True,1)-18; y=draw_text(c,f'Data de Expedição:      {now()}',45,y,W-90,10.8,False,1)-18; y=draw_text(c,f'Nº do Processo:   PF-DICOR-{channel.id}',45,y,W-90,10.8,True,1)-24
        c.setFont('Courier-Bold',12); c.drawString(45,y,f'{code}. {title.upper()}'); y-=24; rows=by.get(code,[])
        if not rows:y=draw_text(c,'Nenhum registro encontrado nesta seção.',45,y,W-90,9.5,False,3)
        else:
            for r in rows[:20]:
                y=draw_text(c,f'[{r["date"]}] {r["author"]}',45,y,W-90,8.2,True,1)-2; y=draw_text(c,r['content'] or '[mídia sem texto]',55,y,W-100,9.0,False,5)-5
                if y<100:break
        c.showPage()
    c.save(); return out

# Helper methods added to Core after class definition.
Core._find_live=lambda self,kind,rid: next((r for r in records(kind) if str(r.get('id'))==str(rid)),None)
Core._find_by_thread=lambda self,kind,thread_id: next((r for r in records(kind) if str(r.get('thread_id'))==str(thread_id)),None)

def bind_core(bot):
    core=Core(bot); bot.add_listener(core.on_message,'on_message')
    try:
        bot.add_view(BOView(core,'')); bot.add_view(PericiaView(core,''))
    except Exception: pass
    async def ready():
        if not getattr(core,'_recovery_done',False):
            core._recovery_done=True; asyncio.create_task(core.recover(),name='dicor-v600-recover')
    bot.add_listener(ready,'on_ready')
    async def dossie(i):
        if not await ack(i):return
        try:
            p=await generate_doc(bot,i.channel); await respond(i,f'✅ Dossiê V600 gerado: `{p.name}`');
            if isinstance(i.channel,(discord.TextChannel,discord.Thread)): await i.channel.send(file=discord.File(str(p)))
        except Exception as e: traceback.print_exc(); await respond(i,f'❌ Falha no documento: {type(e).__name__}: {e}')
    try:bot.tree.add_command(app_commands.Command(name='dossiev600',description='Gera o dossiê operacional da mesa atual',callback=dossie))
    except Exception:pass
    return core

def install(bot):
    return bind_core(bot)
