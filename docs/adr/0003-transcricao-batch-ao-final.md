# Transcricao em batch ao final, nao ao vivo

A transcricao roda em batch depois do `stop`, nao em tempo real durante a
Meeting. Durante a gravacao so capturamos audio (barato); ao encerrar,
transcrevemos os arquivos e geramos o Summary. Decidimos assim porque a maquina
alvo e CPU-only, e o Whisper (modelo medium/large) em CPU e lento demais para
tempo real e sobrecarregaria o notebook durante a call.

Consequencia: o usuario espera o processamento apos o stop (rodando em
background). Ganhamos qualidade maxima de transcricao e nao competimos por CPU
durante a reuniao. Alternativa rejeitada: transcricao ao vivo com modelo
pequeno, descartada por qualidade ruim em portugues e uso constante de CPU.
