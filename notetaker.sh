#!/usr/bin/env bash
#
# notetaker.sh — instala dependencias e executa o Notetaker via uv.
#
# Este script prepara tudo que o Notetaker precisa e o executa:
#   1. Instala o 'uv' (gerenciador de pacotes/venv Python) se ausente.
#   2. Verifica o 'ffmpeg' (necessario para capturar audio) e tenta instala-lo.
#   3. Cria/sincroniza o ambiente virtual com 'uv sync'.
#   4. Executa o Notetaker via 'uv run', repassando os argumentos recebidos.
#
set -euo pipefail

# Diretorio do projeto = diretorio deste script (funciona de qualquer lugar).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --------------------------------------------------------------------------- #
# Cores (apenas em terminal)
# --------------------------------------------------------------------------- #
if [ -t 1 ]; then
    C_BOLD="$(printf '\033[1m')"; C_DIM="$(printf '\033[2m')"
    C_GREEN="$(printf '\033[32m')"; C_YELLOW="$(printf '\033[33m')"
    C_RED="$(printf '\033[31m')"; C_RESET="$(printf '\033[0m')"
else
    C_BOLD=""; C_DIM=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_RESET=""
fi

ts()    { date '+%H:%M:%S'; }

info()  { printf '%s[%s]%s %s==>%s %s\n' "$C_DIM" "$(ts)" "$C_RESET" "$C_GREEN" "$C_RESET" "$*"; }
warn()  { printf '%s[%s]%s %s[aviso]%s %s\n' "$C_DIM" "$(ts)" "$C_RESET" "$C_YELLOW" "$C_RESET" "$*" >&2; }
error() { printf '%s[%s]%s %s[erro]%s %s\n' "$C_DIM" "$(ts)" "$C_RESET" "$C_RED" "$C_RESET" "$*" >&2; }

# --------------------------------------------------------------------------- #
# Ajuda
# --------------------------------------------------------------------------- #
usage() {
    cat <<EOF
${C_BOLD}notetaker.sh${C_RESET} — grava reunioes, transcreve localmente e gera um resumo com IA.

${C_BOLD}USO${C_RESET}
    ./notetaker.sh <comando> [opcoes]
    ./notetaker.sh --setup        # apenas instala/atualiza as dependencias
    ./notetaker.sh --help         # esta ajuda

Na primeira execucao, o script instala o 'uv' (se necessario), verifica o
'ffmpeg' e cria o ambiente virtual automaticamente. Depois, todos os argumentos
sao repassados ao Notetaker.

${C_BOLD}COMANDOS DO NOTETAKER${C_RESET}
    start "<titulo>"    Inicia a gravacao de uma reuniao.
                        Acompanha ao vivo (tempo + tamanho); Ctrl+C encerra
                        e gera o resumo.
    stop                Encerra a reuniao em andamento e gera o resumo.
    status              Mostra o estado da reuniao mais recente.
    list                Lista todas as reunioes gravadas.
    devices             Mostra os dispositivos de audio detectados.
    setup               Assistente interativo de configuracao (idioma, modelo,
                        LLM, dispositivos). Grava o config.toml.
    summarize <pasta>   Regenera o resumo a partir da transcricao existente.
    retry <pasta>       Reprocessa uma reuniao que falhou (transcricao,
                        diarizacao e resumo, do zero, a partir do audio
                        gravado). Roda em background; use --wait para
                        acompanhar em primeiro plano.

${C_BOLD}OPCOES DO 'start'${C_RESET}
    --mode online|presencial|listener
                                 online = mic + audio do sistema (padrao)
                                 presencial = apenas o microfone
                                 listener = apenas o audio do sistema (ouvinte)
    --lang auto|pt|es|en         Idioma falado na reuniao (padrao: config)
    --output-lang meeting|pt|es|en
                                 Idioma do resumo (padrao: idioma da reuniao)
    --diarization level1|level2  level1 = voce vs. participantes (padrao)
                                 level2 = identifica cada locutor (ML, requer
                                          extra de diarizacao)
    --no-watch                   Nao acompanha ao vivo; use 'stop' depois.

${C_BOLD}EXEMPLOS${C_RESET}
    ./notetaker.sh --setup
    ./notetaker.sh start "planejamento sprint"
    ./notetaker.sh start "reuniao cliente" --mode presencial
    ./notetaker.sh start "weekly" --lang en --output-lang pt
    ./notetaker.sh status
    ./notetaker.sh list
    ./notetaker.sh summarize 2026-07-02_1234_planejamento-sprint
    ./notetaker.sh retry 2026-07-02_1234_planejamento-sprint --wait

${C_BOLD}CONFIGURACAO${C_RESET}
    Editavel em: ~/.config/notetaker/config.toml
    (modelo Whisper, idioma padrao, comando do LLM, dispositivos de audio)
EOF
}

# --------------------------------------------------------------------------- #
# Garante o uv instalado
# --------------------------------------------------------------------------- #
ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        return
    fi
    # Locais comuns onde o uv e instalado, caso nao esteja no PATH.
    for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        if [ -x "$candidate" ]; then
            export PATH="$(dirname "$candidate"):$PATH"
            return
        fi
    done

    info "uv nao encontrado; instalando..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        error "curl ou wget sao necessarios para instalar o uv. Instale um deles."
        exit 1
    fi

    # O instalador coloca o uv em ~/.local/bin (ou ~/.cargo/bin).
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv >/dev/null 2>&1; then
        error "uv instalado, mas nao encontrado no PATH. Abra um novo terminal e tente novamente."
        exit 1
    fi
    info "uv instalado: $(uv --version)"
}

# --------------------------------------------------------------------------- #
# Verifica/instala o ffmpeg (dependencia de sistema para captura de audio)
# --------------------------------------------------------------------------- #
ensure_ffmpeg() {
    if command -v ffmpeg >/dev/null 2>&1; then
        return
    fi
    warn "ffmpeg nao encontrado (necessario para gravar audio)."
    if command -v apt-get >/dev/null 2>&1; then
        info "tentando instalar via apt-get (pode pedir sua senha)..."
        sudo apt-get update -qq && sudo apt-get install -y ffmpeg
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y ffmpeg
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --noconfirm ffmpeg
    elif command -v brew >/dev/null 2>&1; then
        brew install ffmpeg
    else
        error "nao foi possivel instalar o ffmpeg automaticamente. Instale-o manualmente."
        exit 1
    fi
}

# --------------------------------------------------------------------------- #
# Sincroniza o ambiente virtual (cria .venv e instala dependencias)
# --------------------------------------------------------------------------- #
sync_env() {
    info "sincronizando o ambiente (uv sync)..."
    uv sync
}

# --------------------------------------------------------------------------- #
# Fluxo principal
# --------------------------------------------------------------------------- #
main() {
    # Ajuda quando pedida explicitamente ou sem argumentos.
    case "${1:-}" in
        -h|--help|help|"")
            usage
            exit 0
            ;;
    esac

    ensure_uv

    # Modo setup: apenas prepara o ambiente e sai.
    if [ "${1:-}" = "--setup" ]; then
        ensure_ffmpeg
        sync_env
        info "pronto. Use: ./notetaker.sh start \"minha reuniao\""
        exit 0
    fi

    # ffmpeg so e essencial para gravar (start); para os demais comandos
    # evitamos travar caso ainda nao esteja instalado.
    if [ "${1:-}" = "start" ]; then
        ensure_ffmpeg
    fi

    # Garante o ambiente sincronizado (rapido quando ja esta atualizado).
    sync_env

    info "executando: notetaker $*"
    exec uv run notetaker "$@"
}

main "$@"
