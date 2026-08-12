# AGENTS.md

## Contexto do projeto

Este repositório contém o sistema DICOR em produção, integrado ao Discord e hospedado na Railway. O projeto atual é centrado em um `bot.py` monolítico, com servidor HTTP, comandos Discord, geração de documentos, persistência local e integrações opcionais de armazenamento remoto.

Segurança, preservação dos dados e compatibilidade com o comportamento existente têm prioridade máxima.

## Regra principal

Antes de qualquer alteração, trate o projeto como produção ativa. Nunca faça mudanças amplas quando uma correção pequena resolver o problema.

## Proibições absolutas

- Não fazer deploy automaticamente.
- Não executar `git push` automaticamente.
- Não fazer commit sem solicitação explícita.
- Não alterar configurações da Railway sem solicitação explícita.
- Não alterar o volume `/data` de produção durante testes locais.
- Não adicionar tokens, senhas, chaves, credenciais ou segredos ao Git.
- Não expor variáveis de ambiente, tokens, senhas ou credenciais em logs, respostas ou arquivos.
- Não limpar dados persistentes sem autorização explícita.
- Não apagar ou recriar o banco SQLite automaticamente.
- Não executar `DELETE`, `DROP`, `TRUNCATE` ou limpeza em massa sem autorização explícita.
- Não substituir arquivos JSON persistentes de forma destrutiva.
- Não alterar dados existentes apenas para adaptar uma funcionalidade nova.
- Não remover funcionalidades existentes sem confirmação clara.
- Não reestruturar o bot inteiro sem solicitação explícita.
- Não dividir `bot.py` em vários arquivos no meio de uma correção funcional, salvo autorização específica.

## Arquitetura observada

- `bot.py` concentra praticamente todo o sistema.
- `requirements.txt` define dependências Python.
- `railway.json` inicia o serviço com `python bot.py` e usa `/health` como healthcheck.
- O bot usa `discord.py`, `aiohttp`, JSONs locais, SQLite, geração de PDF/DOCX, OCR e armazenamento B2 opcional.
- Há muitas versões históricas no próprio `bot.py` (`V10`, `V17`, `V52`, `V75`, `V121` etc.).
- Existem funções e classes duplicadas; a definição efetiva em runtime costuma ser a última carregada.

## Fluxo obrigatório antes de implementar

Antes de modificar qualquer coisa:

1. Localizar o código efetivamente executado.
2. Verificar se há definições duplicadas da função/classe.
3. Explicar brevemente o fluxo atual.
4. Identificar arquivos, tabelas, canais e dados afetados.
5. Propor a mudança mínima.
6. Implementar somente o necessário.
7. Revisar o diff.
8. Executar validações relevantes ou explicar claramente o que não pôde ser testado.
9. Informar exatamente o que mudou.

## Alterações em código

- Antes de modificar uma função, localizar qual definição está ativa em runtime.
- Não assumir que a primeira definição encontrada é a efetiva.
- Evitar refatorações grandes junto com correções funcionais.
- Priorizar mudanças pequenas, isoladas e com diff mínimo.
- Preservar comportamento existente que não faça parte da tarefa solicitada.
- Não remover código legado apenas porque parece não utilizado.
- Não mudar IDs de canais, categorias, cargos, usuários ou servidores sem necessidade explícita.
- Não mudar estruturas do banco sem avaliar compatibilidade, migração e rollback.
- Em áreas com wrappers/versionamentos, verificar a cadeia final de chamadas antes de editar.

## Dados persistentes

O armazenamento persistente de produção deve usar `/data`, normalmente via `DICOR_DATA_DIR=/data`.

Trate como dados importantes:

- SQLite.
- JSONs.
- Imagens.
- Dossiês.
- Relatórios.
- Fichas.
- Boletins.
- Procurados.
- Perícias.
- Backups.
- Arquivos enviados por usuários.
- Índices e estados de migração B2.

Antes de alterar código relacionado à persistência:

- Identificar todos os arquivos afetados.
- Identificar tabelas afetadas.
- Confirmar se a operação é temporária, cache ou dado definitivo.
- Preferir operações atômicas quando possível.
- Evitar sobrescrever arquivos válidos com conteúdo vazio.
- Validar existência e integridade antes de substituir dados.

## Caminhos importantes

- `DATA_DIR` vem de `DICOR_DATA_DIR`; se ausente, cai em `BASE_DIR / "data"`.
- `PUBLIC_DIR` fica em `BASE_DIR / "public"`.
- `UPLOADS_DIR` fica em `PUBLIC_DIR / "uploads"`.
- `BACKUP_DIR` fica em `BASE_DIR / "backups"`.
- `PUBLIC_BACKUPS_DIR` fica em `PUBLIC_DIR / "backups"`.
- O banco principal é `DATA_DIR / "dicor_banco_dados.sqlite3"`.

Não escreva testes que usem o `/data` real de produção.

## Banco SQLite

- Nunca apagar ou recriar o banco automaticamente.
- Nunca rodar migração destrutiva sem autorização explícita.
- Nunca executar limpeza em massa sem autorização explícita.
- Antes de mexer em tabelas, verificar criação, índices, constraints e código legado.
- O banco usa WAL quando possível; considere concorrência e rollback.
- Qualquer alteração de esquema precisa preservar compatibilidade com dados existentes.

## Arquivos JSON

