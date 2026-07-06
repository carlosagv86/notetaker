"""Captura de audio via ffmpeg, com backend por plataforma.

Linux:   backend PulseAudio/PipeWire (`-f pulse`), dispositivos via `pactl`.
macOS:   backend AVFoundation (`-f avfoundation`), dispositivos via ffmpeg. O
         audio de saida (participantes, modo online) exige um dispositivo virtual
         como o BlackHole, pois o macOS nao expoe a saida para captura
         nativamente.
Windows: backend DirectShow (`-f dshow`), dispositivos via ffmpeg. O audio de
         saida (participantes, modo online) exige um dispositivo virtual (VB-CABLE,
         VoiceMeeter) ou o "Stereo Mix"/"Mixagem estereo" da placa, pois o dshow
         nao expoe a saida para captura nativamente.

A API publica (resolve_devices, start_recording, stop_recording, read_progress)
e a mesma em qualquer plataforma; o backend correto e escolhido em tempo de
execucao.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass

from .storage import Meeting


class AudioError(RuntimeError):
    pass


@dataclass
class Devices:
    mic_source: str
    monitor_source: str  # vazio no modo presencial

    # Formato de entrada do ffmpeg para esta plataforma ("pulse" ou "avfoundation").
    input_format: str = "pulse"


def _run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise AudioError(f"comando nao encontrado: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise AudioError(
            f"falha ao executar {' '.join(cmd)}: {exc.stderr.strip()}"
        ) from exc
    return out.stdout.strip()


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _is_windows() -> bool:
    return os.name == "nt"


def _detached_popen_kwargs() -> dict:
    """kwargs para desanexar um subprocesso do terminal/shell atual.

    POSIX: nova sessao (setsid), para que o Ctrl+C do terminal nao atinja o
    processo diretamente. Windows: novo grupo de processo, requisito para depois
    entregar o CTRL_BREAK_EVENT em stop_recording; sem novo grupo, o ffmpeg nao
    finalizaria o container opus corretamente.
    """
    if _is_windows():
        # CREATE_NEW_PROCESS_GROUP so existe no subprocess do Windows.
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP")
        return {"creationflags": flags}
    return {"start_new_session": True}


def detached_worker_kwargs() -> dict:
    """kwargs para o worker de background (pipeline pos-stop), sem TTY.

    Diferente dos recorders, o worker nao precisa receber sinal de parada; ele
    apenas roda ate concluir. No Windows, combina novo grupo de processo com
    DETACHED_PROCESS para desanexar totalmente do console do shell. Em POSIX,
    nova sessao (setsid).
    """
    if _is_windows():
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP") | getattr(
            subprocess, "DETACHED_PROCESS"
        )
        return {"creationflags": flags}
    return {"start_new_session": True}


def _send_stop_signal(pid: int) -> None:
    """Envia o sinal que faz o ffmpeg finalizar o container opus e sair.

    POSIX: SIGINT ao processo. Windows: CTRL_BREAK_EVENT ao grupo de processo
    (criado com CREATE_NEW_PROCESS_GROUP no start_recording); o ffmpeg trata como
    interrupcao e escreve o trailer do opus.
    """
    try:
        if _is_windows():
            # CTRL_BREAK_EVENT so existe no signal do Windows.
            os.kill(pid, getattr(signal, "CTRL_BREAK_EVENT"))
        else:
            os.kill(pid, signal.SIGINT)
    except (ProcessLookupError, OSError):
        pass


def _check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        if _is_macos():
            hint = "brew install ffmpeg"
        elif _is_windows():
            hint = "winget install Gyan.FFmpeg (ou choco install ffmpeg)"
        else:
            hint = "sudo apt install ffmpeg"
        raise AudioError(f"ffmpeg nao encontrado. Instale com: {hint}")


# =========================================================================== #
# Backend Linux (PulseAudio / PipeWire)
# =========================================================================== #
def _linux_check() -> None:
    if shutil.which("pactl") is None:
        raise AudioError("pactl nao encontrado. PulseAudio/PipeWire e necessario.")


def _linux_default_source() -> str:
    return _run(["pactl", "get-default-source"])


def _linux_default_sink() -> str:
    return _run(["pactl", "get-default-sink"])


def _linux_monitor() -> str:
    """O monitor source correspondente ao default sink atual."""
    return f"{_linux_default_sink()}.monitor"


def _linux_resolve(mode: str, mic_override: str, monitor_override: str) -> Devices:
    if mode == "listener":
        # So a saida do sistema (voz dos participantes); o mic nao e gravado.
        monitor = monitor_override or _linux_monitor()
        return Devices(mic_source="", monitor_source=monitor, input_format="pulse")
    mic = mic_override or _linux_default_source()
    if mode == "presencial":
        return Devices(mic_source=mic, monitor_source="", input_format="pulse")
    monitor = monitor_override or _linux_monitor()
    return Devices(mic_source=mic, monitor_source=monitor, input_format="pulse")


def _linux_describe() -> list[str]:
    lines = [
        f"backend:                PulseAudio/PipeWire",
        f"default source (mic):   {_linux_default_source()}",
        f"default sink:           {_linux_default_sink()}",
        f"monitor (system audio): {_linux_monitor()}",
    ]
    return lines


# =========================================================================== #
# Backend macOS (AVFoundation)
# =========================================================================== #
# Nome do dispositivo virtual usado para capturar o audio de saida no Mac.
_MACOS_LOOPBACK_HINTS = ("blackhole", "loopback", "soundflower")

# Linha do -list_devices: "[AVFoundation indev @ 0x..] [0] Device Name"
_AVF_DEVICE_RE = re.compile(r"\]\s*\[(\d+)\]\s*(.+)$")


def _macos_list_audio_devices() -> list[tuple[int, str]]:
    """Lista (indice, nome) dos dispositivos de audio via avfoundation.

    O ffmpeg imprime a lista no stderr e sai com codigo != 0 (comportamento
    esperado do -list_devices), entao nao usamos check=True aqui.
    """
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True,
        text=True,
    )
    text = proc.stderr
    devices: list[tuple[int, str]] = []
    in_audio = False
    for line in text.splitlines():
        low = line.lower()
        if "avfoundation audio devices" in low:
            in_audio = True
            continue
        if "avfoundation video devices" in low:
            in_audio = False
            continue
        if not in_audio:
            continue
        m = _AVF_DEVICE_RE.search(line)
        if m:
            devices.append((int(m.group(1)), m.group(2).strip()))
    return devices


def _macos_find_loopback(devices: list[tuple[int, str]]) -> int | None:
    """Encontra o indice de um dispositivo de loopback (BlackHole etc.)."""
    for idx, name in devices:
        if any(hint in name.lower() for hint in _MACOS_LOOPBACK_HINTS):
            return idx
    return None


def _macos_resolve(mode: str, mic_override: str, monitor_override: str) -> Devices:
    devices = _macos_list_audio_devices()
    if not devices and not mic_override:
        raise AudioError(
            "nenhum dispositivo de audio detectado via avfoundation. "
            "Verifique as permissoes de microfone do terminal em "
            "Ajustes > Privacidade e Seguranca > Microfone."
        )

    # Mic: override explicito, ou o primeiro dispositivo de audio (indice 0 e o
    # default de entrada na maioria dos Macs).
    mic = mic_override or (str(devices[0][0]) if devices else "0")

    if mode == "presencial":
        return Devices(mic_source=mic, monitor_source="", input_format="avfoundation")

    # Online e listener precisam do audio de saida, que no Mac vem de um
    # dispositivo virtual.
    if monitor_override:
        monitor = monitor_override
    else:
        idx = _macos_find_loopback(devices)
        if idx is None:
            listed = ", ".join(f"[{i}] {n}" for i, n in devices) or "(nenhum)"
            raise AudioError(
                f"modo {mode} no macOS requer um dispositivo de audio virtual para "
                "capturar a voz dos participantes (o macOS nao expoe a saida "
                "nativamente). Instale o BlackHole (https://existential.audio/blackhole/), "
                "crie um Dispositivo Agregado com ele + sua saida, e use-o como saida "
                "durante a reuniao.\n"
                f"Dispositivos de audio detectados: {listed}\n"
                "Ou use --mode presencial para gravar apenas o microfone."
            )
        monitor = str(idx)

    if mode == "listener":
        # So a saida do sistema (voz dos participantes); o mic nao e gravado.
        return Devices(mic_source="", monitor_source=monitor, input_format="avfoundation")

    return Devices(mic_source=mic, monitor_source=monitor, input_format="avfoundation")


def _macos_describe() -> list[str]:
    devices = _macos_list_audio_devices()
    lines = ["backend:                AVFoundation (macOS)"]
    for idx, name in devices:
        lines.append(f"  [{idx}] {name}")
    loop = _macos_find_loopback(devices)
    if loop is not None:
        lines.append(f"loopback (system audio): indice {loop}")
    else:
        lines.append(
            "loopback (system audio): nao encontrado (instale o BlackHole para o modo online)"
        )
    return lines


# =========================================================================== #
# Backend Windows (DirectShow)
# =========================================================================== #
# Dispositivos virtuais/de loopback comuns para capturar o audio de saida.
# "Stereo Mix"/"Mixagem estereo" e o loopback nativo de algumas placas (quando
# habilitado); VB-CABLE e VoiceMeeter sao dispositivos virtuais de terceiros.
_WINDOWS_LOOPBACK_HINTS = (
    "stereo mix",
    "mixagem estereo",
    "mixagem estéreo",
    "cable output",
    "cable",
    "voicemeeter",
    "virtual",
    "what u hear",
    "wave out",
)

# Linha do -list_devices do dshow: '"Nome do Dispositivo" (audio)' ou, em
# versoes do ffmpeg, '[dshow @ 0x..] "Nome do Dispositivo"'. Extraimos o nome
# entre aspas.
_DSHOW_DEVICE_RE = re.compile(r'"([^"]+)"')


def _windows_list_audio_devices() -> list[str]:
    """Lista os nomes dos dispositivos de audio de entrada via dshow.

    O ffmpeg imprime a lista no stderr e sai com codigo != 0 (comportamento
    esperado do -list_devices), entao nao usamos check=True aqui.

    No dshow os dispositivos sao referenciados por nome (nao por indice), e o
    ffmpeg lista dispositivos de video e audio juntos; filtramos a secao de
    audio.
    """
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-f", "dshow", "-list_devices", "true", "-i", "dummy"],
        capture_output=True,
        text=True,
    )
    text = proc.stderr
    devices: list[str] = []
    in_audio = False
    for line in text.splitlines():
        low = line.lower()
        # Cabecalhos de secao variam entre versoes do ffmpeg:
        # "DirectShow audio devices" / "DirectShow video devices". A linha de
        # video pode conter "(some may be both video and audio devices)", entao
        # checamos "video devices" primeiro para nao classifica-la como audio.
        if "video devices" in low:
            in_audio = False
            continue
        if "audio devices" in low:
            in_audio = True
            continue
        if not in_audio:
            continue
        # Ignora a linha "Alternative name ..." que o ffmpeg imprime.
        if "alternative name" in low:
            continue
        m = _DSHOW_DEVICE_RE.search(line)
        if m:
            devices.append(m.group(1).strip())
    return devices


def _windows_find_loopback(devices: list[str]) -> str | None:
    """Encontra o nome de um dispositivo de loopback/virtual (Stereo Mix etc.)."""
    for name in devices:
        if any(hint in name.lower() for hint in _WINDOWS_LOOPBACK_HINTS):
            return name
    return None


def _windows_resolve(mode: str, mic_override: str, monitor_override: str) -> Devices:
    devices = _windows_list_audio_devices()
    if not devices and not mic_override:
        raise AudioError(
            "nenhum dispositivo de audio detectado via dshow. Verifique se o "
            "microfone esta conectado e habilitado nas Configuracoes de Som do "
            "Windows, e as permissoes de microfone do app de terminal em "
            "Configuracoes > Privacidade e seguranca > Microfone."
        )

    # Mic: override explicito, ou o primeiro dispositivo de audio detectado.
    mic = mic_override or (devices[0] if devices else "")
    mic_arg = f"audio={mic}"

    if mode == "presencial":
        return Devices(mic_source=mic_arg, monitor_source="", input_format="dshow")

    # Online e listener precisam do audio de saida, que no Windows vem de um
    # dispositivo virtual ou do "Stereo Mix" (quando a placa expoe e ele esta
    # habilitado).
    if monitor_override:
        monitor = monitor_override
    else:
        found = _windows_find_loopback(devices)
        if found is None:
            listed = ", ".join(f'"{n}"' for n in devices) or "(nenhum)"
            raise AudioError(
                f"modo {mode} no Windows requer um dispositivo de audio virtual ou o "
                '"Stereo Mix"/"Mixagem estereo" para capturar a voz dos participantes '
                "(o dshow nao expoe a saida nativamente). Habilite o Stereo Mix em "
                "Configuracoes de Som > Gravacao (se sua placa oferecer), ou instale o "
                "VB-CABLE (https://vb-audio.com/Cable/) ou o VoiceMeeter e roteie a saida "
                "para ele.\n"
                f"Dispositivos de audio detectados: {listed}\n"
                "Ou use --mode presencial para gravar apenas o microfone."
            )
        monitor = found

    monitor_arg = f"audio={monitor}"
    if mode == "listener":
        # So a saida do sistema (voz dos participantes); o mic nao e gravado.
        return Devices(mic_source="", monitor_source=monitor_arg, input_format="dshow")
    return Devices(mic_source=mic_arg, monitor_source=monitor_arg, input_format="dshow")


def _windows_describe() -> list[str]:
    devices = _windows_list_audio_devices()
    lines = ["backend:                DirectShow (Windows)"]
    for name in devices:
        lines.append(f'  "{name}"')
    loop = _windows_find_loopback(devices)
    if loop is not None:
        lines.append(f'loopback (system audio): "{loop}"')
    else:
        lines.append(
            "loopback (system audio): nao encontrado (habilite o Stereo Mix ou "
            "instale o VB-CABLE/VoiceMeeter para o modo online)"
        )
    return lines


# =========================================================================== #
# API publica (despacha para o backend da plataforma)
# =========================================================================== #
def check_dependencies() -> None:
    _check_ffmpeg()
    if _is_macos() or _is_windows():
        return  # avfoundation/dshow vem embutido no ffmpeg
    _linux_check()


def check_device_tooling() -> None:
    """Verifica apenas as ferramentas de deteccao de dispositivo (sem ffmpeg)."""
    if _is_macos() or _is_windows():
        _check_ffmpeg()  # no Mac/Windows, a listagem usa o proprio ffmpeg
    else:
        _linux_check()


def resolve_devices(
    mode: str,
    mic_override: str = "",
    monitor_override: str = "",
) -> Devices:
    """Resolve os dispositivos a usar no momento do start.

    Overrides do config tem prioridade; vazio = deteccao automatica.
    """
    check_dependencies()
    if _is_macos():
        return _macos_resolve(mode, mic_override, monitor_override)
    if _is_windows():
        return _windows_resolve(mode, mic_override, monitor_override)
    return _linux_resolve(mode, mic_override, monitor_override)


def describe_devices() -> list[str]:
    """Linhas descritivas dos dispositivos detectados, para o comando `devices`."""
    check_device_tooling()
    if _is_macos():
        return _macos_describe()
    if _is_windows():
        return _windows_describe()
    return _linux_describe()


def _ffmpeg_track_cmd(source: str, output_path: str, input_format: str) -> list[str]:
    """ffmpeg gravando uma unica fonte para opus mono."""
    return [
        "ffmpeg",
        "-y",
        "-f", input_format,
        "-i", source,
        "-ac", "1",
        "-c:a", "libopus",
        "-b:a", "24k",
        output_path,
    ]


def import_audio(src, dest) -> None:
    """Extrai/converte o audio de um arquivo externo para opus mono (24k).

    Aceita tanto arquivos de audio (m4a, mp3, wav, opus, etc.) quanto de video
    (mp4, mkv, mov, etc.): o `-vn` descarta qualquer trilha de video e o ffmpeg
    extrai apenas o audio, reencodando para o mesmo formato das Tracks gravadas
    (opus mono 24k) para manter a pipeline homogenea.

    Diferente das Tracks gravadas ao vivo, aqui ha uma unica fonte externa
    (celular, gravador, video de call), entao nao ha separacao de locutor por
    Track — o modo 'import' gera uma transcricao corrida (sem rotulos).
    """
    _check_ffmpeg()
    from pathlib import Path

    src = Path(src)
    dest = Path(dest)
    if not src.exists():
        raise AudioError(f"arquivo nao encontrado: {src}")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(src),
        "-vn",              # ignora trilha de video; extrai apenas o audio
        "-ac", "1",
        "-c:a", "libopus",
        "-b:a", "24k",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        detail = stderr.splitlines()[-1] if stderr else "erro desconhecido"
        raise AudioError(f"falha ao extrair o audio de {src.name}: {detail}")
    if not dest.exists() or dest.stat().st_size == 0:
        raise AudioError(
            f"nenhuma trilha de audio encontrada em {src.name}. "
            "O arquivo contem audio?"
        )


def start_recording(meeting: Meeting, devices: Devices, mode: str) -> list[int]:
    """Inicia a gravacao das Tracks em background. Retorna os PIDs do ffmpeg.

    Uma Track por processo ffmpeg: garante Tracks separadas (base para a
    diarizacao nivel 1) e evita mixagem prematura. Quais Tracks sao gravadas
    depende dos sources resolvidos para o modo: presencial so tem mic, listener
    so tem system, online tem ambos.

    Os processos rodam desanexados do terminal (POSIX: nova sessao via
    start_new_session; Windows: novo grupo de processo) para que o Ctrl+C do
    terminal nao os atinja diretamente: o encerramento fica sob controle
    exclusivo de stop_recording (um unico sinal de parada), garantindo que o
    ffmpeg finalize o container opus corretamente. O stderr vai para um log por
    Track, util para diagnostico.
    """
    pids: list[int] = []
    fmt = devices.input_format
    popen_kwargs = _detached_popen_kwargs()

    def _spawn(source: str, out_path, log_path) -> int:
        log = open(log_path, "wb")
        proc = subprocess.Popen(
            _ffmpeg_track_cmd(source, str(out_path), fmt),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=log,
            **popen_kwargs,
        )
        return proc.pid

    if devices.mic_source:
        pids.append(
            _spawn(devices.mic_source, meeting.audio_mic, meeting.ffmpeg_log_mic)
        )

    if devices.monitor_source:
        pids.append(
            _spawn(
                devices.monitor_source,
                meeting.audio_system,
                meeting.ffmpeg_log_system,
            )
        )

    return pids


def stop_recording(pids: list[int], timeout: float = 10.0) -> None:
    """Encerra os ffmpeg com o sinal de parada e aguarda cada um finalizar.

    O sinal (POSIX: SIGINT; Windows: CTRL_BREAK_EVENT) faz o ffmpeg escrever o
    trailer do container opus e sair. Enviamos apenas um sinal por processo e
    esperamos ele terminar, para nao corromper a saida com um segundo sinal.
    """
    for pid in pids:
        _send_stop_signal(pid)

    # Aguarda cada processo sair (ate o timeout), para garantir que o container
    # opus foi finalizado antes de transcrever.
    deadline = time.time() + timeout
    for pid in pids:
        while is_running(pid) and time.time() < deadline:
            time.sleep(0.1)


def _windows_is_running(pid: int) -> bool:
    """Verifica se um PID esta ativo no Windows via OpenProcess/GetExitCodeProcess."""
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def is_running(pid: int) -> bool:
    if _is_windows():
        return _windows_is_running(pid)
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


# Extrai o ultimo "size=  123kB" e o ultimo "time=00:00:12.34" do log do ffmpeg.
_SIZE_RE = re.compile(r"size=\s*(\d+)\s*([kKmMgG]?i?)B")
_TIME_RE = re.compile(r"time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)")

_SIZE_UNIT = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}


def read_progress(log_paths: list) -> tuple[int, float]:
    """Le o tamanho (bytes) e o tempo (segundos) capturados dos logs do ffmpeg.

    O muxer opus so descarrega os dados no arquivo ao finalizar, entao o tamanho
    em disco fica 0 durante a gravacao. O log do ffmpeg, porem, reporta o
    'size=' e 'time=' correntes — usamos ele como fonte de verdade ao vivo.

    Retorna (soma_bytes, maior_tempo) agregando todas as Tracks.
    """
    total_bytes = 0
    max_time = 0.0
    for path in log_paths:
        try:
            data = open(path, "rb").read()
        except OSError:
            continue
        text = data.decode("utf-8", "ignore")

        size_matches = _SIZE_RE.findall(text)
        if size_matches:
            num, unit = size_matches[-1]
            total_bytes += int(num) * _SIZE_UNIT.get(unit.lower().rstrip("i"), 1)

        time_matches = _TIME_RE.findall(text)
        if time_matches:
            h, m, s = time_matches[-1]
            secs = int(h) * 3600 + int(m) * 60 + float(s)
            max_time = max(max_time, secs)

    return total_bytes, max_time
