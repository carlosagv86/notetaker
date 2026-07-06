@echo off
REM ==========================================================================
REM notetaker.bat -- instala dependencias e executa o Notetaker via uv (Windows).
REM
REM Este script prepara tudo que o Notetaker precisa e o executa:
REM   1. Instala o 'uv' (gerenciador de pacotes/venv Python) se ausente.
REM   2. Verifica o 'ffmpeg' (necessario para capturar audio) e tenta instala-lo.
REM   3. Cria/sincroniza o ambiente virtual com 'uv sync'.
REM   4. Executa o Notetaker via 'uv run', repassando os argumentos recebidos.
REM
REM Uso:
REM   notetaker.bat <comando> [opcoes]
REM   notetaker.bat --setup     (apenas instala/atualiza as dependencias)
REM   notetaker.bat --help
REM ==========================================================================
setlocal EnableDelayedExpansion

REM Diretorio do projeto = diretorio deste script (funciona de qualquer lugar).
cd /d "%~dp0"

REM --- Ajuda quando pedida explicitamente ou sem argumentos --------------------
if "%~1"=="" goto :usage
if /i "%~1"=="-h" goto :usage
if /i "%~1"=="--help" goto :usage
if /i "%~1"=="help" goto :usage

call :ensure_uv || exit /b 1

REM --- Modo setup: apenas prepara o ambiente e sai ----------------------------
if /i "%~1"=="--setup" (
    call :ensure_ffmpeg || exit /b 1
    call :sync_env || exit /b 1
    echo ==^> pronto. Use: notetaker.bat start "minha reuniao"
    exit /b 0
)

REM ffmpeg so e essencial para gravar (start); para os demais comandos
REM evitamos travar caso ainda nao esteja instalado.
if /i "%~1"=="start" (
    call :ensure_ffmpeg || exit /b 1
)

REM Garante o ambiente sincronizado (rapido quando ja esta atualizado).
call :sync_env || exit /b 1

echo ==^> executando: notetaker %*
uv run notetaker %*
exit /b %ERRORLEVEL%


REM ==========================================================================
REM Garante o uv instalado
REM ==========================================================================
:ensure_uv
where uv >nul 2>nul
if %ERRORLEVEL%==0 exit /b 0

REM Local comum onde o instalador coloca o uv.
if exist "%USERPROFILE%\.local\bin\uv.exe" (
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    exit /b 0
)

echo ==^> uv nao encontrado; instalando...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if %ERRORLEVEL%==0 (
    for /f "delims=" %%v in ('uv --version') do echo ==^> uv instalado: %%v
    exit /b 0
)
echo [erro] uv instalado, mas nao encontrado no PATH. Abra um novo terminal e tente novamente.
exit /b 1


REM ==========================================================================
REM Verifica/instala o ffmpeg (dependencia de sistema para captura de audio)
REM ==========================================================================
:ensure_ffmpeg
where ffmpeg >nul 2>nul
if %ERRORLEVEL%==0 exit /b 0

echo [aviso] ffmpeg nao encontrado (necessario para gravar audio).
where winget >nul 2>nul
if %ERRORLEVEL%==0 (
    echo ==^> tentando instalar via winget...
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    where ffmpeg >nul 2>nul
    if !ERRORLEVEL!==0 exit /b 0
    echo [aviso] instale o ffmpeg e abra um novo terminal para atualizar o PATH.
    exit /b 1
)
where choco >nul 2>nul
if %ERRORLEVEL%==0 (
    echo ==^> tentando instalar via choco...
    choco install ffmpeg -y
    where ffmpeg >nul 2>nul
    if !ERRORLEVEL!==0 exit /b 0
    echo [aviso] instale o ffmpeg e abra um novo terminal para atualizar o PATH.
    exit /b 1
)
echo [erro] nao foi possivel instalar o ffmpeg automaticamente (winget/choco ausentes).
echo        Baixe em https://ffmpeg.org/download.html e adicione ao PATH.
exit /b 1


REM ==========================================================================
REM Sincroniza o ambiente virtual (cria .venv e instala dependencias)
REM ==========================================================================
:sync_env
echo ==^> sincronizando o ambiente (uv sync)...
uv sync
exit /b %ERRORLEVEL%


REM ==========================================================================
REM Ajuda
REM ==========================================================================
:usage
echo notetaker.bat -- grava reunioes, transcreve localmente e gera um resumo com IA.
echo.
echo USO
echo     notetaker.bat ^<comando^> [opcoes]
echo     notetaker.bat --setup        (apenas instala/atualiza as dependencias)
echo     notetaker.bat --help         (esta ajuda)
echo.
echo Na primeira execucao, o script instala o 'uv' (se necessario), verifica o
echo 'ffmpeg' e cria o ambiente virtual automaticamente. Depois, todos os
echo argumentos sao repassados ao Notetaker.
echo.
echo COMANDOS DO NOTETAKER
echo     start "<titulo>"    Inicia a gravacao de uma reuniao.
echo                         Acompanha ao vivo (tempo + tamanho); Ctrl+C encerra
echo                         e gera o resumo.
echo     stop                Encerra a reuniao em andamento e gera o resumo.
echo     status              Mostra o estado da reuniao mais recente.
echo     list                Lista todas as reunioes gravadas.
echo     devices             Mostra os dispositivos de audio detectados.
echo     summarize ^<pasta^>   Regenera o resumo a partir da transcricao existente.
echo.
echo OPCOES DO 'start'
echo     --mode online^|presencial^|listener
echo                                  online = mic + audio do sistema (padrao)
echo                                  presencial = apenas o microfone
echo                                  listener = apenas o audio do sistema (ouvinte)
echo     --lang auto^|pt^|es^|en         Idioma falado na reuniao (padrao: config)
echo     --output-lang meeting^|pt^|es^|en
echo                                  Idioma do resumo (padrao: idioma da reuniao)
echo     --diarization level1^|level2  level1 = voce vs. participantes (padrao)
echo     --no-watch                   Nao acompanha ao vivo; use 'stop' depois.
echo.
echo AUDIO DO SISTEMA (MODO ONLINE) NO WINDOWS
echo     O DirectShow nao expoe a saida nativamente. Habilite o "Stereo Mix"/
echo     "Mixagem estereo" em Configuracoes de Som ^> Gravacao (se sua placa
echo     oferecer), ou instale o VB-CABLE (https://vb-audio.com/Cable/) ou o
echo     VoiceMeeter e roteie a saida para ele. Sem isso, use --mode presencial.
echo.
echo EXEMPLOS
echo     notetaker.bat --setup
echo     notetaker.bat start "planejamento sprint"
echo     notetaker.bat start "reuniao cliente" --mode presencial
echo     notetaker.bat start "weekly" --lang en --output-lang pt
echo     notetaker.bat status
echo     notetaker.bat list
echo.
echo CONFIGURACAO
echo     Editavel em: %%USERPROFILE%%\.config\notetaker\config.toml
echo     (modelo Whisper, idioma padrao, comando do LLM, dispositivos de audio)
exit /b 0
