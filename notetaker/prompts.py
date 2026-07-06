"""Monta o prompt multilingue enviado ao LLM Provider.

O Summary e produzido diretamente em Markdown pelo LLM, entre sentinelas que
permitem extracao robusta mesmo quando o CLI adiciona banners/ANSI/texto extra.
"""

from __future__ import annotations

# Sentinelas que delimitam o Markdown do Summary na saida do LLM.
BEGIN_MARK = "===NOTETAKER-RESUMO-INICIO==="
END_MARK = "===NOTETAKER-RESUMO-FIM==="

# Nome do idioma alvo por codigo, para instruir o LLM.
_LANG_NAME = {
    "pt": "portugues do Brasil",
    "es": "espanhol",
    "en": "ingles",
}

# Titulos das secoes por idioma (o LLM deve usar exatamente estes).
_SECTIONS = {
    "pt": ["Resumo Executivo", "Pontos Discutidos", "Decisoes", "Tarefas", "Observacoes"],
    "es": ["Resumen Ejecutivo", "Puntos Discutidos", "Decisiones", "Tareas", "Observaciones"],
    "en": ["Executive Summary", "Discussion Points", "Decisions", "Action Items", "Notes"],
}


def resolve_output_language(output_lang: str, meeting_lang: str) -> str:
    """Resolve o idioma de saida do Summary.

    output_lang pode ser 'meeting' (segue a Meeting Language) ou pt/es/en.
    """
    if output_lang and output_lang != "meeting":
        return output_lang
    if meeting_lang in _LANG_NAME:
        return meeting_lang
    return "pt"


def build_prompt(transcript: str, output_lang: str, title: str = "") -> str:
    """Monta o prompt completo: instrucoes + estrutura Markdown + transcricao."""
    lang = output_lang if output_lang in _SECTIONS else "pt"
    lang_name = _LANG_NAME[lang]
    s = _SECTIONS[lang]
    heading = title or {"pt": "Resumo da Reuniao", "es": "Resumen de la Reunion",
                        "en": "Meeting Summary"}[lang]

    return f"""\
Voce e um assistente que resume reunioes a partir de uma transcricao.

A transcricao esta rotulada por locutor (ex.: [Voce], [Participantes]). Use
esses rotulos para atribuir tarefas ao responsavel correto.

Gere um resumo estruturado em Markdown, ESCRITO EM {lang_name.upper()}.

Escreva o Markdown entre as duas linhas sentinela abaixo, sem nenhum outro texto
antes ou depois delas:

{BEGIN_MARK}
# {heading}

## {s[0]}
(2 a 3 frases resumindo a reuniao)

## {s[1]}
(lista de topicos objetivos, um por linha com "- ")

## {s[2]}
(apenas o que foi efetivamente decidido; "- " por item)

## {s[3]}
(cada acao concreta como "- descricao (responsavel; prazo)"; use "-" quando nao houver prazo)

## {s[4]}
(riscos, duvidas em aberto, itens a acompanhar; "- " por item)
{END_MARK}

Regras:
- Use exatamente esses titulos de secao e nessa ordem.
- Se uma secao nao tiver conteudo, escreva "- (nenhum)".
- Nao inclua blocos de codigo, apenas Markdown de texto.

Transcricao da reuniao:
---
{transcript}
---
"""
