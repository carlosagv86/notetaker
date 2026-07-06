# Notetaker

Ferramenta de linha de comando que grava reunioes, transcreve localmente com
Whisper e gera um resumo estruturado (pontos discutidos, decisoes, tarefas e
observacoes) atraves de uma CLI de LLM ja contratada (kiro-cli, claude-code, etc).

Notetaker existe para reduzir o esforco manual de tomar notas e distribuir
resumos de reuniao, mantendo o audio 100% local e enviando apenas texto ao LLM.

## Language

**Meeting** (Reuniao):
Uma sessao gravada, do `start` ao `stop`. Cada Meeting corresponde a uma pasta
em disco com todos os seus arquivos.
_Avoid_: sessao, call, gravacao

**Track** (Trilha):
Um fluxo de audio gravado separadamente. No modo online existem duas: `mic`
(sua voz) e `system` (voz dos participantes, capturada do monitor da saida).
No presencial existe apenas `mic`.
_Avoid_: canal, stream, faixa

**Mode** (Modo):
Como o audio e capturado. `online` grava mic + system em Tracks separadas;
`presencial` grava apenas o mic; `listener` grava apenas o system (voce
participando como ouvinte numa reuniao online).
_Avoid_: tipo de reuniao

**Diarization** (Diarizacao):
Atribuir trechos de fala a quem falou. `level1` distingue voce (Track mic) dos
participantes (Track system) sem ML. `level2` usa ML para separar cada locutor.
_Avoid_: separacao de locutores, speaker split

**Summary** (Resumo):
A saida gerada pelo LLM a partir da transcricao, em Markdown estruturado.
Persistida como `resumo.md`.
_Avoid_: ata, relatorio, sintese

**LLM Provider**:
Qual CLI externo usar para gerar o Summary a partir da transcricao: `kiro`
(kiro-cli chat --no-interactive) ou `claude` (claude -p). Configurado em
`[llm].provider`; a transcricao vai via stdin. Notetaker nao fala com APIs de
LLM direto.
_Avoid_: modelo, IA, backend

**Meeting Language** (Idioma da reuniao):
O idioma falado na reuniao (`auto`, `pt`, `es`, `en`). Determina o idioma da
transcricao e, por padrao, o idioma do Summary.
_Avoid_: locale

## Instalacao

### Opcao A — script automatico (recomendado)

O `notetaker.sh` (Linux/macOS) e o `notetaker.bat` (Windows) cuidam de tudo:
instalam o `uv` (se necessario), verificam o `ffmpeg`, criam o ambiente virtual
e executam a aplicacao.

```bash
# Linux/macOS
./notetaker.sh --setup            # prepara o ambiente
./notetaker.sh start "minha reuniao"
./notetaker.sh --help             # ajuda completa do script
```

```bat
REM Windows (CMD ou PowerShell)
notetaker.bat --setup
notetaker.bat start "minha reuniao"
notetaker.bat --help
```

### Opcao B — instalacao manual

```bash
# 1. Dependencia de sistema para captura de audio
sudo apt install ffmpeg                       # Linux (Debian/Ubuntu)
brew install ffmpeg                           # macOS
winget install Gyan.FFmpeg                    # Windows (ou: choco install ffmpeg)

# 2. Instalar o notetaker (Python >= 3.11)
pip install -e .

# 3. (Opcional) Nivel 2 de diarizacao por ML
pip install -e ".[diarization]"

# 4. (Opcional) Aceleracao por GPU NVIDIA (CUDA)
pip install -e ".[gpu]"
```

Em ambos os casos, voce precisa de um CLI de LLM ja instalado e autenticado
(ex.: `claude`, `kiro-cli`). O Notetaker apenas o invoca; nao gerencia chaves.

## Plataformas

### Linux
Captura via PulseAudio/PipeWire. Modo online (mic + participantes) funciona
nativamente: o audio de saida e capturado do monitor do sink. Nada extra a
instalar alem do `ffmpeg`.

