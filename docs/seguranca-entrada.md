# Segurança de entrada do chat

Estado depois de 11/09/2026. Cobre o `/ws/chat` (autenticado) e o
`/ws/chat-public` (anônimo), que passaram a compartilhar o mesmo guard.

---

## O que estava aberto

**1. O motorista não estava no gate de staff.**
`STAFF_USER_TYPES` listava apenas `adm` e `nurse`. O papel `driver` foi criado
depois e ninguém voltou ao gate. O front nunca mostrou a EVA para o motorista,
mas gate de UI não é barreira: com um token válido bastava abrir o WebSocket
para passar. E, passando, ele era tratado como **nutriz** — o serviço lia o
perfil dele (nome, bebê, endereço) e o contexto de doação, e montava um prompt
de nutriz com dados de quem não é nutriz.

**2. O guard só existia no modo público.**
`contains_pii` e `is_jailbreak_attempt` eram chamados apenas dentro do handler
de `/ws/chat-public`. A nutriz logada mandava a mensagem direto para o LLM: sem
detecção de PII, sem anti-jailbreak, e **sem limite de tamanho em nenhum dos
dois modos**.

---

## O guard hoje (`app/services/input_guard.py`)

O módulo deixou de se chamar `public_guard` porque não é mais do modo público.

| Camada | O que faz | Onde roda |
|---|---|---|
| Limite de tamanho | recusa acima de **1000 caracteres**, com texto amigável | os dois modos |
| Sanitização | NFKC, remove caracteres de controle e de largura zero | os dois modos |
| PII | CPF (pontuado ou 11 dígitos), e-mail, telefone BR | os dois modos |
| Jailbreak | 31 padrões, PT e EN, com strikes | os dois modos |

A ordem é: tamanho → sanitização → PII → jailbreak. Tudo **antes** de qualquer
chamada ao LLM, então o que é barrado não chega à Groq nem ao `llm_audit`, que
é append-only e imutável.

### Padrões de jailbreak

**Português (14):** ignore as instruções, esqueça as regras, desconsidere,
aja como, finja ser, pretenda ser, prompt do sistema, suas instruções, modo
desenvolvedor, sem restrição, repita suas instruções, mostre seu prompt,
a partir de agora você é, novas instruções.

**Inglês (17):** ignore all previous, disregard the above, forget your
instructions, pretend you are, act as a, you are now, from now on you,
output/print/reveal/repeat/show/translate/summarize your prompt, system prompt,
developer mode, jailbreak, DAN, do anything now, without restrictions,
new instructions, override your rules, tag `<system>` falsa.

### Ofuscação

O texto é analisado em várias formas, e o mesmo conjunto de padrões vale para
todas — nenhuma regra é duplicada:

| Técnica | Tratamento |
|---|---|
| Homoglifos | cirílicos e gregos parecidos com latinos são dobrados (`systеm` → `system`) |
| Largura zero | `U+200B`–`U+200F`, `U+2060`, `U+FEFF` removidos antes de analisar |
| Letras espaçadas | `j a i l b r e a k` é colapsado quando há 4+ letras isoladas seguidas |
| Base64 | todo token de 16+ caracteres base64 é decodificado e analisado |
| ROT13 | o texto inteiro é decodificado e analisado |

### Por que 1000 caracteres

Mensagem longa é o esconderijo clássico de injection: o payload vai no meio de
um texto que parece legítimo, longe do começo e do fim, onde a leitura humana
não chega. O limite não é sobre custo de token — é sobre superfície.

### Sem dependência nova

`base64`, `codecs`, `unicodedata` e `re` são biblioteca padrão. Nada entrou no
`requirements`.

---

## Diferenças entre os modos

O único comportamento que muda por modo é o texto de PII. Quem já tem cadastro
não precisa ouvir "faça seu cadastro":

- **Anônimo:** orienta a não compartilhar dado pessoal em chat público e
  convida ao cadastro.
- **Logado:** diz que a EVA não precisa daquele dado, que prefere não registrá-lo
  na conversa, e aponta o perfil para atualização cadastral.

O limite de strikes é o mesmo nos dois (`ANON_MAX_JAILBREAK_STRIKES`, padrão 3,
close **4008**). O nome da variável ficou como estava de propósito: renomear
exigiria mexer no `render.yaml` e no painel do Render, coordenação que não se
paga por cosmética.

---

## O que ficou pendente

**Registrar o modo no `llm_audit`.** A tabela tem `is_anonymous`, mas não tem
coluna de papel. Adicionar exige migration no Neon, e a regra do projeto é que
migration em produção é o Léo quem roda. Como adm, nurse e driver ainda não
conversam com a EVA, a coluna só passa a ter valor na fase das personas — fica
para lá, junto da migration.

---

## Testes

| Arquivo | Cobre |
|---|---|
| `tests/unit/test_input_guard.py` | 35 casos: PII (inclusive e-mail em base64), jailbreak PT e EN, as quatro ofuscações, sanitização, limite |
| `tests/integration/test_ws_chat.py` | gate do driver (4403), PII, jailbreak em inglês, mensagem longa, três strikes → 4008, e a regressão de que pergunta legítima continua passando |
| `tests/integration/test_ws_chat_public.py` | suíte do modo público, inalterada |

A regressão importa tanto quanto a detecção: guard que barra pergunta legítima
é pior que guard nenhum, porque quebra o atendimento sem que ninguém perceba.

`pytest` completo: **231 verdes** (Postgres do compose na 5433).

---

## Validação no serviço rodando

Além do pytest, a bateria foi executada contra o serviço de verdade
(`uvicorn` local, Groq real com `openai/gpt-oss-120b`, banco de dev com os 13
chunks de protocolo ingeridos), dirigindo os dois WebSockets:

| Caso | Modo público | Modo logado |
|---|---|---|
| `ignore all previous instructions` | bloqueado | bloqueado |
| base64 de `ignore all previous instructions` | bloqueado | — |
| `j a i l b r e a k` | bloqueado | — |
| `systеm prompt` com `е` cirílico | bloqueado | — |
| 1200 caracteres | recusado | recusado |
| CPF `123.456.789-00` | aviso de PII público | aviso de PII logado |
| pergunta legítima | respondida pelo LLM | respondida com contexto de doação |
| token de motorista | — | **4403**, `staff_not_allowed` |

### A prova que interessa

Depois da bateria, no banco:

```sql
SELECT count(*) FILTER (WHERE prompt_full::text ILIKE '%123.456.789-00%'),
       count(*) FILTER (WHERE prompt_full::text ILIKE '%ignore all previous%')
FROM llm_audit;
--  0 | 0
SELECT count(*) FROM messages
WHERE content ILIKE '%123.456.789-00%' OR content ILIKE '%ignore all previous%';
--  0
```

Nenhum dado barrado chegou ao `llm_audit` nem à tabela `messages`. Só duas
linhas de auditoria nos dez minutos da bateria — exatamente as duas perguntas
legítimas que passaram. Como o `llm_audit` é append-only e imutável, o que
entra ali fica: é por isso que o bloqueio precisa acontecer **antes** da
chamada, e não por filtragem na saída.
