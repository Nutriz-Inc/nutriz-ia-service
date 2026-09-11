# Rotas e coleta domiciliar

## O que é uma rota

Uma rota é o roteiro de coleta de um motorista num dia. Ela tem um nome, uma
região (cidade e bairro), uma data programada e uma lista de paradas em ordem.
Cada parada corresponde a uma etapa de doação com endereço.

A administração cria a rota e atribui o motorista. O motorista executa.

## Situação da rota

- **Pendente** (`pending`) — criada, ainda não iniciada.
- **Em andamento** (`in_progress`) — o motorista iniciou.
- **Concluída** (`done`) — finalizada, com quilometragem registrada.
- **Cancelada** (`canceled`) — não será executada.
- **Com erro** (`error`) — houve uma ocorrência que encerrou a operação.

## A regra das 6 horas

Entre a saída para a primeira coleta e a chegada ao banco de leite não podem
passar **mais de 6 horas**. É o limite que preserva a qualidade do leite humano
ordenhado durante o transporte refrigerado.

Na plataforma o limite aparece em cinco lugares: na listagem de rotas, no
detalhe da rota (com cronômetro), ao adicionar uma parada, ao finalizar a rota
e na duração média do painel. A escala de cor é a mesma em todos: azul até 5
horas, laranja entre 5 e 6, vermelho depois de 6.

Passar das 6 horas não impede finalizar a rota — o sistema avisa e registra.

## Como o motorista executa a rota

1. Inicia a rota no app. É o que liga o cronômetro das 6 horas.
2. Em cada parada, registra a chegada e faz a coleta.
3. Ao final, finaliza a rota informando a quilometragem percorrida.

Se uma parada não puder ser feita (doadora ausente, portão fechado, endereço
não encontrado), o motorista registra a ocorrência na própria parada.

## Frasco com problema

Frasco danificado, vazando, sem identificação ou fora da temperatura não deve
ser improvisado: o motorista registra a ocorrência no app e comunica a central
da Lactare.
