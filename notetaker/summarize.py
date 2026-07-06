"""Gera o Summary em Markdown: monta o prompt, chama o LLM Provider, extrai
o Markdown delimitado pelas sentinelas (tolerando ANSI/banners do CLI).
"""

from __future__ import annotations

import re

from .llm import run_llm
from .prompts import BEGIN_MARK, END_MARK, build_prompt


class SummaryError(RuntimeError):
    pass


# Sequencias de escape ANSI (cores/cursor) que CLIs interativos emitem no stdout.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def extract_markdown(raw: str) -> str:
    """Extrai o Markdown do Summary da saida do LLM.

    Prefere o conteudo entre as sentinelas. Se elas nao aparecerem (LLM as
    omitiu), faz fallback para o primeiro cabecalho Markdown em diante.
    """
    text = _strip_ansi(raw)

    begin = text.find(BEGIN_MARK)
    end = text.find(END_MARK)
    if begin != -1 and end != -1 and end > begin:
        return text[begin + len(BEGIN_MARK) : end].strip()

    # Fallback: a partir do primeiro cabecalho "# ".
    match = re.search(r"^#\s.+", text, flags=re.MULTILINE)
    if match:
        body = text[match.start() :].strip()
        # Remove sentinela remanescente, se houver.
        body = body.replace(BEGIN_MARK, "").replace(END_MARK, "").strip()
        if body:
            return body

    raise SummaryError("nao foi possivel extrair o resumo em Markdown da saida do LLM")


def generate_summary(
    transcript: str,
    llm_command: str,
    output_lang: str,
    title: str = "",
) -> str:
    """Fluxo completo: prompt -> LLM Provider -> Markdown extraido."""
    if not transcript.strip():
        raise SummaryError("transcricao vazia; nada a resumir")

    prompt = build_prompt(transcript, output_lang, title)
    raw = run_llm(llm_command, prompt)
    return extract_markdown(raw)
