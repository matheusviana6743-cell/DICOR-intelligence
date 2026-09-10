# -*- coding: utf-8 -*-
"""DICOR V305: gerador novo de dossiê usando template visual fixo."""
from __future__ import annotations
import io,json,re,urllib.request
from pathlib import Path
from typing import Any
import fitz
from PIL import Image

PW,PH=768,1056
FONT='Courier'; FB='Courier-Bold'
SECTIONS={
1:('Foto do painel da organização.',('painel','fotos líderes','fotos lideres','liderança','lideranca')),
2:('Foto dos principais membros da organização.',('fotos dos membros','fotos membros','principais membros','membros','integrantes','gerentes')),
3:('Localização da organização.',('localização','localizacao','coordenadas','endereço','endereco')),
4:('Foto de cima da organização para realizar estratégia de pacificação:',('foto de cima','visão aérea','visao aerea','aérea','aerea','vista aérea','vista aerea')),
5:('Material que vendem.',('material que vendem','materiais','ingredientes base','produtos','mercadorias','vendas')),
6:('Registrar compra do ilícito em frente ou dentro da comunidade/organização.',('registrar compra','compra do ilícito','compra do ilicito','compra','negociação','negociacao')),
7:('Foto do informante da organização.',('informante','foto do informante','informações do informante','informacoes do informante')),
8:('Foto do baú de membros.',('baú de membros','bau de membros','baú membros','bau membros')),
9:('Foto do baú de líder.',('baú de líder','bau de lider','baú líder','bau lider')),
10:('Foto e localização do local de fabricação.',('local de fabricação','local de fabricacao','fabricação','fabricacao','rota de farm','farm')),
11:('Foto e localização do local de produção.',('local de produção','local de producao','produção','producao','rota de produção','rota de producao','escoamento')),
12:('Informações gerais.',('informações gerais','informacoes gerais','informação geral','informacao geral','geral','rádio','radio','crimes da comunidade'))}

def norm(x):
 s=str(x or '').casefold(); r={'á':'a','à':'a','â':'a','ã':'a','é':'e','ê':'e','í':'i','ó':'o','ô':'o','õ':'o','ú':'u','ç':'c'}
 for a,b in r.items(): s=s.replace(a,b)
 return ' '.join(re.sub(r'[^0-9a-z]+',' ',s).split())

def clean(x):
 if x is None:return ''
 if isinstance(x,str):return x.strip()
 if isinstance(x,(int,float,bool)):return str(x)
 try:return json.dumps(x,ensure_ascii=False,default=str)
 except:return str(x)

def walk(x):
 if isinstance(x,dict):
  yield '',x
  for k,v in x.items():
   for p,c in walk(v): yield (f'{k}.{p}'.rstrip('.'),c)
 elif isinstance(x,(list,tuple,set)):
  for i,v in enumerate(x):
   for p,c in walk(v): yield f'[{i}].{p}',c

def pick(d,keys):
 keys={norm(k) for k in keys}
 for k,v in d.items():
  if norm(k) in keys and clean(v):return clean(v)
 return ''

def records(dados):
 out=[];seen=set()
 for path,obj in walk(dados):
  if not isinstance(obj,dict):continue
  r={k:pick(obj,a) for k,a in {
   'id':('id','message_id','thread_id','task_id','record_id'),'task':('tarefa','task','task_name','nome_tarefa'),
   'topic':('topico','tópico','topic','thread','thread_name','nome_topico','nome_tópico'),'title':('titulo','título','title','nome','name','assunto','subject'),
   'source':('origem','source','canal','channel','channel_name','parent_name'),'content':('conteudo','conteúdo','content','texto','text','mensagem','message','descricao','descrição','description','observacao','observação','valor','value','resultado','result'),
   'author':('autor','author','autor_nome','author_name','usuario','user','membro'),'date':('data','date','timestamp','created_at','criado_em','created','quando')}.items()}
  r['raw']=obj;r['urls']=[]
  for _,v in walk(obj):
   if isinstance(v,str):
    for u in re.findall(r'https?://[^\s<>\]\)]+',v):
     u=u.rstrip('.,);]')
     if u not in r['urls']:r['urls'].append(u)
   elif isinstance(v,dict):
    for k in ('url','proxy_url','attachment_url','image_url','thumbnail_url','media_url','video_url'):
     u=v.get(k)
     if isinstance(u,str) and u.startswith('http') and u not in r['urls']:r['urls'].append(u)
  sig=r['id'] or (path,r['task'],r['topic'],r['title'],r['content'][:500])
  if sig in seen:continue
  if any(r[k] for k in ('task','topic','title','source','content','author','date','urls')):
   seen.add(sig);out.append(r)
 return out

