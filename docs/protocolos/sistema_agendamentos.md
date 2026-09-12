# Agendamentos da equipe de enfermagem

## O que é um agendamento

Um agendamento (`job`, no sistema) é uma tarefa atribuída a um profissional de
enfermagem, vinculada a uma etapa específica de uma doação. É por ele que a
equipe organiza as visitas: entregar o kit de ordenha, acompanhar uma coleta,
conferir uma etapa.

Cada agendamento tem uma data marcada e pertence a **um** profissional.

## Situação do agendamento

- **Pendente** (`pending`) — ainda a fazer.
- **Concluído** (`done`) — executado.
- **Não concluído** (`failed`) — não foi possível executar.

## Quem vê o quê

A administração enxerga todos os agendamentos. Cada profissional de enfermagem
enxerga **apenas os seus**. A EVA respeita esse limite: no modo enfermagem ela
só conhece os agendamentos de quem está falando com ela, e diz isso se
perguntarem pelos de outra pessoa.

## O que a EVA não sabe do agendamento

A EVA recebe apenas a etapa, a situação e a data. Ela **não** tem acesso ao
texto que a equipe escreve na descrição nem ao relato de conclusão — esses
campos costumam conter informação clínica e por isso nunca chegam ao chat.
Dúvida sobre conduta em um caso específico é com a coordenação da Lactare.
