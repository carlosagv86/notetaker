"""Diarizacao: atribui trechos de fala a quem falou.

Nivel 1 (sem ML): usa as Tracks separadas. Tudo da Track mic e "Voce"; tudo da
Track system e "Participantes". Os segmentos das duas Tracks sao intercalados
por timestamp para produzir a transcript-full.

Nivel 2 (ML, opcional): usa whisperx/pyannote sobre o audio para separar cada
locutor individualmente. Requer o extra [diarization] instalado.
"""

from __future__ import annotations

from dataclasses import dataclass

from .transcribe import TrackTranscript

# Rotulos por idioma para os falantes no nivel 1.
_LABELS = {
    "pt": {"you": "Voce", "others": "Participantes"},
    "es": {"you": "Tu", "others": "Participantes"},
    "en": {"you": "You", "others": "Participants"},
}


class DiarizeError(RuntimeError):
    pass


@dataclass
class Utterance:
    speaker: str
    start: float
    text: str


def _labels_for(lang: str) -> dict[str, str]:
    return _LABELS.get(lang, _LABELS["pt"])


def build_level1(
    mic: TrackTranscript | None,
    system: TrackTranscript | None,
    lang: str = "pt",
) -> list[Utterance]:
    """Intercala os segmentos de mic (Voce) e system (Participantes) por tempo."""
    labels = _labels_for(lang)
    utterances: list[Utterance] = []

    if mic:
        for seg in mic.segments:
            utterances.append(Utterance(labels["you"], seg.start, seg.text))
    if system:
        for seg in system.segments:
            utterances.append(Utterance(labels["others"], seg.start, seg.text))

    utterances.sort(key=lambda u: u.start)
    return utterances


def render_transcript(utterances: list[Utterance]) -> str:
    """Formata as utterances como texto rotulado por locutor."""
    lines = [f"[{u.speaker}] {u.text}" for u in utterances]
    return "\n".join(lines)


def render_plain(transcript: TrackTranscript | None) -> str:
    """Formata uma unica Track como texto corrido, sem rotulo de locutor.

    Usado no modo 'import': a fonte e um unico arquivo externo (celular, video
    de call), entao nao ha separacao por Track e portanto nao ha diarizacao
    nivel 1. A saida e a transcricao corrida, um segmento por linha.
    """
    if transcript is None:
        return ""
    return "\n".join(seg.text for seg in transcript.segments)


def build_level2(audio_path, mic_transcript: TrackTranscript, lang: str = "pt"):
    """Diarizacao ML por locutor via whisperx. Opcional.

    Retorna uma lista de Utterance com rotulos por locutor (Locutor 1, 2, ...).
    """
    try:
        import whisperx  # noqa: F401
    except ImportError as exc:
        raise DiarizeError(
            "Nivel 2 requer o extra de diarizacao. Rode: pip install -e '.[diarization]'"
        ) from exc

    raise DiarizeError(
        "Diarizacao nivel 2 ainda nao implementada nesta versao. Use level1."
    )
