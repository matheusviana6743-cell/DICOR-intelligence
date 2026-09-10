# -*- coding: utf-8 -*-
"""DICOR V307 — gerador novo e independente de documentos de mesa.
Layout fixo do modelo aprovado; dados preenchidos por tarefas, tópicos,
mensagens e mídias. Sem ReportLab/Platypus, evitando erros de renderização.
"""
from __future__ import annotations
import base64,io,json,re,urllib.request
from pathlib import Path
from typing import Any
import fitz
from PIL import Image

W,H=768,1056
TEMPLATE='dicor_template_v302.b64'
FONT='Courier';BOLD='Courier-Bold'
RULES={1:('Foto do painel da organização.',('painel','fotos líderes','fotos lideres','liderança','lideranca')),2:('Foto dos principais membros da organização.',('fotos dos membros','fotos membros','principais membros','membros','integrantes','gerentes')),3:('Localização da organização.',('localização','localizacao','coordenadas','endereço','endereco')),4:('Foto de cima da organização para realizar estratégia de pacificação:',('foto de cima','visão aérea','visao aerea','aérea','aerea','vista aérea','vista aerea')),5:('Material que vendem.',('material que vendem','materiais','ingredientes base','produtos','mercadorias','vendas')),6:('Registrar compra do ilícito em frente ou dentro da comunidade/organização.',('registrar compra','compra do ilícito','compra do ilicito','compra','negociação','negociacao')),7:('Foto do informante da organização.',('informante','foto do informante','informações do informante','informacoes do informante')),8:('Foto do baú de membros.',('baú de membros','bau de membros','baú membros','bau membros')),9:('Foto do baú de líder.',('baú de líder','bau de lider','baú líder','bau lider')),10:('Foto e localização do local de fabricação.',('local de fabricação','local de fabricacao','fabricação','fabricacao','rota de farm','farm')),11:('Foto e localização do local de produção.',('local de produção','local de producao','produção','producao','rota de produção','rota de producao','escoamento')),12:('Informações gerais.',('informações gerais','informacoes gerais','informação geral','informacao geral','geral','rádio','radio','crimes da comunidade'))}

def norm(v):
 s=str(v or '').casefold();
 for a,b in {'á':'a','à':'a','â':'a','ã':'a','é':'e','ê':'e','í':'i','ó':'o','ô':'o','õ':'o','ú':'u','ç':'c'}.items():s=s.replace(a,b)
 return ' '.join(re.sub(r'[^0-9a-z]+',' ',s).split())

def clean(v):
 if v is None:return ''
 if isinstance(v,str):return v.strip()
 if isinstance(v,(int,float,bool)):return str(v)
 try:return json.dumps(v,ensure_ascii=False,default=str)
 except:return str(v)

def walk(v):
 if isinstance(v,dict):
  yield '',v
  for k,c in v.items():
   for p,x in walk(c):yield f'{k}.{p}'.rstrip('.'),x
 elif isinstance(v,(list,tuple,set)):
  for i,c in enumerate(v):
   for p,x in walk(c):yield f'[{i}].{p}',x

def pick(d,keys):
 wanted={norm(k) for k in keys}
 for k,v in d.items():
  if norm(k) in wanted and clean(v):return clean(v)
 return ''

