# LLM Provider via CLI externo, nao API direta

Notetaker gera o Summary invocando um CLI de LLM ja contratado (kiro-cli,
claude-code, etc.) via comando-template configuravel, enviando a transcricao por
stdin e recebendo o resumo em Markdown por stdout. Decidimos assim para reusar
assinaturas existentes com politica de nao reaproveitamento de dados, evitar
gerenciar API keys e desacoplar do provider.

Trade-off: dependemos de o CLI aceitar entrada por stdin e modo one-shot, e
precisamos extrair o Markdown do stdout (que pode vir com banners/ANSI/texto
extra) em vez de uma resposta de API estruturada. Para isso o LLM delimita o
resumo entre sentinelas. Alternativa rejeitada: chamar APIs de LLM direto, que
traria gestao de credenciais e acoplamento ao provider. Tambem consideramos
pedir JSON ao LLM, mas Markdown e mais robusto de extrair do ruido do CLI e ja
e o formato final desejado.
