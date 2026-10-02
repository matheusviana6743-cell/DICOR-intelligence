from app import CONFIGS

# Opções extras para o configurador do Bot Discord.
# Mantém o restante do sistema intacto e amplia as escolhas disponíveis.
CONFIGS['discord'] = [
    ('Objetivo', 'objective', 'textarea', True, 'Explique em poucas palavras o que o bot precisa fazer.'),
    ('Nome do bot', 'bot_name', 'text', False, 'Ex.: Forge Assistant'),
    ('Nome do servidor', 'server_name', 'text', False, 'Opcional'),
    ('Tipo do bot', 'bot_type', 'select', False, [
        'Vendas', 'Conversas / Chat', 'Jogos / Diversão', 'Atendimento', 'Tickets',
        'Moderação', 'Economia', 'Comunidade', 'Whitelist', 'Verificação',
        'Utilidades', 'Música', 'Notificações', 'Automação', 'Logs / Auditoria',
        'Integração FiveM', 'Integração Web', 'IA / Assistente', 'Segurança',
        'Sorteios', 'Ranking / XP', 'Formulários', 'Suporte', 'Personalizado'
    ]),
    ('Canais e comunicação', 'communication', 'multi', False, [
        'Chat', 'Call / Voz', 'Canais temporários', 'Salas privadas', 'Fórum',
        'Anúncios', 'Notificações', 'Sistema de avisos'
    ]),
    ('Vendas', 'sales', 'multi', False, [
        'Catálogo', 'Carrinho', 'Pedidos', 'Cupons', 'Checkout', 'Produtos digitais',
        'Controle de estoque', 'Comprovantes', 'Histórico de compras'
    ]),
    ('Conversas', 'conversation', 'multi', False, [
        'Chat automático', 'Respostas automáticas', 'FAQ', 'Atendimento humano',
        'Transferência para atendente', 'Histórico', 'Mensagem de boas-vindas'
    ]),
    ('Jogos e diversão', 'games', 'multi', False, [
        'Mini-games', 'Roleta', 'Sorteios', 'Quiz', 'Ranking', 'XP', 'Moedas',
        'Conquistas', 'Desafios'
    ]),
    ('Tickets', 'tickets', 'multi', False, [
        'Criar ticket', 'Categorias', 'Transcrição', 'Fechamento automático',
        'Avaliação', 'Tickets por equipe', 'Prioridade', 'Anexos'
    ]),
    ('Moderação', 'moderation', 'multi', False, [
        'Ban', 'Kick', 'Mute', 'Timeout', 'Anti-spam', 'Anti-link', 'Filtros',
        'Anti-raid', 'Verificação', 'Logs de punição'
    ]),
    ('Logs', 'logs', 'multi', False, [
        'Mensagens', 'Entradas / Saídas', 'Moderação', 'Tickets', 'Auditoria',
        'Alterações de cargos', 'Alterações de canais', 'Comandos'
    ]),
    ('Automação', 'automation', 'multi', False, [
        'AutoRole', 'Boas-vindas', 'Verificação', 'Cargos por reação',
        'Mensagens automáticas', 'Agendamentos', 'Lembretes', 'Respostas automáticas'
    ]),
    ('Economia', 'economy', 'multi', False, [
        'Saldo', 'Loja', 'Ranking', 'XP', 'Moedas', 'Transferências',
        'Recompensas', 'Daily'
    ]),
    ('Interface', 'ui', 'multi', False, [
        'Embeds', 'Botões', 'Menus', 'Slash Commands', 'Modais', 'Painéis',
        'Mensagens interativas'
    ]),
    ('Integrações', 'integrations', 'multi', False, [
        'Webhooks', 'Painel Web', 'APIs', 'Banco de dados', 'Mercado / Pagamentos',
        'FiveM', 'Site', 'Google', 'Outras APIs'
    ]),
    ('Permissões', 'permissions', 'textarea', False, 'Quais cargos podem usar cada área?'),
    ('Idioma', 'language', 'select', False, ['Português', 'Português + Inglês', 'Inglês', 'Outro']),
    ('Cor / estilo', 'style', 'text', False, 'Ex.: claro, moderno, azul e branco'),
    ('Hospedagem', 'hosting', 'select', False, ['Já tenho', 'Quero orientação', 'Quero hospedagem']),
    ('Código-fonte', 'source_code', 'select', False, ['Incluir', 'Não incluir']),
    ('Observações', 'notes', 'textarea', False, 'Qualquer detalhe adicional.')
]