### macOS
Captura via AVFoundation. O modo **presencial** (so microfone) funciona direto.

O modo **online** (capturar a voz dos participantes) exige um dispositivo de
audio virtual, pois o macOS nao expoe o audio de saida para captura:

1. Instale o [BlackHole](https://existential.audio/blackhole/) (gratuito):
   `brew install blackhole-2ch`
2. Em *Audio MIDI Setup*, crie um **Dispositivo Agregado** com o BlackHole + sua
   saida normal (para ouvir e capturar ao mesmo tempo).
3. Durante a reuniao, use esse dispositivo como saida de audio.

O Notetaker detecta o BlackHole automaticamente no `start`. Rode
`./notetaker.sh devices` para ver o que foi detectado. Sem o BlackHole, o modo
online exibe instrucoes e sugere `--mode presencial`.

> Nota: no macOS a transcricao roda em CPU (o CTranslate2 nao suporta
> Metal/MPS). Em Apple Silicon a CPU e rapida o suficiente para modelos menores.

### Windows
Captura via DirectShow (dshow). O modo **presencial** (so microfone) funciona
direto — o Notetaker usa o dispositivo de entrada padrao detectado.

O modo **online** (capturar a voz dos participantes) exige um dispositivo de
audio de loopback, pois o DirectShow nao expoe o audio de saida para captura:

1. **Stereo Mix / Mixagem estereo** (mais simples, se sua placa oferecer):
   habilite-o em *Configuracoes de Som > Gravacao* (clique com o botao direito
   na lista e marque "Mostrar dispositivos desativados"), depois ative-o.
2. **Dispositivo virtual** (universal): instale o
   [VB-CABLE](https://vb-audio.com/Cable/) ou o VoiceMeeter e roteie a saida de
   audio para ele durante a reuniao.

O Notetaker detecta o Stereo Mix / dispositivo virtual automaticamente no
`start`. Rode `notetaker.bat devices` para ver o que foi detectado. Sem um
loopback, o modo online exibe instrucoes e sugere `--mode presencial`.

> Nota: no Windows a transcricao usa GPU NVIDIA (CUDA) quando disponivel; senao,
> CPU. Verifique tambem as permissoes de microfone do app de terminal em
> *Configuracoes > Privacidade e seguranca > Microfone*.

### Aceleracao por GPU (NVIDIA)
Quando uma GPU NVIDIA e detectada, a transcricao usa CUDA automaticamente
(muito mais rapida). Instale as libs com `pip install -e ".[gpu]"` ou
`./notetaker.sh` (que ja sincroniza o ambiente). Sem GPU, usa CPU normalmente.
Verifique o dispositivo em uso pelas metricas exibidas ao processar.

## Configuracao

Na primeira execucao, o Notetaker detecta que ainda nao ha config e oferece
rodar um assistente interativo, que pergunta cada opcao com o valor padrao
(pressione Enter para aceitar). Voce tambem pode rodar o assistente a qualquer
momento:

```bash
./notetaker.sh setup
```

O assistente grava `~/.config/notetaker/config.toml`. Se preferir editar o
arquivo a mao, ele tem este formato:

```toml
storage_root = "~/notetaker"   # onde as Meetings sao salvas

[audio]
mic_source = ""        # vazio = auto (default source do PulseAudio)
monitor_source = ""    # vazio = auto (monitor do default sink)

[whisper]
model = "medium"       # tiny | base | small | medium | large-v3
language = "auto"      # auto | pt | es | en

[summary]
language = "meeting"   # "meeting" = idioma da reuniao | pt | es | en

[llm]
provider = "kiro"      # kiro | claude
```

Dicas:
- **Dispositivos**: deixe vazio para deteccao automatica. Ao trocar de
  headset/speaker, o Notetaker usa o dispositivo ativo no momento do `start`.
- **Modelo Whisper**: `medium` da boa qualidade em portugues; `base`/`small`
  sao mais rapidos em CPU; `large-v3` e o mais preciso (e o mais lento).
- **LLM**: qualquer CLI que leia stdin e imprima a resposta serve. O Notetaker
  pede o resumo delimitado por sentinelas, entao tolera banners/ANSI na saida.

## Uso

Os exemplos abaixo usam o `notetaker.sh` (recomendado): ele mantem o ambiente
atualizado e repassa os argumentos ao Notetaker. Se voce instalou manualmente
(Opcao B), basta trocar `./notetaker.sh` por `notetaker` em qualquer comando.

Veja a ajuda completa a qualquer momento:

```bash
./notetaker.sh --help
```

### Gravar uma reuniao (modo padrao, com acompanhamento ao vivo)

```bash
./notetaker.sh start "planejamento sprint"
```

Durante a gravacao, uma linha ao vivo mostra o tempo decorrido e o tamanho do
audio capturado:

```
⠹ gravando  12:34  audio: 3.2 MB  (Ctrl+C para encerrar)
```

Pressione **Ctrl+C** para encerrar. O Notetaker entao transcreve e gera o
resumo, exibindo o progresso de cada fase:

```
⠧ transcrevendo sua fala (mic)...
⠴ transcrevendo os participantes (system)...
⠋ gerando o resumo com o LLM...
resumo pronto: ~/notetaker/2026-07-02_1234_planejamento-sprint/resumo.md
```

### Reuniao presencial (apenas microfone)

```bash
./notetaker.sh start "reuniao cliente" --mode presencial
```

### Escolher idioma e diarizacao

```bash
# Reuniao em ingles, resumo em portugues, identificar cada locutor (ML)
./notetaker.sh start "weekly" --lang en --output-lang pt --diarization level2
```

### Modo desanexado (sem acompanhamento ao vivo)

Util para automacao ou quando voce nao quer o terminal preso na sessao:

```bash
./notetaker.sh start "call" --no-watch   # retorna imediatamente
# ... reuniao acontece ...
./notetaker.sh stop                      # encerra e processa em background
./notetaker.sh status                    # acompanha o progresso
```

### Demais comandos

```bash
./notetaker.sh status                 # estado da reuniao mais recente
./notetaker.sh list                   # lista todas as reunioes
./notetaker.sh devices                # mostra os dispositivos de audio detectados
./notetaker.sh summarize <pasta>      # regenera o resumo sem re-transcrever
./notetaker.sh summarize <pasta> --output-lang en   # ... em outro idioma
```

## Arquivos gerados por reuniao

Cada Meeting e uma pasta em `storage_root`, nomeada `AAAA-MM-DD_HHMM_titulo`:

```
2026-07-02_1234_planejamento-sprint/
├── audio-mic.opus        # sua voz (Track mic)
├── audio-system.opus     # voz dos participantes (Track system; so online)
├── transcript-mic.txt    # transcricao da sua fala
├── transcript-system.txt # transcricao dos participantes
├── transcript-full.txt   # transcricao combinada, rotulada por locutor
├── resumo.md             # o Summary final (Markdown)
└── meta.json             # metadados da sessao
```

## Referencia dos comandos

Via script (recomendado) ou, se instalado manualmente, trocando `./notetaker.sh`
por `notetaker`:

```
./notetaker.sh --setup            # instala/atualiza dependencias e sai
./notetaker.sh --help             # ajuda do script

./notetaker.sh start "titulo" [--mode online|presencial] [--lang auto|pt|es|en] \
                              [--diarization level1|level2] [--output-lang meeting|pt|es|en] \
                              [--no-watch]
./notetaker.sh stop [--wait]
./notetaker.sh status
./notetaker.sh list
./notetaker.sh devices
./notetaker.sh summarize <pasta> [--output-lang meeting|pt|es|en]
```

## Privacidade

O audio nunca sai da sua maquina: a transcricao roda localmente com Whisper.
Apenas o texto da transcricao e enviado ao LLM Provider configurado. Consulte
`docs/adr/0002-audio-local-texto-remoto.md` para detalhes.