def records(dados):
 out=[];seen=set()
 for path,obj in walk(dados):
  if not isinstance(obj,dict):continue
  r={'path':path,'id':pick(obj,('id','message_id','thread_id','task_id','record_id')),'task':pick(obj,('tarefa','task','task_name','nome_tarefa')),'topic':pick(obj,('topico','tópico','topic','thread','thread_name','nome_topico','nome_tópico')),'title':pick(obj,('titulo','título','title','nome','name','assunto','subject')),'source':pick(obj,('origem','source','canal','channel','channel_name','parent_name')),'content':pick(obj,('conteudo','conteúdo','content','texto','text','mensagem','message','descricao','descrição','description','observacao','observação','valor','value','resultado','result')),'author':pick(obj,('autor','author','autor_nome','author_name','usuario','user','membro')),'date':pick(obj,('data','date','timestamp','created_at','criado_em','created','quando')),'raw':obj,'urls':[]}
  for _,x in walk(obj):
   if isinstance(x,str):
    for u in re.findall(r'https?://[^\s<>\]\)]+',x):
     u=u.rstrip('.,);]')
     if u not in r['urls']:r['urls'].append(u)
   elif isinstance(x,dict):
    for k in ('url','proxy_url','attachment_url','image_url','thumbnail_url','media_url','video_url'):
     u=x.get(k)
     if isinstance(u,str) and u.startswith('http') and u not in r['urls']:r['urls'].append(u)
  sig=r['id'] or (path,r['task'],r['topic'],r['title'],r['content'][:500])
  if sig in seen:continue
  seen.add(sig)
  if any(r[k] for k in ('task','topic','title','source','content','author','date','urls')):out.append(r)
 return out

def classify(r):
 h=norm(' '.join((r['task'],r['topic'],r['title'],r['source'])));b=norm(r['content']);best=12;score=0
 for n,(_,als) in RULES.items():
  s=sum(6 if norm(a) in h else 1 if norm(a) in b else 0 for a in als)
  if s>score:score,best=s,n
 return best

def wrap(t,n=74):
 out=[];t=re.sub(r'/tmp/[^\s]+','',str(t or ''))
 for p in t.splitlines() or ['']:
  cur=''
  for w in p.split():
   c=(cur+' '+w).strip()
   if len(c)<=n:cur=c
   else:
    if cur:out.append(cur)
    cur=w
  if cur:out.append(cur)
 return out

def text(p,t,x,y,size=11.5,bold=False,maxchars=74,lines=8,leading=17):
 f=BOLD if bold else FONT
 for s in wrap(t,maxchars)[:lines]:p.insert_text((x,y),s,fontsize=size,fontname=f,color=(0,0,0));y+=leading
 return y

def field(p,label,value,y,size=11.2,lines=5):
 p.insert_text((39,y),label,fontsize=12,fontname=BOLD,color=(0,0,0));return text(p,value,55,y+20,size,False,74,lines)

def bg(doc,tpl):
 p=doc.new_page(width=W,height=H);p.insert_image(p.rect,stream=tpl);return p

def media(rs):
 out=[]
 for r in rs:
  hint=norm(r['task']+' '+r['topic']+' '+r['title'])
  for u in r['urls']:
   if u not in out and (Path(u.split('?',1)[0]).suffix.lower() in ('.png','.jpg','.jpeg','.webp','.gif','.bmp') or any(k in hint for k in ('foto','imagem','informante','painel','membro','bau','localizacao','fabricacao','producao'))):out.append(u)
 return out

def add_image(p,url,rect):
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'DICOR-V307'})
  with urllib.request.urlopen(req,timeout=7) as r:data=r.read(10*1024*1024)
  im=Image.open(io.BytesIO(data)).convert('RGB');bio=io.BytesIO();im.save(bio,'PNG');p.insert_image(fitz.Rect(*rect),stream=bio.getvalue(),keep_proportion=True);return True
 except:return False

