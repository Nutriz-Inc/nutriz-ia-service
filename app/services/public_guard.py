# Guardas de entrada do modo publico (chat anonimo, sem login).
#
# Duas protecoes sobre o texto do visitante ANTES de chamar o LLM:
# - deteccao de PII (CPF, e-mail, telefone): dado sensivel do visitante nunca
#   e repassado ao LLM nem persistido; a EVA orienta a nao compartilhar.
# - deteccao de tentativa de jailbreak / fuga de escopo: acumula strikes na
#   sessao; o chamador encerra apos o limite configurado.

import re


# CPF: 000.000.000-00 ou 00000000000 (11 digitos). Evita casar numeros longos
# aleatorios exigindo a forma pontuada OU exatamente 11 digitos isolados.
_CPF_RE = re.compile(r"\b(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Telefone BR: com DDD, aceita +55, parenteses, espacos e hifen; 10-11 digitos.
_PHONE_RE = re.compile(
    r"(?:\+?55\s?)?(?:\(?\d{2}\)?[\s-]?)?9?\d{4}[\s-]?\d{4}\b"
)

_JAILBREAK_PATTERNS = [
    r"ignore\s+(as\s+)?(instru|regras|tudo)",
    r"esque[çc]a\s+(as\s+)?(instru|regras)",
    r"desconsidere\s+(as\s+)?(instru|regras)",
    r"aja\s+como",
    r"finja\s+(que\s+)?(ser|voc[êe])",
    r"pretenda\s+ser",
    r"system\s+prompt",
    r"prompt\s+do\s+sistema",
    r"suas\s+instru[çc][õo]es",
    r"developer\s+mode",
    r"modo\s+desenvolvedor",
    r"jailbreak",
    r"\bDAN\b",
    r"sem\s+(nenhuma\s+)?restri[çc][ãa]o",
]

_JAILBREAK_RE = re.compile("|".join(_JAILBREAK_PATTERNS), re.IGNORECASE)


def contains_pii(text: str) -> bool:
    if _CPF_RE.search(text):
        return True
    if _EMAIL_RE.search(text):
        return True
    # Telefone tem regex mais permissivo; exige ao menos 10 digitos no total
    # para nao disparar com numeros curtos (ex: "tenho 2 bebes").
    for match in _PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group())
        if len(digits) >= 10:
            return True
    return False


def is_jailbreak_attempt(text: str) -> bool:
    return _JAILBREAK_RE.search(text) is not None


PII_WARNING = (
    "Notei que voce pode ter enviado um dado pessoal (como CPF, e-mail ou "
    "telefone). Por seguranca, nao compartilhe dados pessoais neste chat "
    "publico. Para um atendimento personalizado e seguro, faca seu cadastro na "
    "plataforma Nutriz. Posso seguir tirando suas duvidas sobre amamentacao e "
    "doacao de leite."
)

JAILBREAK_WARNING = (
    "Eu sou a EVA e meu foco e ajudar com amamentacao e doacao de leite "
    "materno. Vamos manter a conversa nesses temas?"
)

JAILBREAK_SESSION_ENDED = (
    "Encerrei esta sessao por seguranca. Se quiser retomar, e so iniciar um "
    "novo chat. Estou aqui para falar sobre amamentacao e doacao de leite."
)
