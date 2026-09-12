import base64
import binascii
import codecs
import re
import unicodedata

MAX_MESSAGE_CHARS = 1000

_CPF_RE = re.compile(r"\b(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"(?:\+?55\s?)?(?:\(?\d{2}\)?[\s-]?)?9?\d{4}[\s-]?\d{4}\b")

_JAILBREAK_PATTERNS_PT = [
    r"ignore\s+(as\s+)?(instru|regras|tudo)",
    r"esque[çc]a\s+(as\s+)?(instru|regras)",
    r"desconsidere\s+(as\s+)?(instru|regras)",
    r"aja\s+como",
    r"finja\s+(que\s+)?(ser|voc[êe])",
    r"pretenda\s+ser",
    r"prompt\s+do\s+sistema",
    r"suas\s+instru[çc][õo]es",
    r"modo\s+desenvolvedor",
    r"sem\s+(nenhuma\s+)?restri[çc][ãa]o",
    r"repita\s+(as\s+)?(suas\s+)?instru[çc][õo]es",
    r"mostre\s+(o\s+)?(seu\s+)?prompt",
    r"a\s+partir\s+de\s+agora\s+voc[êe]\s+[ée]",
    r"novas\s+instru[çc][õo]es",
]

_JAILBREAK_PATTERNS_EN = [
    r"ignore\s+(all\s+)?(previous|prior|above|preceding|earlier)",
    r"disregard\s+(all\s+)?(previous|prior|above|the)",
    r"forget\s+(all\s+)?(previous|your)\s+(instructions|rules|prompt)",
    r"pretend\s+(you\s+are|to\s+be|that\s+you)",
    r"act\s+as\s+(a|an|if|though)",
    r"you\s+are\s+now",
    r"from\s+now\s+on\s+you",
    r"(output|print|reveal|repeat|show|translate|summarize)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions|rules)",
    r"system\s+prompt",
    r"developer\s+mode",
    r"jailbreak",
    r"\bDAN\b",
    r"do\s+anything\s+now",
    r"without\s+(any\s+)?(restrictions|limits|rules)",
    r"new\s+instructions",
    r"override\s+(your|the)\s+(instructions|rules)",
    r"</?(system|instruction)>",
]

_JAILBREAK_RE = re.compile(
    "|".join(_JAILBREAK_PATTERNS_PT + _JAILBREAK_PATTERNS_EN), re.IGNORECASE
)

_HOMOGLYPHS = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "х": "x",
        "у": "y",
        "і": "i",
        "ο": "o",
        "α": "a",
        "ε": "e",
        "ρ": "p",
        "υ": "u",
        "ı": "i",
    }
)

_ZERO_WIDTH_RE = re.compile(r"[​-‏‪-‮⁠﻿]")
_SPACED_LETTERS_RE = re.compile(r"(?:\b\w\b[\s.\-_]{1,3}){3,}\w\b")
_BASE64_CANDIDATE_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")


def sanitize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = _ZERO_WIDTH_RE.sub("", normalized)
    cleaned = "".join(
        char
        for char in normalized
        if char in ("\n", "\t") or unicodedata.category(char) != "Cc"
    )
    return cleaned.strip()


def exceeds_length(text: str) -> bool:
    return len(text.strip()) > MAX_MESSAGE_CHARS


def _collapse_spaced_letters(text: str) -> str:
    def join_run(match: re.Match[str]) -> str:
        return re.sub(r"[\s.\-_]+", "", match.group())

    return _SPACED_LETTERS_RE.sub(join_run, text)


def _decoded_variants(text: str) -> list[str]:
    variants: list[str] = []

    try:
        variants.append(codecs.decode(text, "rot13"))
    except (UnicodeDecodeError, TypeError):
        pass

    for candidate in _BASE64_CANDIDATE_RE.findall(text):
        padded = candidate + "=" * (-len(candidate) % 4)
        try:
            decoded = base64.b64decode(padded, validate=True)
        except (binascii.Error, ValueError):
            continue
        try:
            variants.append(decoded.decode("utf-8"))
        except UnicodeDecodeError:
            continue

    return variants


def _analysis_forms(text: str) -> list[str]:
    base = sanitize(text).translate(_HOMOGLYPHS)
    forms = [base, _collapse_spaced_letters(base)]
    forms.extend(_decoded_variants(base))
    return forms


def contains_pii(text: str) -> bool:
    for form in _analysis_forms(text):
        if _CPF_RE.search(form):
            return True
        if _EMAIL_RE.search(form):
            return True
        for match in _PHONE_RE.finditer(form):
            digits = re.sub(r"\D", "", match.group())
            if len(digits) >= 10:
                return True
    return False


def is_jailbreak_attempt(text: str) -> bool:
    return any(_JAILBREAK_RE.search(form) for form in _analysis_forms(text))


PII_WARNING = (
    "Notei que voce pode ter enviado um dado pessoal (como CPF, e-mail ou "
    "telefone). Por seguranca, nao compartilhe dados pessoais neste chat "
    "publico. Para um atendimento personalizado e seguro, faca seu cadastro na "
    "plataforma Nutriz. Posso seguir tirando suas duvidas sobre amamentacao e "
    "doacao de leite humano."
)

PII_WARNING_LOGGED = (
    "Percebi um dado pessoal na sua mensagem (como CPF, e-mail ou telefone). "
    "Nao preciso dessas informacoes por aqui, e prefiro nao registra-las na "
    "conversa. Seus dados de cadastro voce atualiza direto no seu perfil. "
    "Pode me contar o resto da duvida sem eles?"
)

JAILBREAK_WARNING = (
    "Eu sou a EVA e meu foco e ajudar com amamentacao e doacao de leite "
    "humano. Vamos manter a conversa nesses temas?"
)

JAILBREAK_SESSION_ENDED = (
    "Encerrei esta sessao por seguranca. Se quiser retomar, e so iniciar um "
    "novo chat. Estou aqui para falar sobre amamentacao e doacao de leite."
)

MESSAGE_TOO_LONG = (
    "Sua mensagem ficou longa demais para eu ler de uma vez. Pode resumir em "
    "ate 1000 caracteres ou me contar uma duvida de cada vez?"
)
