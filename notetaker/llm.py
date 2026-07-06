"""LLM Provider: invoca um CLI externo, enviando o prompt via stdin.

O comando e resolvido a partir do LLM Provider escolhido no config
([llm].provider: "kiro" ou "claude") via `config.resolve_llm_command`.
A transcricao + instrucoes vao por stdin (evita limite de argumento). A resposta
vem por stdout e e devolvida crua para o summarize parsear.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess


class LLMError(RuntimeError):
    pass


def run_llm(command: str, prompt: str, timeout: int = 600) -> str:
    """Executa o LLM Provider passando `prompt` via stdin e retorna o stdout.

    `command` e uma string de shell (ex.: "claude -p"); e dividida com shlex
    para evitar interpretacao de shell sobre o conteudo da transcricao. No
    Windows usamos posix=False para que barras invertidas em caminhos (ex.:
    C:\\Ferramentas\\llm.exe) nao sejam interpretadas como escape.
    """
    argv = shlex.split(command, posix=(os.name != "nt"))
    if not argv:
        raise LLMError("comando de LLM vazio (resolvido a partir de [llm].provider)")

    if shutil.which(argv[0]) is None:
        raise LLMError(
            f"CLI de LLM nao encontrado: '{argv[0]}'. "
            f"Ajuste [llm].provider no config (kiro | claude) ou instale a CLI."
        )

    try:
        proc = subprocess.run(
            argv,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise LLMError(f"LLM Provider excedeu o tempo limite ({timeout}s)") from exc

    if proc.returncode != 0:
        detalhe = proc.stderr.strip() or proc.stdout.strip()
        raise LLMError(
            f"LLM Provider retornou codigo {proc.returncode}: {detalhe}"
        )

    output = proc.stdout.strip()
    if not output:
        raise LLMError("LLM Provider nao retornou saida")
    return output
