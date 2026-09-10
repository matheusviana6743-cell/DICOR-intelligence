# -*- coding: utf-8 -*-
"""DICOR V304 - gerador de documento de mesa.

Motor novo e independente. Mantem a interface esperada pelo bot, mas usa
um template visual fixo para reproduzir o modelo aprovado e somente escreve
os dados variaveis sobre ele. Fonte: tarefas, topicos, mensagens, anexos e
registros estruturados da mesa.
"""
from __future__ import annotations
import base64, io, json, re, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from PIL import Image as PILImage
from reportlab.pdfgen import canvas
from reportlab.lib import colors

W,H=768,1056
BLACK=colors.HexColor('#161616')
GOLD=colors.HexColor('#AF8739')
TEMPLATE_NAME='dicor_template_v302.b64'
SOURCE_HINTS=('origem','source','canal','channel','channel_name','parent_name')
TITLE_HINTS=('titulo','título','title','nome','name','assunto','subject')
TOPIC_HINTS=('topico','tópico','topic','thread','thread_name','nome_topico','nome_tópico')
CONTENT_HINTS=('conteudo','conteúdo','content','texto','text','mensagem','message','descricao','descrição','description','observacao','observação','resultado','result','valor','value')
TASK_HINTS=('tarefa','task','task_name','nome_tarefa')
AUTHOR_HINTS=('autor','author','autor_nome','author_name','usuario','user','membro')
DATE_HINTS=('data','date','timestamp','created_at','criado_em','created','quando')
RULES={
1:("Foto do painel da organização.",('painel','fotos líderes','fotos lideres','liderança','lideranca')),
2:("Foto dos principais membros da organização.",('fotos dos membros','fotos membros','principais membros','membros','integrantes','gerentes')),
3:("Localização da organização.",('localização','localizacao','coordenadas','endereço','endereco')),
4:("Foto de cima da organização para realizar estratégia de pacificação:",('foto de cima','visão aérea','visao aerea','aérea','aerea','vista aérea','vista aerea')),
5:("Material que vendem.",('material que vendem','materiais','ingredientes base','produtos','mercadorias','vendas')),
6:("Registrar compra do ilícito em frente ou dentro da comunidade/organização.",('registrar compra','compra do ilícito','compra do ilicito','compra','negociação','negociacao')),
7:("Foto do informante da organização.",('informante','foto do informante','informações do informante','informacoes do informante')),
8:("Foto do baú de membros.",('baú de membros','bau de membros','baú membros','bau membros')),
9:("Foto do baú de líder.",('baú de líder','bau de lider','baú líder','bau lider')),
10:("Foto e localização do local de fabricação.",('local de fabricação','local de fabricacao','fabricação','fabricacao','rota de farm','farm')),
11:("Foto e localização do local de produção.",('local de produção','local de producao','produção','producao','rota de produção','rota de producao','escoamento')),
12:("Informações gerais.",('informações gerais','informacoes gerais','informação geral','informacao geral','geral','rádio','radio','crimes da comunidade')),
}

def _norm(v:Any)->str:
 s=str(v or '').casefold()
 for a,b in [('á','a'),('à','a'),('â','a'),('ã','a'),('é','e'),('ê','e'),('í','i'),('ó','o'),('ô','o'),('õ','o'),('ú','u'),('ç','c')]: s=s.replace(a,b)
 return ' '.join(re.sub(r'[^0-9a-z]+',' ',s).split())

def _clean(v:Any)->str:
 if v is None:return ''
 if isinstance(v,str):return v.strip()
 if isinstance(v,(int,float,bool)):return str(v)
 try:return json.dumps(v,ensure_ascii=False,default=str)
 except Exception:return str(v)

def _walk(v:Any,p:str='')->Iterable[Tuple[str,Any]]:
 if isinstance(v,dict):
  yield p,v
  for k,c in v.items(): yield from _walk(c,f'{p}.{k}' if p else str(k))
 elif isinstance(v,(list,tuple,set)):
  for i,c in enumerate(v): yield from _walk(c,f'{p}[{i}]')
 else: yield p,v

def _get(d:Dict[str,Any], aliases:Sequence[str])->str:
 wanted={_norm(x) for x in aliases}
 for k,v in d.items():
  if _norm(k) in wanted and _clean(v): return _clean(v)
 return ''

