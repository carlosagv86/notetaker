# Diarizacao nivel 1 por padrao; nivel 2 (ML) opcional

A gravacao sempre separa as Tracks (mic e system) no modo online. O nivel 1 de
diarizacao usa essa separacao para distinguir voce (mic) dos participantes
(system) sem ML, a custo quase zero. O nivel 2, que identifica cada locutor via
ML (whisperx/pyannote), fica opcional atras do extra `[diarization]` e nao e o
padrao.

Decidimos assim porque a maquina alvo nao tem GPU: diarizacao por ML e pesada,
instavel e de valor incerto (gera "Locutor 1/2" que ainda exige mapeamento
manual). O nivel 1 cobre o caso principal ("o que eu me comprometi" vs "o que
eles disseram"). Consequencia: no modo presencial (so mic) nao ha separacao no
nivel 1. O nivel 2 pode ser adotado depois sem mudar a gravacao, ja que as
Tracks sao sempre preservadas.