def generate(bot_module:Any,dados:Any,caminho:Any)->str:
 rs=records(dados);sec={n:[] for n in RULES}
 for r in rs:sec[classify(r)].append(r)
 def first(keys,default):
  for r in rs:
   v=pick(r['raw'],keys)
   if v:return v
  return default
 ident=next((r['id'] for r in rs if str(r['id']).isdigit()),'MESA')
 m={'pedido':first(('nº do pedido de pacificação','numero do pedido','numero_pedido','pedido'),f'INV-{str(ident)[-6:]}'),'data':first(('data de expedição','data de expedicao','data_expedicao','data'),'Não informado'),'processo':first(('nº do processo','numero processo','numero_processo','processo'),f'PF-DICOR-{ident}'),'requerente':first(('requerente','solicitante','responsavel','responsável','autoridade'),'Polícia Federal - DICOR'),'local':first(('localização','localizacao','endereco','endereço','local','cidade'),'Não informado'),'organizacao':first(('organização','organizacao','comunidade','grupo','alvo','investigado'),'Não identificado')}
 tpl=base64.b64decode(Path(__file__).with_name(TEMPLATE).read_text(encoding='utf-8').strip());doc=fitz.open()
 # 1
 p=bg(doc,tpl);text(p,f'N° do Pedido de Pacificação:   {m["pedido"]}',39,438,12,True,74,1);text(p,f'Data de Expedição:      {m["data"]}',39,470,12,False,74,1);text(p,f'N° do Processo:   {m["processo"]}',39,502,12,True,74,1);text(p,'Requerente:',39,560,12,True,74,1);text(p,'• '+m['requerente'],55,590,11.5,False,74,2);text(p,'Localização:',39,648,12,True,74,1);text(p,f'• {m["requerente"]}, por intermédio da Diretoria de Investigação e Combate ao Crime Organizado - DICOR, requer a concessão do presente MANDADO DE PACIFICAÇÃO, visando a manutenção da ordem e o cumprimento das determinações aplicáveis ao procedimento.\n• Dessa forma, solicita-se autorização para proceder com a busca e pacificação no local denominado “{m["organizacao"]}”, incluindo os pontos e instalações documentados no dossiê operacional.',55,682,11.5,False,74,10)
 # 2
 p=bg(doc,tpl);text(p,'DISPOSIÇÕES DO MANDADO',384,221,14,True,60,1);disp=['Fica autorizada a busca em qualquer andar ou sala do estabelecimento, bem como nos veículos pessoais pertencentes aos investigados.','Nenhum documento ou objeto pertencente a terceiros, familiares ou residentes, presentes no momento da operação, deverá ser apreendido.','Deverá ser solicitada a presença de um representante da OAC (Advogado(a)), conforme previsto no Art. 7º, §6º, da Lei nº 8.906/1994.','Caso sejam identificados materiais probatórios adicionais relevantes, deverá ser requerida expressamente a extensão da busca.','Fica autorizado o arrombamento de cofres, baús, porta-malas e demais compartimentos caso não sejam voluntariamente abertos.','O(s) investigado(s) detido(s) deverá(ão) ser apresentado(s) imediatamente à Autoridade Civil competente.'];text(p,'\n'.join('• '+x for x in disp),39,270,11.7,False,74,28)
 # 3
 p=bg(doc,tpl);text(p,'PLANEJAMENTO OPERACIONAL',384,221,14,True,60,1);text(p,'Para garantir o sucesso da pacificação, a operação contará com:',39,270,12,True,74,2);y=325
 for label,keys in [('Efetivo envolvido:',('efetivo','equipe','agente','membro')),('Recursos utilizados:',('recurso','viatura','drone','helicoptero','helicóptero')),('Estratégia de abordagem:',('estrategia','estratégia','abordagem','setor','acesso')),('Medidas serão tomadas pra proteger a população local, incluindo:',('proteção','protecao','morador','oab','direitos humanos'))]:
  text(p,label,39,y,12,True,74,1);y+=22;vals=[r['content'] for r in rs if r['content'] and any(norm(k) in norm(r['content']) for k in keys)];y=text(p,'• '+('; '.join(dict.fromkeys(vals)) if vals else 'Informação conforme registros da mesa.'),55,y,11.2,False,74,4)+9
 # 4
 p=bg(doc,tpl);text(p,'PROVAS E DOCUMENTAÇÕES',39,221,14,True,60,1);text(p,'As provas e documentações gerais relativas ao processo serão anexadas ao mandado e permanecerão de uso restrito das autoridades competentes. Todas as evidências foram obtidas por meio dos registros da mesa operacional e documentadas para comprovar a necessidade da incursão.',39,270,11.5,False,74,7);text(p,'Descrição:',39,415,12,True,74,1);text(p,'• Registros, evidências e informações reunidas diretamente das tarefas, tópicos e mensagens da mesa.',55,445,11.3,False,74,4)
 # 5 liderança
 p=bg(doc,tpl);text(p,'Mídia de Apoio:',39,221,12,True,74,1);entries=[]
 for r in sec[1]:
  for line in r['content'].splitlines():
   z=re.search(r'(.+?)\s*(?:rg\s*[:=-]\s*)(\d+)',line,re.I)
   if z:entries.append(f"{z.group(1).strip(' *:-')}    RG: {z.group(2)}")
 y=270;text(p,'Líder:',39,y,12,True,74,1);y=text(p,'• '+(entries[0] if entries else 'Não identificado'),55,y+25,11.5,False,74,2)+35;text(p,'Gerentes:',39,y,12,True,74,1);text(p,'\n'.join('• '+x for x in entries[1:9]) or '• Não identificado',55,y+25,11.5,False,74,12)
 # 6 painel
 p=bg(doc,tpl);text(p,'Painel:',39,221,12.5,True,74,1);ii=media(sec[1]);
 if ii:add_image(p,ii[0],(205,243,360,650))
 # 7-16
 for n in range(2,12):
  p=bg(doc,tpl);text(p,f'{n}. {SECTIONS[n][0]}',39,221,11.8,True,74,2);rr=sec[n];date='; '.join(dict.fromkeys(r['date'] for r in rr if r['date'])) or 'Data e local conforme registros.';desc=' '.join(r['content'] for r in rr if r['content']) or 'Nenhuma informação textual localizada.';y=285;y=field(p,'Data e Local:',date,y,11.2,4)-3;y=field(p,'Descrição:',desc,y,10.6,7)-3;y=field(p,'Relação com o Processo:','Informação consolidada diretamente das tarefas, tópicos e mensagens vinculadas à etapa.',y,10.6,4)-3;field(p,'Mídia de Apoio:',f'{len(media(rr))} mídia(s) encontrada(s).',y,11.2,2);ii=media(rr)
  if ii:add_image(p,ii[0],(150,620,470,320))
 # 17
 p=bg(doc,tpl);text(p,'MOTIVAÇÃO',384,221,14,True,60,1);mot=[r['content'] for r in rs if r['content'] and any(k in norm(r['content']) for k in ('art.','tráfico','trafico','quadrilha','ameaça','violencia','violência','prisao','prisão','controle territorial'))];text(p,'\n'.join('• '+x for x in dict.fromkeys(mot)) or '• Fundamentação conforme os registros da mesa operacional.',39,270,11.5,False,74,28)
 # 18
 p=bg(doc,tpl);text(p,'PROVAS E DOCUMENTAÇÕES',39,221,14,True,60,1);text(p,'Com base nas provas apresentadas, solicitamos a manutenção do mandado de pacificação e a adoção das medidas necessárias para garantir a segurança pública na região documentada.',39,270,11.5,False,74,7);text(p,'DELEGADO RESPONSÁVEL:',39,420,12,True,74,1);text(p,m['requerente'],39,450,11.5,False,74,3);text(p,'DIRETORIA DE INVESTIGAÇÃO E COMBATE AO CRIME ORGANIZADO - DICOR',39,515,11,True,74,2);text(p,'RESPONSÁVEL PELA CONSOLIDAÇÃO',125,650,11,True,34,1);text(p,'AUTORIDADE DICOR',500,650,11,True,22,1);text(p,'____________________________',125,690,11,False,34,1);text(p,'____________________________',500,690,11,False,22,1)
 target=Path(caminho);target.parent.mkdir(parents=True,exist_ok=True);doc.save(str(target),garbage=4,deflate=True,clean=True);doc.close();return str(target)

def gerar_pdf_dossie(bot_module,dados,caminho):return generate(bot_module,dados,caminho)
def gerar_pdf(bot_module,dados,caminho):return generate(bot_module,dados,caminho)
def install(bot_module):print('✅ V307 Dossiê: modelo visual fixo PF/DICOR + coleta por tarefas/tópicos/mensagens, sem motor legado.',flush=True)