def _urls(v:Any)->List[str]:
 out=[]
 for _,x in _walk(v):
  if isinstance(x,str): vals=re.findall(r'https?://[^\s<>\]\)]+',x)
  elif isinstance(x,dict): vals=[x.get(k,'') for k in ('url','proxy_url','attachment_url','image_url','thumbnail_url','media_url','video_url')]
  else: vals=[]
  for u in vals:
   if isinstance(u,str) and u.startswith('http'):
    u=u.rstrip('.,);]')
    if u not in out:out.append(u)
 return out

def _image_urls(v:Any)->List[str]:
 out=[];hints=('foto','imagem','image','anexo','attachment','midia','media','thumbnail','embed')
 for p,x in _walk(v):
  hint=_norm(p);cand=[]
  if isinstance(x,str): cand=re.findall(r'https?://[^\s<>\]\)]+',x)
  elif isinstance(x,dict): cand=[x.get(k,'') for k in ('url','proxy_url','attachment_url','image_url','thumbnail_url','media_url')]
  for u in cand:
   if not isinstance(u,str) or not u.startswith('http'): continue
   u=u.rstrip('.,);]'); ext=Path(u.split('?',1)[0]).suffix.casefold()
   if ext in ('.png','.jpg','.jpeg','.webp','.gif','.bmp') or any(h in hint for h in hints):
    if u not in out:out.append(u)
 return out

def _records(dados:Any)->List[Dict[str,Any]]:
 out=[];seen=set()
 for p,obj in _walk(dados):
  if not isinstance(obj,dict): continue
  r={'id':_get(obj,('id','message_id','thread_id','task_id','record_id')),'title':_get(obj,TITLE_HINTS),'topic':_get(obj,TOPIC_HINTS),'task':_get(obj,TASK_HINTS),'source':_get(obj,SOURCE_HINTS),'content':_get(obj,CONTENT_HINTS),'author':_get(obj,AUTHOR_HINTS),'date':_get(obj,DATE_HINTS),'raw':obj,'urls':_urls(obj),'image_urls':_image_urls(obj)}
  if not any((r[k] for k in ('title','topic','task','source','content','author','date','image_urls'))): continue
  sig=r['id'] or p+'|'+r['title']+'|'+r['topic']+'|'+r['content'][:400]
  if sig in seen: continue
  seen.add(sig);out.append(r)
 return out

def _classify(r:Dict[str,Any])->Optional[int]:
 topic=_norm(' '.join((r['task'],r['topic'],r['title'],r['source'])));body=_norm(r['content']);scores={}
 for n,(_,aliases) in RULES.items():
  s=0
  for a in aliases:
   aa=_norm(a)
   if aa and aa in topic:s+=5
   elif aa and aa in body:s+=1
  if s:scores[n]=s
 return max(scores,key=scores.get) if scores else 12

def _meta(records:List[Dict[str,Any]],dados:Any)->Dict[str,str]:
 all_d=[r['raw'] for r in records if isinstance(r.get('raw'),dict)] + ([dados] if isinstance(dados,dict) else [])
 def find(keys):
  for d in all_d:
   v=_get(d,keys)
   if v:return v
  return ''
 ids=[r['id'] for r in records if r['id'].isdigit()]
 ident=next((x for x in ids if len(x)>=6),'MESA')
 return {'pedido':find(('nº do pedido de pacificação','numero do pedido','numero_pedido','pedido','referencia','referência')) or f'INV-{ident[-6:]}','data':find(('data de expedição','data de expedicao','data_expedicao','data')) or datetime.now().strftime('%d/%m/%Y'),'processo':find(('nº do processo','numero processo','numero_processo','processo','protocolo')) or f'PF-DICOR-{ident}','requerente':find(('requerente','solicitante','responsavel','responsável','autoridade')) or 'Polícia Federal - DICOR','local':find(('localização','localizacao','endereco','endereço','local','cidade')) or 'Não informado','organizacao':find(('organização','organizacao','comunidade','grupo','alvo','investigado')) or 'Não identificado'}

