"""Transcricao local em batch com faster-whisper, uma Track por vez.

Idioma pode ser fixado (pt/es/en) ou 'auto' (Whisper detecta). O idioma
detectado da Track mic e usado como Meeting Language efetiva.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

# Idiomas suportados explicitamente pelo Notetaker.
SUPPORTED_LANGS = ("pt", "es", "en")


class TranscribeError(RuntimeError):
    pass


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TranscribeStats:
    """Metricas de desempenho de uma transcricao, para diagnostico.

    rtf (real-time factor) = tempo_transcricao / duracao_audio. rtf < 1 e mais
    rapido que tempo real; rtf > 1 e mais lento (comum em CPU com modelo grande).
    """

    audio_seconds: float = 0.0        # duracao do audio transcrito
    model_load_seconds: float = 0.0   # tempo para carregar o modelo (0 se cache)
    transcribe_seconds: float = 0.0   # tempo efetivo de transcricao
    segments: int = 0

    @property
    def rtf(self) -> float:
        if self.audio_seconds <= 0:
            return 0.0
        return self.transcribe_seconds / self.audio_seconds


@dataclass
class TrackTranscript:
    text: str
    language: str
    segments: list[Segment] = field(default_factory=list)
    stats: TranscribeStats = field(default_factory=TranscribeStats)


_model_cache: dict[tuple, object] = {}

# Resultado memoizado da deteccao de dispositivo de computacao.
_compute_device: tuple[str, str] | None = None


def detect_compute_device() -> tuple[str, str]:
    """Detecta o melhor (device, compute_type) para o faster-whisper.

    Retorna ("cuda", "float16") se houver GPU NVIDIA utilizavel pelo CTranslate2;
    caso contrario ("cpu", "int8"). O resultado e memoizado.

    Nota: o CTranslate2 (backend do faster-whisper) so acelera em GPUs NVIDIA
    (CUDA). Nao ha suporte a Metal/MPS, entao Macs (Apple Silicon ou Intel)
    permanecem em CPU.
    """
    global _compute_device
    if _compute_device is not None:
        return _compute_device

    device, compute = "cpu", "int8"
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            device, compute = "cuda", "float16"
    except Exception:
        # Sem ctranslate2/CUDA disponivel: mantem CPU.
        pass

    _compute_device = (device, compute)
    return _compute_device


def _load_model(model_name: str, cpu_threads: int = 0, use_cache: bool = True):
    """Carrega o modelo faster-whisper no melhor dispositivo disponivel.

    Usa GPU NVIDIA (cuda/float16) quando detectada; senao CPU (int8). Em CPU,
    cpu_threads=0 deixa o CTranslate2 decidir (todos os cores); para transcricao
    paralela, passe metade dos cores e use_cache=False, de modo que cada Track
    tenha sua propria instancia com seu proprio pool de threads. Em GPU, o
    cpu_threads e irrelevante e a paralelizacao por threads nao se aplica.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscribeError(
            "faster-whisper nao instalado. Rode: pip install -e ."
        ) from exc

    device, compute_type = detect_compute_device()

    def _build():
        if device == "cpu":
            return WhisperModel(
                model_name, device=device, compute_type=compute_type,
                cpu_threads=cpu_threads,
            )
        return WhisperModel(model_name, device=device, compute_type=compute_type)

    if use_cache:
        key = (model_name, device, compute_type, cpu_threads)
        cached = _model_cache.get(key)
        if cached is not None:
            return cached
        model = _build()
        _model_cache[key] = model
        return model

    return _build()


def gpu_available() -> bool:
    """True se a transcricao usara GPU NVIDIA."""
    return detect_compute_device()[0] == "cuda"


def nvidia_gpu_present() -> bool:
    """Indica se ha uma GPU NVIDIA no hardware (via nvidia-smi).

    Diferente de detect_compute_device(), que so retorna 'cuda' quando as libs
    CUDA (ctranslate2 + cublas/cudnn) ja estao utilizaveis em runtime. Esta
    checagem detecta o hardware antes das libs estarem prontas, para orientar a
    instalacao do libcublas na primeira execucao.
    """
    import shutil
    import subprocess

    if shutil.which("nvidia-smi") is None:
        return False
    try:
        result = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        # nvidia-smi presente mas nao executavel (driver ausente etc.): sem GPU.
        return False
    return result.returncode == 0 and "GPU" in result.stdout


def load_model(model_name: str, cpu_threads: int = 0):
    """Carrega uma instancia dedicada do modelo (sem cache).

    O carregador do faster-whisper nao e seguro para uso concorrente, entao o
    caminho paralelo carrega os modelos sequencialmente com esta funcao e depois
    transcreve em threads.
    """
    return _load_model(model_name, cpu_threads=cpu_threads, use_cache=False)


def transcribe_track(
    audio_path: Path,
    model_name: str = "medium",
    language: str = "auto",
    cpu_threads: int = 0,
    use_cache: bool = True,
    preloaded_model=None,
) -> TrackTranscript:
    """Transcreve uma Track. language 'auto' deixa o Whisper detectar.

    preloaded_model: instancia WhisperModel ja carregada. Usada no caminho
    paralelo, onde os modelos sao carregados sequencialmente antes (o carregador
    do faster-whisper nao e seguro para uso concorrente).
    """
    if not audio_path.exists():
        raise TranscribeError(f"audio nao encontrado: {audio_path}")
    if audio_path.stat().st_size == 0:
        raise TranscribeError(
            f"audio vazio (0 B): {audio_path.name}. A captura pode ter falhado; "
            f"verifique o log ffmpeg-*.log na pasta da reuniao e os dispositivos "
            f"com 'notetaker devices'."
        )

    stats = TranscribeStats()

    if preloaded_model is not None:
        model = preloaded_model
    else:
        t0 = time.monotonic()
        model = _load_model(model_name, cpu_threads=cpu_threads, use_cache=use_cache)
        stats.model_load_seconds = time.monotonic() - t0

    lang_arg = None if language == "auto" else language

    # A chamada retorna um gerador; o trabalho pesado ocorre ao iterar.
    t1 = time.monotonic()
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=lang_arg,
        vad_filter=True,
    )

    segments: list[Segment] = []
    parts: list[str] = []
    for seg in segments_iter:
        text = seg.text.strip()
        if not text:
            continue
        segments.append(Segment(start=seg.start, end=seg.end, text=text))
        parts.append(text)
    stats.transcribe_seconds = time.monotonic() - t1

    stats.audio_seconds = getattr(info, "duration", 0.0) or 0.0
    stats.segments = len(segments)

    return TrackTranscript(
        text=" ".join(parts).strip(),
        language=info.language,
        segments=segments,
        stats=stats,
    )