def classify(r):
 head=norm(' '.join((r['task'],r['topic'],r['title'],r['source'])));body=norm(r['content']);best=12;score0=0
 for n,(_,als) in SECTIONS.items():
  s=sum(6 if norm(a) in head else 1 if norm(a) in body else 0 for a in als)
  if s>score0:score0,best=s,n
 return best

def lines(text,n=78):
 text=re.sub(r'/tmp/[^\s]+','',str(text or ''))
 out=[]
 for p in text.splitlines() or ['']:
  cur=''
  for w in p.split():
   c=(cur+' '+w).strip()
   if len(c)<=n:cur=c
   else:
    if cur:out.append(cur)
    cur=w
  if cur:out.append(cur)
 return out

def put(p,text,x,y,size=11.5,bold=False,n=78,max_lines=10):
 for s in lines(text,n)[:max_lines]:
  p.insert_text((x,y),s,fontsize=size,fontname=FB if bold else FONT,color=(0,0,0));y+=size*1.47
 return y

def field(p,label,value,y,size=11.2,max_lines=5):
 p.insert_text((39,y),label,fontsize=12,fontname=FB,color=(0,0,0));return put(p,value,55,y+20,size,False,77,max_lines)

def base(doc,tpl):
 p=doc.new_page(width=PW,height=PH);p.insert_image(p.rect,stream=tpl);return p

def imgs(rs):
 out=[]
 for r in rs:
  for u in r['urls']:
   h=norm(r['task']+' '+r['topic']+' '+r['title'])
   if u.lower().split('?',1)[0].endswith(('.png','.jpg','.jpeg','.webp','.gif')) or any(k in h for k in ('foto','imagem','informante','painel','membro','bau','localizacao')):
    if u not in out:out.append(u)
 return out

def addimg(p,u,rect):
 try:
  req=urllib.request.Request(u,headers={'User-Agent':'DICOR-V305'})
  with urllib.request.urlopen(req,timeout=8) as f:data=f.read(8*1024*1024)
  im=Image.open(io.BytesIO(data)).convert('RGB');b=io.BytesIO();im.save(b,'PNG');p.insert_image(fitz.Rect(*rect),stream=b.getvalue(),keep_proportion=True);return True
 except:return False