def _fmt_date(v:str)->str:
 s=str(v or '');m=re.search(r'(\d{4})[-/](\d{2})[-/](\d{2})',s);return f'{m.group(3)}/{m.group(2)}/{m.group(1)}' if m else s

def _template_bytes()->bytes:
 return base64.b64decode(Path(__file__).with_name(TEMPLATE_NAME).read_text(encoding='utf-8'))

def _template_image(): return PILImage.open(io.BytesIO(_template_bytes())).convert('RGB')

def _draw_bg(c):
 img=_template_image();tmp=io.BytesIO();img.save(tmp,'PNG');tmp.seek(0);c.drawImage(tmp,0,0,width=W,height=H,mask='auto')

def _wrap(text:str,maxchars:int=74)->List[str]:
 lines=[]
 for raw in str(text or '').splitlines() or ['']:
  words=raw.split();cur=''
  if not words:lines.append('');continue
  for word in words:
   cand=(cur+' '+word).strip()
   if len(cand)<=maxchars:cur=cand
   else:
    if cur:lines.append(cur)
    cur=word
  if cur:lines.append(cur)
 return lines

def _block(c,text,x,y,size=11.5,bold=False,leading=17,maxchars=74,limit=28):
 c.setFillColor(BLACK);c.setFont('Courier-Bold' if bold else 'Courier',size)
 for line in _wrap(text,maxchars)[:limit]:c.drawString(x,y,line);y-=leading
 return y

def _label(c,label,x,y):c.setFillColor(BLACK);c.setFont('Courier-Bold',12);c.drawString(x,y,label)

def _download(url,cache)->Optional[Path]:
 cache.mkdir(parents=True,exist_ok=True);p=cache/(str(abs(hash(url)))+'.jpg')
 if p.exists() and p.stat().st_size:return p
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'DICOR-Dossie/304'})
  with urllib.request.urlopen(req,timeout=8) as r:data=r.read(12*1024*1024)
  im=PILImage.open(io.BytesIO(data)).convert('RGB');im.thumbnail((1600,1600));im.save(p,'JPEG',quality=88);return p
 except Exception:return None

def _images(records,cache)->List[Path]:
 urls=[]
 for r in records:
  for u in r['image_urls']:
   if u not in urls:urls.append(u)
 out=[]
 with ThreadPoolExecutor(max_workers=6) as pool:
  fs=[pool.submit(_download,u,cache) for u in urls]
  for f in as_completed(fs):
   try:
    p=f.result()
    if p:out.append(p)
   except Exception:pass
 return out

def _grid(c,paths,x,y,w,h,cols=4):
 if not paths:return
 gap=8;rows=(len(paths)+cols-1)//cols;cw=(w-gap*(cols-1))/cols;ch=(h-gap*(rows-1))/rows
 for i,p in enumerate(paths):
  rr,cc=divmod(i,cols);box=(x+cc*(cw+gap),y+h-(rr+1)*ch-rr*gap,cw,ch)
  try:
   im=PILImage.open(p);iw,ih=im.size;s=min(box[2]/iw,box[3]/ih);dw,dh=iw*s,ih*s;c.drawImage(str(p),box[0]+(box[2]-dw)/2,box[1]+(box[3]-dh)/2,dw,dh,preserveAspectRatio=True,mask='auto')
  except Exception:pass

def _summary(rs):
 dates=[];texts=[]
 for r in rs:
  if r['date']:dates.append(_fmt_date(r['date']))
  for t in (r['content'],r['title'],r['task']):
   if t and t not in texts:texts.append(t)
 return ('; '.join(dict.fromkeys(dates)) or 'Não informado',' '.join(texts) or 'Nenhuma informação textual localizada.',f'Registros vinculados: {len(rs)}.')

