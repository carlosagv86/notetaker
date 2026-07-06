# Notetaker

Ferramenta CLI que grava reunioes, transcreve localmente com Whisper e gera um
Summary estruturado atraves de um LLM Provider (CLI externo). O audio nunca sai
da maquina; apenas a transcricao em texto e enviada ao LLM Provider.

## Language

**Meeting** (Reuniao):
Uma sessao gravada, do `start` ao `stop`. Corresponde a uma pasta em disco.
_Avoid_: sessao, call, gravacao

**Track** (Trilha):
Um fluxo de audio gravado separadamente. Online: `mic` (sua voz) e `system`
(voz dos participantes, do monitor da saida). Presencial: apenas `mic`.
_Avoid_: canal, stream, faixa

**Mode** (Modo):
Como o audio e capturado. `online` = mic + system; `presencial` = so mic;
`listener` = so system (voce como ouvinte numa reuniao online).
_Avoid_: tipo de reuniao

**Diarization** (Diarizacao):
Atribuir fala a quem falou. `level1` distingue voce (Track mic) dos
participantes (Track system) sem ML. `level2` usa ML para separar cada locutor.
_Avoid_: separacao de locutores, speaker split

**Summary** (Resumo):
Saida gerada pelo LLM Provider a partir da transcricao, em Markdown estruturado.
Persistida como `resumo.md`.
_Avoid_: ata, relatorio, sintese

**LLM Provider**:
Comando de CLI externo (definido no config) que recebe a transcricao via stdin
e devolve o Summary em JSON. Notetaker nao fala com APIs de LLM direto.
_Avoid_: modelo, IA, backend

**Meeting Language** (Idioma da reuniao):
Idioma falado na reuniao (`auto`, `pt`, `es`, `en`). Determina o idioma da
transcricao e, por padrao, o idioma do Summary.
_Avoid_: locale
