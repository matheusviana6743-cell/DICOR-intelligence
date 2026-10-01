# BOT FORGE

Loja e plataforma de configuração de bots Discord, sistemas FiveM e sites.

## Executar

python -m pip install -r requirements.txt
python app.py

## Railway

O projeto usa Gunicorn e a variável PORT.

## Variáveis recomendadas

- ADMIN_PASSWORD
- FLASK_SECRET_KEY
- BOT_FORGE_DATA_DIR=/data
- ASAAS_API_KEY
- ASAAS_API_BASE=https://api-sandbox.asaas.com/v3
- ASAAS_WEBHOOK_TOKEN
- PUBLIC_URL

O pagamento Asaas é criado no servidor e nunca expõe a API Key ao navegador.

## Fluxo

Cliente configura → revisão → pedido → checkout → pagamento → acompanhamento → entrega.

Projetos personalizados entram como orçamento entre R$50 e R$200; o valor final é confirmado no painel antes da cobrança.