def _page1(c,m):
 _draw_bg(c);y=790;c.setFont('Courier-Bold',12.8);c.drawString(39,y,f"N° do Pedido de Pacificação:   {m['pedido']}");y-=32;c.setFont('Courier',12);c.drawString(39,y,f"Data de Expedição:      {_fmt_date(m['data'])}");y-=32;c.setFont('Courier-Bold',12.8);c.drawString(39,y,f"N° do Processo:   {m['processo']}");y-=58;_label(c,'Requerente:',39,y);y-=22;y=_block(c,'• '+m['requerente'],55,y,11.5,leading=17,maxchars=74)-35;_label(c,'Localização:',39,y);y-=22;y=_block(c,'• '+m['requerente']+', por intermédio da Diretoria de Investigação e Combate ao Crime Organizado - DICOR, requer a concessão do presente MANDADO DE PACIFICAÇÃO, visando a manutenção da ordem e o cumprimento das determinações aplicáveis ao procedimento.',55,y,11.5,maxchars=74,limit=8)-8;y=_block(c,'• Dessa forma, solicita-se autorização para proceder com a busca e pacificação no local denominado “'+m['organizacao']+'”, incluindo os pontos e instalações documentados no dossiê operacional.',55,y,11.5,maxchars=74,limit=6);c.showPage()

def _page2(c):
 _draw_bg(c);y=_block(c,'DISPOSIÇÕES DO MANDADO',384,830,14,bold=True,maxchars=60,limit=1)-20
 items=['Fica autorizada a busca em qualquer andar ou sala do estabelecimento, bem como nos veículos pessoais pertencentes aos investigados.','Nenhum documento ou objeto pertencente a terceiros, familiares ou residentes, presentes no momento da operação, deverá ser apreendido.','Deverá ser solicitada a presença de um representante da OAC (Advogado(a)), conforme previsto no Art. 7º, §6º, da Lei nº 8.906/1994.','Caso sejam identificados materiais probatórios adicionais relevantes, deverá ser requerida expressamente a extensão da busca.','Fica autorizado o arrombamento de cofres, baús, porta-malas e demais compartimentos caso não sejam voluntariamente abertos.','O(s) investigado(s) detido(s) deverá(ão) ser apresentado(s) imediatamente à Autoridade Civil competente.']
 for t in items:c.drawString(39,y,'•');y=_block(c,t,55,y,11.7,maxchars=74,limit=5)-4
 c.showPage()

def _page3(c,records):
 _draw_bg(c);y=_block(c,'PLANEJAMENTO OPERACIONAL',384,830,14,bold=True,maxchars=60,limit=1)-20;y=_block(c,'Para garantir o sucesso da pacificação, a operação contará com:',39,y,12,bold=True,maxchars=74,limit=2)-8
 groups=[('Efetivo envolvido:',('efetivo','equipe','agente','membro')),('Recursos utilizados:',('recurso','viatura','drone','helicoptero','helicóptero')),('Estratégia de abordagem:',('estrategia','estratégia','abordagem','setor','acesso')),('Medidas serão tomadas pra proteger a população local, incluindo:',('proteção','protecao','morador','medica','médica','oab','direitos humanos'))]
 for label,keys in groups:
  _label(c,label,39,y);y-=20;vals=[r['content'] for r in records if r['content'] and any(_norm(k) in _norm(r['content']) for k in keys)]
  if not vals:vals=['Informações não localizadas nas tarefas ou mensagens.']
  for v in list(dict.fromkeys(vals))[:4]:c.drawString(39,y,'•');y=_block(c,v,55,y,11.2,maxchars=74,limit=3)-4
  y-=7
 c.showPage()

def _page4(c):
 _draw_bg(c);y=_block(c,'PROVAS E DOCUMENTAÇÕES',39,820,14,bold=True,maxchars=60,limit=1)-18;y=_block(c,'As provas e documentações gerais relativas ao processo serão anexadas ao mandado e permanecerão de uso restrito das autoridades competentes. Todas as evidências foram obtidas por meio dos registros da mesa operacional e documentadas para comprovar a necessidade da incursão.',39,y,11.3,maxchars=76,limit=7);c.showPage()

def _evidence(c,n,rs,imgs):
 _draw_bg(c);y=_block(c,f'{n}. {RULES[n][0]}',39,815,12.2,bold=True,maxchars=75,limit=2)-8;date,desc,rel=_summary(rs)
 for label,val in [('Data e Local:',date),('Descrição:',desc),('Relação com o Processo:',rel),('Mídia de Apoio:',f'{len(imgs)} mídia(s) incorporada(s).' if imgs else 'Nenhuma mídia localizada.')]:
  _label(c,label,39,y);y-=20;y=_block(c,'• '+val,55,y,11.1,maxchars=74,limit=5)-6
 if imgs:_grid(c,imgs,39,105,691,310,4)
 c.showPage()