def generate(bot_module:Any,dados:Any,caminho:Any)->str:
 rs=records(dados);sec={n:[] for n in SECTIONS}
 for r in rs:sec[classify(r)].append(r)
 def first(keys,default):
  for r in rs:
   v=pick(r['raw'],keys)
   if v:return v
  return default
 ident=next((r['id'] for r in rs if str(r['id']).isdigit()),'MESA')
 meta={'pedido':first(('nº do pedido de pacificação','numero do pedido','numero_pedido','pedido'),f'INV-{str(ident)[-6:]}'),'data':first(('data de expedição','data de expedicao','data_expedicao','data'),'Não informado'),'processo':first(('nº do processo','numero processo','numero_processo','processo'),f'PF-DICOR-{ident}'),'requerente':first(('requerente','solicitante','responsavel','responsável','autoridade'),'Polícia Federal - DICOR'),'local':first(('localização','localizacao','endereco','endereço','local','cidade'),'Não informado'),'organizacao':first(('organização','organizacao','comunidade','grupo','alvo','investigado'),'Não identificado')}
 tpl=Path(__file__).with_name(TEMPLATE_FILE).read_bytes();doc=fitz.open()
 p=base(doc,tpl);put(p,f"Nº do Pedido de Pacificação:   {meta['pedido']}",39,438,12,True,74,1);put(p,f"Data de Expedição:      {meta['data']}",39,470,12,False,74,1);put(p,f"Nº do Processo:   {meta['processo']}",39,502,12,True,74,1);put(p,'Requerente:',39,560,12,True,74,1);put(p,'• '+meta['requerente'],55,590,11.5,False,76,2);put(p,'Localização:',39,648,12,True,74,1);put(p,f"• {meta['requerente']}, por intermédio da Diretoria de Investigação e Combate ao Crime Organizado - DICOR, requer a concessão do presente MANDADO DE PACIFICAÇÃO, visando a manutenção da ordem e o cumprimento das determinações aplicáveis ao procedimento.\n• Dessa forma, solicita-se autorização para proceder com a busca e pacificação no local denominado “{meta['organizacao']}”, incluindo os pontos e instalações documentados no dossiê operacional.",55,682,11.5,False,76,10)
 p=base(doc,tpl);put(p,'DISPOSIÇÕES DO MANDADO',205,221,14,True,60,1);put(p,'\n'.join('• '+x for x in ['Fica autorizada a busca em qualquer andar ou sala do estabelecimento, bem como nos veículos pessoais pertencentes aos investigados.','Nenhum documento ou objeto pertencente a terceiros, familiares ou residentes, presentes no momento da operação, deverá ser apreendido.','Deverá ser solicitada a presença de um representante da OAC (Advogado(a)), conforme previsto no Art. 7º, §6º, da Lei nº 8.906/1994.','Caso sejam identificados materiais probatórios adicionais relevantes, deverá ser requerida expressamente a extensão da busca.','Fica autorizado o arrombamento de cofres, baús, porta-malas e demais compartimentos caso não sejam voluntariamente abertos.','O(s) investigado(s) detido(s) deverá(ão) ser apresentado(s) imediatamente à Autoridade Civil competente.']),39,270,11.7,False,77,28)
 p=base(doc,tpl);put(p,'PLANEJAMENTO OPERACIONAL',185,221,14,True,60,1);put(p,'Para garantir o sucesso da pacificação, a operação contará com:',39,270,12,True,76,2);y=325
 for label,ks in [('Efetivo envolvido:',('efetivo','equipe','agente','membro')),('Recursos utilizados:',('recurso','viatura','drone','helicoptero','helicóptero')),('Estratégia de abordagem:',('estrategia','estratégia','abordagem','setor','acesso')),('Medidas serão tomadas pra proteger a população local, incluindo:',('proteção','protecao','morador','oab','direitos humanos'))]:
  put(p,label,39,y,12,True,76,1);y+=22;vals=[r['content'] for r in rs if r['content'] and any(norm(k) in norm(r['content']) for k in ks)];y=put(p,'• '+('; '.join(dict.fromkeys(vals)) if vals else 'Informação conforme registros da mesa.'),55,y,11.2,False,76,4)+10
 p=base(doc,tpl);put(p,'PROVAS E DOCUMENTAÇÕES',39,221,14,True,60,1);put(p,'As provas e documentações gerais relativas ao processo serão anexadas ao mandado e permanecerão de uso restrito das autoridades competentes. Todas as evidências foram obtidas por meio dos registros da mesa operacional e documentadas para comprovar a necessidade da incursão.',39,270,11.5,False,76,7)
 if sec[12]:put(p,'INFORMAÇÕES GERAIS:',39,410,12,True,76,1);put(p,'\n'.join('• '+r['content'] for r in sec[12] if r['content']),55,440,10.5,False,76,10)
 p=base(doc,tpl);put(p,'Mídia de Apoio:',39,221,12,True,76,1);entries=[]
 for r in sec[1]:
  for line in r['content'].splitlines():
   m=re.search(r'(.+?)\s*(?:rg\s*[:=-]\s*)(\d+)',line,re.I)
   if m:entries.append(f"{m.group(1).strip(' *:-')}    RG: {m.group(2)}")
 y=270;put(p,'Líder:',39,y,12,True,76,1);y=put(p,'• '+(entries[0] if entries else 'Não identificado'),55,y+25,11.5,False,76,2)+35;put(p,'Gerentes:',39,y,12,True,76,1);put(p,'\n'.join('• '+x for x in entries[1:9]) or '• Não identificado',55,y+25,11.5,False,76,12)
 p=base(doc,tpl);put(p,'Painel:',39,221,12.5,True,76,1);ii=imgs(sec[1]);
 if ii:addimg(p,ii[0],(205,243,360,650))
 for n in range(2,12):
  p=base(doc,tpl);put(p,f'{n}. {SECTIONS[n][0]}',39,221,11.8,True,76,2);rr=sec[n];dates='; '.join(dict.fromkeys(r['date'] for r in rr if r['date'])) or 'Data e local conforme registros.';desc=' '.join(r['content'] for r in rr if r['content']) or 'Nenhuma informação textual localizada.';y=285;y=field(p,'Data e Local:',dates,y,11.2,4)-3;y=field(p,'Descrição:',desc,y,10.6,7)-3;y=field(p,'Relação com o Processo:','Informação consolidada a partir das tarefas, tópicos e mensagens vinculadas à etapa.',y,10.6,4)-3;field(p,'Mídia de Apoio:',f'{len(imgs(rr))} mídia(s) encontrada(s).',y,11.2,2);ii=imgs(rr)
  if ii:
   if n==2:
    for i,u in enumerate(ii[:4]):addimg(p,u,(70+i*165,640,150,280))
   else:addimg(p,ii[0],(150,620,470,320))
 p=base(doc,tpl);put(p,'MOTIVAÇÃO',270,221,14,True,60,1);mot=[r['content'] for r in rs if r['content'] and any(k in norm(r['content']) for k in ('art.','tráfico','trafico','quadrilha','ameaça','violencia','violência','prisao','prisão','controle territorial'))];put(p,'\n'.join('• '+x for x in dict.fromkeys(mot)) or '• Fundamentação conforme os registros da mesa operacional.',39,270,11.5,False,76,28)
 p=base(doc,tpl);put(p,'PROVAS E DOCUMENTAÇÕES',39,221,14,True,60,1);put(p,'Com base nas provas apresentadas, solicitamos a manutenção do mandado de pacificação e a adoção das medidas necessárias para garantir a segurança pública na região documentada.',39,270,11.5,False,76,7);put(p,'DELEGADO RESPONSÁVEL:',39,420,12,True,76,1);put(p,meta['requerente'],39,450,11.5,False,76,3);put(p,'DIRETORIA DE INVESTIGAÇÃO E COMBATE AO CRIME ORGANIZADO - DICOR',39,515,11,True,76,2);put(p,'RESPONSÁVEL PELA CONSOLIDAÇÃO',125,650,11,True,34,1);put(p,'AUTORIDADE DICOR',500,650,11,True,22,1);put(p,'____________________________',125,690,11,False,34,1);put(p,'____________________________',500,690,11,False,22,1)
 target=Path(caminho);target.parent.mkdir(parents=True,exist_ok=True);doc.save(str(target),garbage=4,deflate=True,clean=True);doc.close();return str(target)

def gerar_pdf_dossie(bot_module,dados,caminho):return generate(bot_module,dados,caminho)
def gerar_pdf(bot_module,dados,caminho):return generate(bot_module,dados,caminho)
def install(bot_module):print('✅ V305 Dossiê: gerador novo com template visual fixo e coleta por tarefas/tópicos/mensagens.',flush=True)

TEMPLATE_FILE='dicor_template_v305.png'
