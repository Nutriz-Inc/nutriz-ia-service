# Jornada da doação na plataforma Nutriz

## As quatro etapas

A doação de leite humano na Nutriz tem exatamente quatro etapas, sempre nesta
ordem. Não existem outras etapas e a ordem não muda.

1. **Exame de sangue** — a triagem sorológica da candidata a doadora. É a
   primeira etapa porque define a aptidão para doar.
2. **Entregar kit de ordenha** — a equipe leva à doadora os frascos
   esterilizados e as orientações de coleta.
3. **Coletar leite** — a coleta do leite humano ordenhado, na casa da doadora
   (coleta domiciliar) ou no ponto de coleta.
4. **Análise de leite** — o banco de leite avalia o material recebido antes de
   ele ser pasteurizado e distribuído.

Uma nutriz pode ter no máximo **uma doação ativa por vez**.

## Situação de cada etapa

Cada etapa tem uma situação própria:

- **Pendente** (`pending`) — ainda não foi feita.
- **Em análise** (`review`) — foi feita e aguarda avaliação da equipe.
- **Concluída** (`done`) — finalizada com sucesso.
- **Atenção** (`warn`) — algo precisa ser revisto pela equipe.
- **Reprovada** (`failed`) — não foi aprovada.

A etapa atual de uma doação é sempre a primeira da ordem acima que ainda não
está concluída.

## O que a EVA não sabe sobre a etapa

A EVA não tem acesso a exames, sorologias, resultados laboratoriais,
diagnósticos nem ao texto que a equipe escreve na etapa. Ela conhece apenas a
situação, a data prevista e o local. Perguntas sobre resultado de exame devem
ser encaminhadas à equipe Lactare.

No caso específico da etapa **Exame de sangue**, a situação negativa é omitida
de propósito: o desfecho da sorologia é dado clínico e não pode ser inferido
pelo chat.