- Muitos estados são salvos como JSON inteiro.
- A função genérica de salvamento pode sobrescrever o arquivo completo.
- Evite escritas concorrentes sem necessidade.
- Não substituir JSON válido por `{}`, `[]` ou conteúdo parcial.
- Quando possível, use escrita temporária + replace atômico em novas rotinas.

## Discord

- Não criar mensagens extras ou spam em canais.
- Não apagar canais ou mensagens existentes, exceto recursos explicitamente temporários previstos pelo sistema.
- Validar usuário, cargo e contexto antes de ações administrativas.
- Respeitar permissões e hierarquias existentes.
- Alterações administrativas não devem conceder privilégios adicionais acidentalmente.
- Cuidado com listeners `on_message`, pois vários módulos podem processar a mesma mensagem.
- Cuidado com múltiplos `on_ready`; não adicionar rotinas pesadas sem escalonamento.

## Permissões e cargos

- A regra administrativa central usa cargos autorizadores específicos.
- Não trocar a lógica de cargos por permissões gerais do Discord sem solicitação explícita.
- Não ampliar acesso a comandos, painéis, endpoints ou ações destrutivas por acidente.
- Se mexer em permissões, documentar quais cargos/IDs são afetados.

## Mesas

- Preservar mesas existentes.
- Não apagar histórico de mesas.
- Se a mudança for válida apenas para novas mesas, nunca retroagir para mesas antigas.
- Fechamento de mesa deve preservar dados necessários ao dossiê e histórico.
- Antes de alterar fechamento, verificar coleta de evidências, geração de PDF/DOCX, persistência e limpeza temporária.

## Tarefas de mesas

- Tratar o sistema de tarefas separadamente do restante das mesas.
- Preservar estado persistente das tarefas.
- Não alterar mesas antigas quando a tarefa especificar aplicação apenas a novas mesas.
- Em fluxos com duas etapas, a segunda tarefa só pode ser disponibilizada após conclusão da primeira.
- Evitar mensagens desnecessárias quando a informação já puder ser exibida no painel.
- Verificar versões finais de `GerenciamentoTarefasView`, tarefas guiadas e tarefas manuais antes de editar.

## Boletins

- Preservar numeração existente.
- Evitar registros duplicados.
- Não apagar registros históricos automaticamente.
- Não alterar reconciliação mensal sem analisar impacto.
- Canais temporários podem ser apagados apenas quando o fluxo existente prevê isso.
- Se alterar publicação, garantir que rascunhos sejam preservados em caso de erro.

## Procurados e catálogo

- Preservar registros ativos, retirados e históricos.
- Evitar duplicação por RG ou mensagem.
- O endpoint web de apagar catálogo é sensível; não alterar sem revisão cuidadosa.
- Nunca apagar fotos, mensagens ou registros de procurados sem autorização explícita.
- Antes de mexer no catálogo, verificar `procurados.json`, `public/index.html`, `public/uploads` e integrações com Discord.

## Perícias, relatórios e OCR

- Tratar imagens e anexos como evidências importantes.
- Não remover arquivos de perícia/relatório sem confirmação.
- OCR pode gerar pendências e vínculos no banco; validar antes de alterar parsing.
- Alterações em OCR devem evitar duplicar registros já sincronizados.
- Antes de mexer em relatórios, confirmar diretórios temporários versus persistentes.

## PDFs, DOCX e dossiês

- Antes de alterar geração de PDF/DOCX, identificar arquivos temporários, finais e persistentes.
- O fechamento de mesa deve enviar documentos ao Discord e preservar o histórico.
- Não apagar dossiês finais para liberar espaço.
- Limpezas devem atingir apenas caches ou temporários comprovados.
- O `bot.py` contém imagem/modelo visual embutido em base64; evite tocar nisso sem necessidade.

## Backup e armazenamento remoto

- Backup completo pode consumir muito volume, RAM e tempo.
- Não iniciar backup completo automaticamente.
- Não alterar política de retenção sem autorização.
- B2/armazenamento remoto envolve credenciais e estados persistentes; não alterar sem revisar variáveis e fallback local.
- Não apagar cópia local após upload remoto sem confirmação de segurança do fluxo existente.

## Testes e validações

- Nunca testar usando banco real de produção quando o teste puder escrever dados.
- Preferir mocks, cópias e diretórios temporários.
- Para mudanças somente estáticas, validar com análise estática.
- Para mudanças Python, preferir `python -m py_compile bot.py` quando apropriado e seguro.
- Se não houver teste automatizado, informar isso claramente.
- Não rodar comandos que possam postar no Discord, alterar Railway ou tocar produção sem autorização.

## Pontos frágeis conhecidos

- `bot.py` é monolítico e muito grande.
- Existem muitas funções/classes duplicadas.
- Existem múltiplos `on_ready` e múltiplos `start_web_server`.
- Várias rotinas automáticas editam mensagens, sincronizam dados ou fazem manutenção.
- JSONs podem ser regravados por completo.
- Há rotinas de limpeza de cache/volume; confirmar escopo antes de alterar.
- Há endpoint web para apagar registro do catálogo.
- Há trecho de auditoria que pode arquivar e remover ficha vazia duplicada do banco após confirmação.
- B2, reconstrução de procurados e reconciliação de boletins são áreas sensíveis.

## Entrega de mudanças

Ao finalizar uma tarefa:

- Mostrar resumo objetivo.
- Informar arquivos alterados.
- Mostrar ou descrever o diff.
- Informar testes/validações executados.
- Informar riscos ou partes não testadas.
- Confirmar que não houve commit, push ou deploy, salvo se isso tiver sido solicitado explicitamente.
