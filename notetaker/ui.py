"""Helpers de saida no terminal: spinner/animacao e formatacao.

Respeita TTY: quando a saida nao e um terminal (pipe, arquivo), degrada para
mensagens simples em linha, sem escapes de cursor.
"""

from __future__ import annotations

import itertools
import shutil
import sys
import threading
import time

# Frames do spinner (braille). Fallback ascii quando o terminal nao suporta.
_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_FRAMES_ASCII = "|/-\\"


def is_tty() -> bool:
    return sys.stdout.isatty()


def _frames() -> str:
    enc = (sys.stdout.encoding or "").lower()
    if "utf" in enc:
        return _FRAMES
    return _FRAMES_ASCII


def format_duration(seconds: float) -> str:
    """Formata segundos como HH:MM:SS (ou MM:SS quando < 1h)."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_size(num_bytes: int) -> str:
    """Formata bytes em unidade legivel (B, KB, MB, GB)."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def clear_line() -> None:
    if is_tty():
        sys.stdout.write("\r\x1b[2K")
        sys.stdout.flush()


def status_line(text: str) -> None:
    """Escreve uma linha de status reescrevivel (fica na mesma linha no TTY)."""
    width = shutil.get_terminal_size((80, 20)).columns
    text = text[: width - 1]
    if is_tty():
        sys.stdout.write("\r\x1b[2K" + text)
        sys.stdout.flush()
    else:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()


class Spinner:
    """Spinner em thread para tarefas de duracao indefinida (ex.: transcricao).

    Uso:
        with Spinner("transcrevendo..."):
            trabalho_pesado()

    Em nao-TTY, apenas imprime a mensagem uma vez ao iniciar.
    """

    def __init__(self, message: str, interval: float = 0.1):
        self.message = message
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._final: str | None = None

    def _run(self) -> None:
        for frame in itertools.cycle(_frames()):
            if self._stop.is_set():
                break
            status_line(f"{frame} {self.message}")
            time.sleep(self.interval)

    def start(self) -> "Spinner":
        if is_tty():
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        else:
            sys.stdout.write(self.message + "\n")
            sys.stdout.flush()
        return self

    def update(self, message: str) -> None:
        self.message = message

    def stop(self, final_message: str | None = None) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        clear_line()
        if final_message:
            print(final_message)

    def __enter__(self) -> "Spinner":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
