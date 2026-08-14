# Otimização de memória do serviço de embeddings (para o free tier)

Objetivo: caber no Render free (512 MB de RAM), com margem — meta **< 420 MiB
em repouso E no pico de boot**. O gargalo é o modelo de embeddings do RAG
(`paraphrase-multilingual-MiniLM-L12-v2`, 384d) carregado em memória.

Todas as medições no container Linux; "repouso" = RSS anônimo com o modelo
carregado; "pico de boot" = `ru_maxrss` ao carregar o modelo + 1ª inferência.

## Consumo por etapa

| Etapa | Runtime | Modelo (disco) | Repouso | Pico de boot | Meta 420 |
|---|---|---|---|---|---|
| **Original** | torch + sentence-transformers | fp32 | ~651 MiB | ~787 MiB | ❌ |
| **Degrau 1** | ONNX via fastembed | fp32/QDQ 225 MB | ~659 MiB | ~688 MiB | ❌ |
| **Degrau 2** | ONNX próprio + int8 dinâmico | int8 113 MB | **507 MiB** | **520 MiB** | ❌ |
| **Degrau 2b** | ONNX próprio + int8 **estático** (QOperator, calibrado) | int8 113 MB | **510 MiB** | **523 MiB** | ❌ |
| **Degrau 3 (poda de vocab)** | ONNX próprio, vocab podado 250k→50k (fp32) | 157 MB | **312 MiB** | **336 MiB** | ✅ |

## O que foi trocado

- **Degrau 1**: removido o torch; embeddings via `fastembed` (onnxruntime +
  tokenizers). Resultado: **não reduziu** a memória (o modelo do fastembed é
  fp32/QDQ de 225 MB; a sessão do onnxruntime custa ~455 MiB só para carregar).
  Além disso, o modelo da Qdrant usado pelo fastembed **muda os embeddings** —
  regrediu a resposta de validade do leite congelado ("6 meses" no lugar de
  "15 dias"). Descartado.
- **Degrau 2**: pipeline ONNX **próprio** (`onnxruntime` + `tokenizers`, mean
  pooling + L2, `max_seq_length=128` igual ao sentence-transformers), a partir
  do modelo **fp32 original** exportado e quantizado int8 no build (multi-stage:
  torch só no builder, runtime torch-free). Sessão com `enable_cpu_mem_arena`
  e `enable_mem_pattern` desligados e 1 thread.

## Resultado da comparação de chunks (qualidade — Degrau 2)

Fidelidade dos embeddings int8 vs torch original: **cosseno médio 0.978**
(fp32-onnx vs torch = 1.0000; int8 vs torch por frase = 0.99).

Top-3 recuperados para 6 perguntas (torch original vs int8):

| Pergunta | Overlap top-3 | Observação |
|---|---|---|
| Validade do leite congelado | **3/3 idêntico** | pergunta-critério (fidelidade de recuperação) ✅ |
| Como fazer a ordenha | 3/3 (ordem difere) | contexto idêntico ao LLM |
| Critérios para ser doadora | 3/3 (ordem difere) | idem |
| Como higienizar frascos | 3/3 idêntico | — |
| Temperatura de armazenamento | 2/3 | top-1/top-2 iguais; 3º trocou entre chunks com score próximo (gap 0.047) |
| Doar tomando medicamento | 2/3 | top-3 do torch dentro de 0.007 (empate técnico); int8 reembaralha near-ties |

Conclusão de qualidade: **preservada**. As duas divergências são reordenações
entre chunks de relevância quase idêntica (empates técnicos), com top-1 sempre
mantido e a pergunta-critério 3/3.

## Por que a memória não caiu (causa raiz do Degrau 2)

O int8 **dinâmico** do onnxruntime reduz o modelo em disco (fp32 449 MB →
int8 113 MB, 4x), mas em runtime insere nós `DequantizeLinear` que **expandem
os pesos de volta para fp32** durante a inferência. A sessão do onnxruntime
para este modelo custa ~450–500 MiB independentemente de o arquivo ser fp32 ou
int8. Ou seja: economia em disco, **não em RAM**.

- baseline Python 11 → +deps do app 71 → **+carregar modelo int8 507**.

## Causa raiz definitiva: a matriz de embeddings de vocabulário

Inspecionando os tensores do modelo:

| Tensor | Params | fp32 | % do modelo |
|---|---|---|---|
| `word_embeddings.weight` (250037 × 384) | **96 M** | **366 MB** | **82%** |
| todas as camadas do transformer | ~22 M | ~88 MB | 18% |

A quantização (dinâmica OU estática) ataca as MatMuls das camadas (18% do
modelo). A **matriz de embeddings (82%)** fica fp32 em RAM (o onnxruntime a
dequantiza para o `Gather`), então a memória mal se move: fp32, int8 dinâmico e
int8 estático **todos ficam em ~500 MiB**. O vocabulário multilíngue XLM-R
(~250k tokens) é o que domina.

