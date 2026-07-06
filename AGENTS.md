# AGENTS.md

Notetaker: CLI that records meetings, transcribes locally with faster-whisper,
and generates a Markdown Summary by piping the transcript to an external LLM CLI.
Audio never leaves the machine; only text goes to the LLM Provider.

## Language & terminology (important)

- The codebase is **Portuguese-first**: comments, docstrings, user-facing
  strings, error messages, config, and docs are all in pt-BR. Match that when
  editing. Code identifiers are English.
- A precise domain glossary lives in `CONTEXT.md` and `README.md` ("Language"
  section). Use the canonical terms and honor the `_Avoid_` lists: **Meeting**
  (not sessao/call), **Track** (not canal/faixa), **Mode**, **Diarization**,
  **Summary** (not ata/resumo-as-code — the artifact file is `resumo.md`),
  **LLM Provider**, **Meeting Language**.

## Commands

- Run: `uv run notetaker <cmd>` or `./notetaker.sh <cmd>` (wrapper installs uv +
  ffmpeg, runs `uv sync`, then `uv run notetaker`).
- Setup env: `./notetaker.sh --setup`.
- There is **no test, lint, or typecheck tooling** configured (no pytest/ruff/
  mypy, no CI). Verify changes by running the CLI directly.
- Requires Python >= 3.11 and system `ffmpeg`. Optional extras:
  `.[diarization]` (whisperx), `.[gpu]` (NVIDIA CUDA libs).
- This directory is **not a git repository**.

## Architecture

Flow: `cli.py` (argparse subcommands) -> `pipeline.process_meeting` runs the
batch **after stop**: `transcribe` -> `diarize` -> `summarize` -> `llm`.

- `storage.py`: a **Meeting is a folder** `AAAA-MM-DD_HHMM_slug/`. `meta.json`
  is both the persisted state machine (`status`: recording|transcribing|
  summarizing|done|error) **and** the IPC channel between the foreground CLI and
  the detached background worker. Artifact paths are properties on `Meeting`.
- `config.py`: loaded from `~/.config/notetaker/config.toml`, auto-created with
  defaults on first run.
- `audio.py`: ffmpeg capture, one process **per Track** (base for level-1
  diarization). Platform backends: Linux PulseAudio (`pactl`), macOS
  AVFoundation, Windows DirectShow (`dshow`, devices by name). Public API is
  platform-agnostic; backend chosen at runtime. Detached spawn and the stop
  signal are also platform-specific: POSIX uses `start_new_session` + SIGINT;
  Windows uses `CREATE_NEW_PROCESS_GROUP` + `CTRL_BREAK_EVENT` (so ffmpeg
  finalizes the opus trailer).
- `prompts.py` / `summarize.py` / `llm.py`: prompt built with section titles per
  language; LLM output delimited by sentinels (`===NOTETAKER-RESUMO-*===`) and
  extracted tolerating ANSI/banners.

## Non-obvious gotchas

- **Background processing**: `stop` (without `--wait`) spawns a detached
  `python -m notetaker.cli _process <path>` via `start_new_session=True`. `_process`
  is a hidden subcommand. Progress is tracked only through `meta.json` (`status`).
- **ffmpeg lifecycle**: recorders run in a new session so terminal Ctrl+C does
  not hit them; `stop_recording` sends a single SIGINT per PID and waits, so the
  opus container trailer is written. Do not send a second signal.
- **Recording size reads from ffmpeg logs, not disk**: the opus muxer flushes
  bytes only on finalize, so the file is 0 B mid-recording. `read_progress`
  parses `size=`/`time=` from `ffmpeg-*.log`.
- **faster-whisper model loader is not thread-safe**: the CPU parallel path
  (two Tracks) loads both models sequentially with `load_model(use_cache=False)`,
  each capped at half the cores, then transcribes in threads. GPU path
  transcribes sequentially (parallel threads waste VRAM).
- **Compute device**: CTranslate2 (faster-whisper backend) accelerates **only on
  NVIDIA CUDA**; no Metal/MPS, so macs always use CPU. Detection is memoized in
  `transcribe._compute_device`.
- **Devices are auto-detected at `start`**, not fixed in config (ADR 0005).
  Empty config source = auto (PulseAudio default source/sink, or AVFoundation
  index / BlackHole loopback on mac).
- **Diarization level2 is not implemented** — `diarize.build_level2` raises. Only
  level1 (Track-based: mic="Voce" vs system="Participantes") works.
- **Meeting Language** is detected from the mic Track transcript and stored as
  `meta.detected_lang`; it drives the default Summary language.

## Design invariants (see `docs/adr/`)

- 0001: LLM only via external CLI (stdin->stdout), never direct API. Output is
  Markdown between sentinels.
- 0002: audio stays local; only transcript text is sent to the LLM.
- 0003: transcription is batch after `stop`, never live (target machine is CPU-only).
- 0004: Tracks are always recorded separately so level2 can be added later
  without changing capture.
- 0005: devices resolved at runtime; config holds optional overrides only.