def _panel(c,rs,imgs):
 _draw_bg(c);y=815;_label(c,'Mídia de Apoio:',39,y);y-=42;_label(c,'Líder:',39,y);y-=22;lines=[]
 for r in rs:
  for ln in r['content'].splitlines():
   if re.search(r'RG\s*[:=-]\s*\d+',ln,re.I):lines.append(ln.strip(' •'))
 y=_block(c,'• '+(lines[0] if lines else 'Não identificado'),55,y,11.2,maxchars=72,limit=2)-25;_label(c,'Gerentes:',39,y);y-=22
 for ln in list(dict.fromkeys(lines[1:]))[:12]:c.drawString(55,y,'•');y=_block(c,ln,72,y,10.7,maxchars=60,limit=1)-3
 c.showPage();_draw_bg(c);c.setFont('Courier',12.5);c.drawString(39,820,'Painel:')
 if imgs:_grid(c,imgs[:1],150,105,520,660,1)
 c.showPage()

def _motivation(c,rs):
 _draw_bg(c);y=_block(c,'MOTIVAÇÃO',384,830,14,bold=True,maxchars=60,limit=1)-18;vals=[r['content'] for r in rs if r['content'] and any(k in _norm(r['content']) for k in ('art','tráfico','trafico','quadrilha','ameaça','violencia','violência','prisao','prisão','controle territorial'))]
 if not vals:vals=['A motivação será consolidada diretamente dos registros da mesa operacional.']
 for v in list(dict.fromkeys(vals))[:14]:c.drawString(39,y,'•');y=_block(c,v,55,y,11.2,maxchars=74,limit=4)-4
 c.showPage()

def _end(c,m):
 _draw_bg(c);y=_block(c,'PROVAS E DOCUMENTAÇÕES',39,820,14,bold=True,maxchars=60,limit=1)-18;y=_block(c,'Com base nas provas apresentadas, solicitamos a manutenção do mandado de pacificação e a adoção das medidas necessárias para garantir a segurança pública na região documentada.',39,y,11.2,maxchars=74,limit=6)-35;_label(c,'DELEGADO RESPONSÁVEL:',39,y);y-=25;y=_block(c,m['requerente'],39,y,11.2,maxchars=74,limit=2)-28;c.setFont('Courier-BoldOblique',10.5);c.drawString(39,y,'DIRETORIA DE INVESTIGAÇÃO E COMBATE AO CRIME ORGANIZADO - DICOR');y-=70;c.setFont('Courier-Bold',11);c.drawCentredString(215,y,'RESPONSÁVEL PELA CONSOLIDAÇÃO');c.drawCentredString(560,y,'AUTORIDADE DICOR');y-=30;c.setFont('Courier',11);c.drawCentredString(215,y,'____________________________');c.drawCentredString(560,y,'____________________________');c.showPage()

def gerar_pdf_dossie(bot_module:Any,dados:Any,caminho:Any)->str:
 target=Path(caminho);target.parent.mkdir(parents=True,exist_ok=True);records=_records(dados);sections={n:[] for n in RULES}
 for r in records:sections[_classify(r) or 12].append(r)
 m=_meta(records,dados);cache=target.parent/'.dossie_media_v304';c=canvas.Canvas(str(target),pagesize=(W,H),pageCompression=1,title=f"Dossiê Operacional — {m['organizacao']}",author='POLÍCIA FEDERAL - DICOR')
 _page1(c,m);_page2(c);_page3(c,records);_page4(c);imgs={n:_images(sections[n],cache) for n in sections};_panel(c,sections[1],imgs[1]);_evidence(c,2,sections[2],imgs[2]);
 for n in (3,4,5,6,7,8,9,10,11):_evidence(c,n,sections[n],imgs[n])
 _motivation(c,sections[12]);_end(c,m);c.save();return str(target)

def gerar_pdf(bot_module:Any,dados:Any,caminho:Any)->str:return gerar_pdf_dossie(bot_module,dados,caminho)

def install(bot_module:Any)->None:print('✅ V304 Dossiê instalado — template visual fixo PF/DICOR + coleta de tarefas/tópicos/mensagens/mídias.',flush=True)
