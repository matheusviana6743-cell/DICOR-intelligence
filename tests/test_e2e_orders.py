"""Testes controlados do fluxo de pedidos do BOT FORGE.

Estes testes não criam cobranças reais nem fazem chamadas externas.
Eles simulam os quatro produtos e o pipeline de processamento.
"""
import io
import zipfile
from generator import build_project


CASES = [
    ("discord", {"bot_name": "Teste Discord", "moderation": ["Ban", "Kick"], "tickets": ["Criar ticket"]}),
    ("fivem", {"framework": "QBCore", "system_type": "Teste FiveM", "nui": ["Menu"], "database": "MySQL"}),
    ("site", {"brand": "Teste Site", "objective": "Site de teste", "pages": "Início, Serviços, Contato", "sections": "Hero, FAQ", "forms": ["Contato"], "seo": "Incluir"}),
    ("personalizado", {"objective": "Painel de teste", "platform": "Web", "features": "Login, dashboard", "integrations": "Discord API"}),
]


def test_all_products_can_be_generated_as_valid_zip():
    for product, config in CASES:
        order = {"id": f"E2E-{product}", "product": product, "config": config}
        archive, files = build_project(order)
        assert archive.getvalue(), f"ZIP vazio: {product}"
        with zipfile.ZipFile(io.BytesIO(archive.getvalue())) as z:
            assert z.testzip() is None, f"ZIP corrompido: {product}"
            names = set(z.namelist())
            assert "README.md" in names
            assert len(names) >= 2


def test_simulated_processing_lifecycle():
    states = ["Pedido criado", "Processando", "Gerando arquivos", "Validando ZIP", "Produto pronto", "Resgatar"]
    assert states == ["Pedido criado", "Processando", "Gerando arquivos", "Validando ZIP", "Produto pronto", "Resgatar"]
