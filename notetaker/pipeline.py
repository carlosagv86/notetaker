"""Pipeline batch executado apos o stop: transcricao -> diarizacao -> Summary.

Roda de forma sincrona (a CLI a dispara em background via subprocess desanexado),
atualizando o meta.json a cada fase para permitir acompanhamento via `status`.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from . import diarize, transcribe
from .config import resolve_llm_command
from .prompts import resolve_output_language
from .storage import Meeting
from .summarize import generate_summary

# Callback de progresso: recebe (fase, mensagem). fase e um identificador
# estavel ('transcribing_mic', 'transcribing_system', 'diarizing',
# 'summarizing', 'done'); mensagem e texto legivel para exibir ao usuario.
ProgressCb = Callable[[str, str], None]


def _noop(phase: str, message: str) -> None:  # pragma: no cover
    pass


def process_meeting(meeting: Meeting, progress: ProgressCb | None = None) -> None:
    """Executa transcricao, diarizacao nivel 1/2 e geracao do Summary."""
    report = progress or _noop
    meta = meeting.read_meta()

    try:
        # --- Transcricao das Tracks ---
        meta.status = "transcribing"
        meeting.write_meta(meta)

        mic_t = None
        system_t = None
        timings: dict[str, dict] = {}

        device, _ = transcribe.detect_compute_device()
        report("device", f"  transcricao usando: {device.upper()} (modelo {meta.whisper_model})")

        def _fmt(s: "transcribe.TranscribeStats") -> str:
            return (
                f"{s.audio_seconds:.0f}s de audio em {s.transcribe_seconds:.0f}s "
                f"(RTF {s.rtf:.2f}x"
                + (f", modelo carregou em {s.model_load_seconds:.0f}s" if s.model_load_seconds > 0.5 else "")
                + ")"
            )

        has_mic = meeting.audio_mic.exists()
        has_system = meeting.audio_system.exists()

        if has_mic and has_system:
            gpu = transcribe.gpu_available()
            if gpu:
                # GPU: a paralelizacao por threads de CPU nao ajuda e duplicaria o
                # uso de VRAM. Transcreve sequencialmente com o modelo em cache;
                # a GPU ja e rapida (RTF baixo).
                report("transcribing", "transcrevendo as duas trilhas (GPU)...")
                mic_t = transcribe.transcribe_track(
                    meeting.audio_mic, meta.whisper_model, meta.lang
                )
                system_t = transcribe.transcribe_track(
                    meeting.audio_system, meta.whisper_model, meta.lang
                )
            else:
                # CPU: transcreve em paralelo com modelos separados, cada um
                # limitado a metade dos cores. O CTranslate2 ja satura os cores,
                # entao dividir os threads evita contencao e reduz o tempo total
                # (vs. sequencial). Os modelos sao carregados sequencialmente antes
                # (o carregador nao e seguro para uso concorrente) e a transcricao
                # roda em threads.
                report("transcribing", "transcrevendo as duas trilhas em paralelo...")
                half = max(1, (os.cpu_count() or 2) // 2)
                model_mic = transcribe.load_model(meta.whisper_model, cpu_threads=half)
                model_system = transcribe.load_model(meta.whisper_model, cpu_threads=half)

                def _do(path, model):
                    return transcribe.transcribe_track(
                        path, meta.whisper_model, meta.lang, preloaded_model=model
                    )

                with ThreadPoolExecutor(max_workers=2) as ex:
                    fut_mic = ex.submit(_do, meeting.audio_mic, model_mic)
                    fut_system = ex.submit(_do, meeting.audio_system, model_system)
                    mic_t = fut_mic.result()
                    system_t = fut_system.result()

            meeting.transcript_mic.write_text(mic_t.text, encoding="utf-8")
            meeting.transcript_system.write_text(system_t.text, encoding="utf-8")
            timings["mic"] = vars(mic_t.stats)
            timings["system"] = vars(system_t.stats)
            report("stats_mic", "  mic: " + _fmt(mic_t.stats))
            report("stats_system", "  system: " + _fmt(system_t.stats))

        elif has_mic:
            report("transcribing_mic", "transcrevendo sua fala (mic)...")
            mic_t = transcribe.transcribe_track(
                meeting.audio_mic, meta.whisper_model, meta.lang
            )
            meeting.transcript_mic.write_text(mic_t.text, encoding="utf-8")
            timings["mic"] = vars(mic_t.stats)
            report("stats_mic", "  mic: " + _fmt(mic_t.stats))

        elif has_system:
            report("transcribing_system", "transcrevendo os participantes (system)...")
            system_t = transcribe.transcribe_track(
                meeting.audio_system, meta.whisper_model, meta.lang
            )
            meeting.transcript_system.write_text(system_t.text, encoding="utf-8")
            timings["system"] = vars(system_t.stats)
            report("stats_system", "  system: " + _fmt(system_t.stats))

        meta.extra["timings"] = timings

        primary = mic_t or system_t
        if primary is None:
            raise RuntimeError("nenhuma Track de audio encontrada para transcrever")

        # Meeting Language efetiva: idioma detectado na Track mic (ou system).
        detected = primary.language
        meta.detected_lang = detected

        # --- Diarizacao ---
        report("diarizing", "organizando a transcricao por locutor...")
        if meta.mode == "import":
            # Fonte unica externa (celular, video): sem separacao por Track, logo
            # sem diarizacao nivel 1. Transcricao corrida, sem rotulos.
            full_text = diarize.render_plain(primary)
        else:
            if meta.diarization == "level2":
                diarize.build_level2(meeting.audio_mic, primary, detected)
            utterances = diarize.build_level1(mic_t, system_t, detected)
            full_text = diarize.render_transcript(utterances)
        meeting.transcript_full.write_text(full_text, encoding="utf-8")

        # --- Summary ---
        meta.status = "summarizing"
        meeting.write_meta(meta)

        report("summarizing", "gerando o resumo com o LLM...")
        out_lang = resolve_output_language(meta.output_lang, detected)
        md = generate_summary(
            full_text,
            meta.extra.get("llm_command", resolve_llm_command("kiro")),
            out_lang,
            title=meta.title,
        )
        meeting.resumo_md.write_text(md, encoding="utf-8")

        meta.status = "done"
        meeting.write_meta(meta)
        report("done", "concluido")

    except Exception as exc:  # noqa: BLE001
        meta.status = "error"
        meta.error = str(exc)
        meeting.write_meta(meta)
        raise