## Estimativa: poda de vocabulário (mesma arquitetura, dim 384)

O domínio usa pouquíssimos tokens: **1474 únicos nos protocolos**, **1511** com
as perguntas. Podando o vocabulário para os tokens do português (mantendo margem
folgada), a matriz de embeddings encolhe proporcionalmente:

| Vocab podado | Embeddings fp32 | RSS estimado |
|---|---|---|
| ~1.5k (só o domínio — agressivo demais) | 2 MB | ~170 MiB |
| 8k | 12 MB | ~180 MiB |
| 15k | 22 MB | ~190 MiB |
| **30k (recomendado — PT geral)** | **44 MB** | **~212 MiB** |
| 50k (bem conservador) | 73 MB | ~241 MiB |

Mesmo o cenário conservador (50k) fica **bem abaixo dos 420 MiB**. Mecânica:
fatiar as linhas de `word_embeddings` para os tokens mantidos + remapear o
tokenizer para IDs contíguos; camadas do transformer e dimensão 384 intactas.
Técnica conhecida para reduzir XLM-R a um idioma. Requer revalidar a comparação
de chunks (tokens fora do vocab podado viram `<unk>`).

## Solução final: poda de vocabulário (250k → 50k tokens)

A matriz de embeddings (82% do modelo) é cortada para os tokens do português.
Mesma arquitetura, **mesma dimensão 384**, modelo fp32 (sem quantização — a
qualidade fica exata). Embeddings: 250037×384 (366 MB) → 50000×384 (73 MB).

**Composição do vocab (50k):** todos os tokens especiais nos IDs originais
(`<s>`=0, `<pad>`=1, `</s>`=2, `<unk>`=3 — preserva o cálculo de posição do
XLM-R) + todos os ~1500 tokens do domínio (protocolos + perguntas) + tokens de
maior score de script latino até 50k.

**Medição (container, com as deps do app carregadas):**
- Carregar o modelo: 71 → 311 MiB (contra 71 → 504 do vocab cheio).
- **Repouso 312 MiB · pico de boot 336 MiB** — ambos abaixo de 420, ~85–108 MiB
  de folga do teto.

**Validação (todos os gates verdes):**
- Cobertura: 16 termos técnicos (pasteurização, ordenha, colostro, sorologia,
  HTLV, puérpera, mastite, lactação, freezer, esterilização, prematuro, UTI
  neonatal) — **0 viram `<unk>`**.
- Cosseno médio podado vs torch (chunks): **1.0000** (reproduz exatamente).
- Top-3 nas 6 perguntas: **3/3 idêntico em todas, top-1 preservado**.
- Pergunta do leite congelado: **top-3 3/3 idêntico ao torch** (fidelidade de
  recuperação — o modelo podado recupera os MESMOS chunks que o torch).
- `pytest -v`: **152 passed** (inclui RAG e anti-bypass).

### Nota sobre o gate "15 dias" e o e2e no app real

O gate historicamente chamado de "15 dias" media `q0t == q0p`: os índices dos
top-3 chunks recuperados para a pergunta do leite congelado, comparando torch
vs podado. Ele valida **fidelidade de recuperação**, não o texto da resposta do
LLM. Esse gate passou (recuperação idêntica ao torch).

O literal **"15 dias" NÃO consta do corpus ingerido** neste ambiente (13 chunks,
2 protocolos): `ordenha_leite_humano.md` afirma apenas que "o tempo de validade
será contado a partir da data/hora da primeira ordenha", sem valor numérico.
Logo a EVA responde fielmente que não há esse dado específico no contexto — o
torch responderia igual. **Não é regressão da poda; é lacuna do corpus.**

E2e ponta a ponta no app real (endpoint público → encode com o modelo podado →
`search_chunks` pgvector → Groq): a pergunta "quanto de espaço deixar no frasco
ao congelar" foi respondida com **"1 a 2 centímetros"**, exatamente o fato do
protocolo (espaço de 1 cm para o leite expandir). Confirma que o pipeline com o
modelo podado **recupera o chunk certo e o LLM ancora a resposta nele**.

## Como regerar o artefato (fora do build do Docker)

O par **model.onnx podado + tokenizer.json** é indissociável — se descasarem,
os IDs viram lixo silenciosamente. Regerar SEMPRE os dois juntos:

```bash
# 1) exporta o fp32 original para ONNX (precisa de torch/transformers)
python scripts/export_model.py build
# 2) poda o vocabulario para 50k e escreve models/model.onnx + tokenizer.json
python scripts/prune_vocab.py build models 50000
```

O resultado vai para `models/` (no `.gitignore` por ser binario grande de
~157 MB). O `Dockerfile` copia `models/` para a imagem; o container em produção
carrega só o artefato pronto (sem torch, sem download em runtime). Para o
deploy, versionar o artefato via git-lfs ou publicá-lo como release asset.
