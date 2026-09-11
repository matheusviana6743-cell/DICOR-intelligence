# Central DICOR V700 — configuração

A Central V700 foi criada sem gravar segredos no repositório. No ambiente de produção, configure as variáveis abaixo.

## Administração

`CENTRAL_ADMIN_QRA` — QRA do administrador principal.

`CENTRAL_ADMIN_PASSAPORTE` — passaporte do administrador principal.

`CENTRAL_ADMIN_DISCORD_ID` — ID da sua conta Discord. Somente este ID pode aprovar ou recusar solicitações de acesso.

## E-mail

`DICOR_MAIL_HOST` — servidor IMAP SSL do e-mail.

`DICOR_MAIL_PORT` — normalmente `993`.

`DICOR_MAIL_USER` — usuário/endereço da caixa postal.

`DICOR_MAIL_PASSWORD` — senha/app password da caixa postal.

`DICOR_MAIL_FOLDER` — normalmente `INBOX`.

`DICOR_MAIL_LIMIT` — quantidade máxima de mensagens lidas por ciclo; padrão `120`.

A leitura é feita em modo somente leitura. Os registros são classificados por assunto/conteúdo em Procurados, Boletins, Perícias e Operações. A Central remove elementos de formatação e mensagens operacionais de Discord que não pertencem ao registro, mas preserva o conteúdo útil do e-mail no campo completo.

## FiveM

`FIVEMANAGE_API_KEY` — chave da Fivemanage usada para gerar o link direto da imagem.

## Persistência Railway

`DICOR_DATA_DIR=/data` é recomendado quando o serviço possui volume persistente. A Central mantém usuários, autorização, auditoria e segredo de sessão nesse diretório.

Sem volume persistente, esses arquivos podem ser perdidos em uma recriação do container. Isso não é substituído por banco externo automaticamente.

## Logos

`DICOR_LOGO_URL` é opcional. Por padrão, a Central usa `marca_dagua_dicor.png` do próprio repositório.

## Atualização

A V700 é carregada pelo `start_safe.py` e não depende do antigo `central_rate_guard_v615` para iniciar a Central. O código não contém tokens, senhas ou chaves reais.
