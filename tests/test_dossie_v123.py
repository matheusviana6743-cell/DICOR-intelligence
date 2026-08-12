from __future__ import annotations

from pathlib import Path

from docx import Document
from PIL import Image, ImageDraw
from pypdf import PdfReader

from dossie_v123 import SECTION_DEFINITIONS, build_operational_dossier_payload, generate_docx, generate_pdf


def _sample_image(path: Path, label: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (900, 520), "#1f2f46")
    draw = ImageDraw.Draw(img)
    draw.rectangle((24, 24, 876, 496), outline="#d7b66a", width=8)
    draw.text((60, 230), label, fill="#ffffff")
    img.save(path)
    return path


def test_v123_payload_filters_admin_and_generates_files(tmp_path: Path):
    image_path = _sample_image(tmp_path / "evidencia_painel.png", "PAINEL DICOR")
    dados = {
        "processo": "PF-DICOR-999",
        "numero_investigacao": "INV-999",
        "nome_operacao": "OPERAÇÃO TESTE V123",
        "comunidade": "Comunidade Teste",
        "faccao": "Organização Teste",
        "canal_id": 999,
        "canal_nome": "mesa-teste",
        "guild_id": 123,
        "guild_nome": "Guild Teste",
        "data_abertura": "01/08/2026 10:00",
        "data_encerramento": "12/08/2026 10:00",
        "agente_encerramento": "Inspetor Teste",
        "mesa": {"autor_nome": "Criador Teste"},
        "mensagens": [
            {
                "id": 1,
                "autor": "Agente Um",
                "autor_id": 11,
                "data": "12/08/2026 09:00",
                "origem": "01-painel",
                "topico": "painel",
                "conteudo": "Painel real da organização com dados de liderança.",
                "url": "https://discord.test/msg/1",
            },
            {
                "id": 2,
                "autor": "DICOR Bot",
                "author_bot": True,
                "data": "12/08/2026 09:01",
                "origem": "01-painel",
                "topico": "painel",
                "conteudo": "🎯 TAREFA GUIADA — ITEM 1 — PAINEL\nFinalizar tarefa",
                "url": "https://discord.test/msg/2",
            },
            {
                "id": 3,
                "autor": "Agente Dois",
                "data": "12/08/2026 09:03",
                "origem": "05-localizacao",
                "topico": "localizacao",
                "conteudo": "Etapa 1: mapa e referência geográfica confirmados.",
                "url": "https://discord.test/msg/3",
            },
            {
                "id": 4,
                "autor": "Agente Dois",
                "data": "12/08/2026 09:04",
                "origem": "05-localizacao",
                "topico": "localizacao",
                "conteudo": "Etapa 2: rota de aproximação descrita.",
                "url": "https://discord.test/msg/4",
            },
        ],
        "evidencias": [
            {
                "tipo": "imagem",
                "arquivo": "evidencia_painel.png",
                "local": str(image_path),
                "url": "https://discord.test/evidencia_painel.png",
                "mensagem_id": 1,
                "mensagem_url": "https://discord.test/msg/1",
                "autor": "Agente Um",
                "data": "12/08/2026 09:00",
                "origem": "01-painel",
                "topico": "painel",
            },
            {
                "tipo": "video",
                "arquivo": "radio.mp4",
                "url": "https://discord.test/radio.mp4",
                "mensagem_id": 5,
                "mensagem_url": "https://discord.test/msg/5",
                "autor": "Agente Três",
                "data": "12/08/2026 09:05",
                "origem": "04-radio",
                "topico": "radio",
            },
        ],
        "resumos": {
            "painel": "Resumo real do painel.",
            "localizacao": "Resumo real da localização.",
            "radio": "Resumo real do rádio.",
        },
        "estatisticas": {"mensagens_analisadas": 4, "evidencias": 2, "imagens": 1, "videos": 1, "links": 2},
    }
    estado = {
        "versao": 122,
        "concluidos": {str(i): {"concluido_em": "12/08/2026"} for i in range(1, 14)},
        "etapas_por_item": {"5": 2, "11": 2, "12": 2},
        "tarefas_guiadas": {
            "5:1": {"item": 5, "etapa": 1, "status": "CONCLUIDA"},
            "5:2": {"item": 5, "etapa": 2, "status": "CONCLUIDA"},
        },
    }
    payload = build_operational_dossier_payload(dados, estado)
    assert len(payload["sections"]) == 13
    assert [s["title"] for s in payload["sections"]] == [s["title"] for s in SECTION_DEFINITIONS]
    painel_messages = payload["sections"][0]["messages"]
    assert len(painel_messages) == 1
    assert "TAREFA GUIADA" not in painel_messages[0]["content"]
    assert payload["sections"][4]["tasks"]["1"]["status"] == "CONCLUIDA"
    assert payload["sections"][4]["tasks"]["2"]["status"] == "CONCLUIDA"

    pdf_path = tmp_path / "DOSSIE_OPERACIONAL_PF_DICOR_999.pdf"
    docx_path = tmp_path / "DOSSIE_OPERACIONAL_PF_DICOR_999.docx"
    generate_pdf(payload, pdf_path)
    generate_docx(payload, docx_path)

    assert pdf_path.exists() and pdf_path.stat().st_size > 6000
    assert docx_path.exists() and docx_path.stat().st_size > 3500

    pdf = PdfReader(str(pdf_path))
    assert len(pdf.pages) >= 15
    text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "01. PAINEL" in text
    assert "13. RESIDÊNCIA DO LÍDER" in text
    assert "TAREFA GUIADA" not in text

    doc = Document(str(docx_path))
    doc_text = "\n".join(p.text for p in doc.paragraphs)
    assert "DOSSIÊ OPERACIONAL DE INVESTIGAÇÃO" in doc_text
    assert "13. RESIDÊNCIA DO LÍDER" in doc_text
    assert "TAREFA GUIADA" not in doc_text
