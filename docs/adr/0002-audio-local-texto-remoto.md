# Audio 100% local, apenas texto vai ao LLM Provider

O audio das reunioes e gravado e transcrito inteiramente na maquina do usuario
(faster-whisper). Somente a transcricao em texto e enviada ao LLM Provider.
Decidimos assim porque as reunioes podem conter conteudo sensivel e o audio
bruto e o dado mais critico; o texto vai a um CLI contratado com politica de
nao reaproveitamento.

Consequencia: transcricao roda em CPU local, sem custo por minuto e offline,
ao custo de tempo de processamento. Esta e uma restricao de privacidade que nao
aparece no codigo, por isso registrada aqui.
