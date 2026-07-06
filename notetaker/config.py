"""Carrega e cria o config do Notetaker (~/.config/notetaker/config.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "notetaker" / "config.toml"

DEFAULT_CONFIG_TOML = """\
# Config do Notetaker. Campos vazios de dispositivo = deteccao automatica.
storage_root = "~/notetaker"

[audio]
# Vazio = auto. Linux: usa o default source/sink do PulseAudio. macOS: usa o
# indice de dispositivo do avfoundation (mic = indice do microfone; monitor =
# indice do dispositivo de loopback tipo BlackHole, necessario no modo online).
# Windows: usa o nome do dispositivo do dshow (mic = nome do microfone; monitor
# = nome do Stereo Mix ou dispositivo virtual tipo VB-CABLE, necessario no modo
# online).
mic_source = ""
monitor_source = ""

[whisper]
model = "medium"       # tiny | base | small | medium | large-v3
language = "auto"      # auto | pt | es | en
# GPU NVIDIA (cuda) e usada automaticamente quando detectada; senao, CPU.

[summary]
# "meeting" = mesmo idioma da reuniao. Ou fixe: pt | es | en
language = "meeting"

[llm]
# LLM Provider usado para gerar o Summary a partir da transcricao (via stdin).
provider = "kiro"      # kiro | claude
"""


@dataclass
class AudioConfig:
    mic_source: str = ""
    monitor_source: str = ""


@dataclass
class WhisperConfig:
    model: str = "medium"
    language: str = "auto"


@dataclass
class SummaryConfig:
    language: str = "meeting"


# Providers de LLM suportados e o comando de CLI correspondente. O comando
# recebe a transcricao via stdin e devolve o Summary em Markdown pelo stdout.
LLM_PROVIDER_COMMANDS: dict[str, str] = {
    "kiro": "kiro-cli chat --no-interactive",
    "claude": "claude -p",
}


class InvalidLLMProviderError(ValueError):
    pass


def resolve_llm_command(provider: str) -> str:
    """Mapeia o LLM Provider (kiro|claude) para o comando de CLI real."""
    try:
        return LLM_PROVIDER_COMMANDS[provider]
    except KeyError:
        opcoes = ", ".join(LLM_PROVIDER_COMMANDS)
        raise InvalidLLMProviderError(
            f"LLM Provider invalido: '{provider}'. Opcoes: {opcoes}."
        ) from None


@dataclass
class LLMConfig:
    provider: str = "kiro"


@dataclass
class Config:
    storage_root: Path = field(default_factory=lambda: Path.home() / "notetaker")
    audio: AudioConfig = field(default_factory=AudioConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    summary: SummaryConfig = field(default_factory=SummaryConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)


def _expand(path_str: str) -> Path:
    return Path(path_str).expanduser()


def config_exists() -> bool:
    """Indica se o config ja foi criado (usado para detectar a primeira execucao)."""
    return CONFIG_PATH.exists()


def ensure_config() -> Path:
    """Cria o config com defaults se ainda nao existir. Retorna o caminho."""
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    return CONFIG_PATH


def _toml_str(value: str) -> str:
    """Escapa uma string para valor TOML entre aspas."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_config_toml(cfg: Config) -> str:
    """Renderiza um Config como TOML comentado (mesmo formato do default)."""
    storage = str(cfg.storage_root)
    # Preserva o "~" quando o storage_root esta dentro do HOME do usuario.
    home = str(Path.home())
    if storage == home:
        storage = "~"
    elif storage.startswith(home + "/"):
        storage = "~" + storage[len(home):]
    return f"""\
# Config do Notetaker. Campos vazios de dispositivo = deteccao automatica.
storage_root = {_toml_str(storage)}

[audio]
# Vazio = auto. Linux: usa o default source/sink do PulseAudio. macOS: usa o
# indice de dispositivo do avfoundation (mic = indice do microfone; monitor =
# indice do dispositivo de loopback tipo BlackHole, necessario no modo online).
# Windows: usa o nome do dispositivo do dshow (mic = nome do microfone; monitor
# = nome do Stereo Mix ou dispositivo virtual tipo VB-CABLE, necessario no modo
# online).
mic_source = {_toml_str(cfg.audio.mic_source)}
monitor_source = {_toml_str(cfg.audio.monitor_source)}

[whisper]
model = {_toml_str(cfg.whisper.model)}       # tiny | base | small | medium | large-v3
language = {_toml_str(cfg.whisper.language)}      # auto | pt | es | en
# GPU NVIDIA (cuda) e usada automaticamente quando detectada; senao, CPU.

[summary]
# "meeting" = mesmo idioma da reuniao. Ou fixe: pt | es | en
language = {_toml_str(cfg.summary.language)}

[llm]
# LLM Provider usado para gerar o Summary a partir da transcricao (via stdin).
provider = {_toml_str(cfg.llm.provider)}      # kiro | claude
"""


def write_config(cfg: Config) -> Path:
    """Grava o config renderizado a partir de um Config. Retorna o caminho."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(render_config_toml(cfg), encoding="utf-8")
    return CONFIG_PATH


def load_config() -> Config:
    """Carrega o config, criando defaults na primeira execucao."""
    ensure_config()
    with CONFIG_PATH.open("rb") as fh:
        data = tomllib.load(fh)

    audio = data.get("audio", {})
    whisper = data.get("whisper", {})
    summary = data.get("summary", {})
    llm_data = data.get("llm", {})
    provider = llm_data.get("provider", "kiro")
    if provider not in LLM_PROVIDER_COMMANDS:
        opcoes = ", ".join(LLM_PROVIDER_COMMANDS)
        raise InvalidLLMProviderError(
            f"LLM Provider invalido em [llm].provider: '{provider}'. "
            f"Opcoes: {opcoes}."
        )

    return Config(
        storage_root=_expand(data.get("storage_root", "~/notetaker")),
        audio=AudioConfig(
            mic_source=audio.get("mic_source", ""),
            monitor_source=audio.get("monitor_source", ""),
        ),
        whisper=WhisperConfig(
            model=whisper.get("model", "medium"),
            language=whisper.get("language", "auto"),
        ),
        summary=SummaryConfig(
            language=summary.get("language", "meeting"),
        ),
        llm=LLMConfig(provider=provider),
    )
