# Dispositivos de audio detectados no start, nao fixados no config

O mic e o monitor de saida sao resolvidos em tempo de execucao no `start`, a
partir do default source/sink atual do PulseAudio (`pactl get-default-source` /
`get-default-sink`, derivando o `.monitor` do sink). O config oferece apenas
overrides opcionais; vazio significa deteccao automatica.

A resolucao e por backend de plataforma, mantendo a mesma semantica de auto-
deteccao:
- **Linux (PulseAudio/PipeWire)**: default source/sink; monitor = `<sink>.monitor`.
- **macOS (AVFoundation)**: indices de dispositivo; monitor = indice de um
  dispositivo de loopback (BlackHole), obrigatorio no modo online.
- **Windows (DirectShow)**: nomes de dispositivo; monitor = nome do "Stereo Mix"
  ou de um dispositivo virtual (VB-CABLE/VoiceMeeter), obrigatorio no modo online.

Decidimos assim porque a ferramenta sera distribuida a outras pessoas e o
usuario troca de headset/speaker com frequencia. Fixar nomes de dispositivo no
config quebraria a cada troca e inviabilizaria a distribuicao. Consequencia: a
captura usa o dispositivo ativo no momento do start; para forcar um dispositivo
especifico, o usuario preenche o override no config.
