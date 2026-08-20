"""Deteccao deterministica de acao contextual para a resposta da EVA.

A decisao e SEMPRE por regras (nunca pelo LLM): navegacao decidida por LLM e
nao-deterministica e pode alucinar rota inexistente - inaceitavel em produto de
saude. O modelo apenas escreve o texto; este modulo, a partir da PERGUNTA da
usuaria, decide se um botao de acao acompanha a resposta.

Contrato:
- No maximo 1 acao por resposta. Se mais de uma regra casar, vence a de maior
  prioridade (ordem do catalogo `ACTION_RULES`).
- Conservador: na duvida, nao emite acao. Falso negativo e aceitavel; falso
  positivo (botao errado numa resposta de saude) nao e.
"""

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvaAction:
    slug: str
    label: str


@dataclass(frozen=True)
class _ActionRule:
    slug: str
    label: str
    patterns: list[re.Pattern[str]]
    # signup so faz sentido para visitante anonimo; para nutriz logada, nunca.
    anonymous_only: bool = False
    # Telas internas (minhas doacoes, perfil...) so existem com sessao: para
    # visitante anonimo a rota nem esta no router do front.
    authenticated_only: bool = False
    # Se algum destes casar, a regra e vetada (negacoes / falso positivo).
    blockers: list[re.Pattern[str]] = field(default_factory=list)


def _normalize(text: str) -> str:
    # Minusculas + remocao de acentos, para as regras casarem "ordenha" e
    # "ordenhá", "cadastro" e "cadástro", etc., sem duplicar padroes.
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p) for p in patterns]


# "quero ir para X", "me leva pra X", "onde vejo X", "abrir a tela de X".
# O verbo e obrigatorio: sem ele, "minhas doacoes" no meio de uma frase
# qualquer viraria botao (falso positivo).
_VERBOS_NAVEGACAO = (
    r"(?:ir|vou|abrir|abre|abro|acessar|acesso|ver|vejo|visualizar|mostrar|"
    r"mostra|leva|leve|levar|entrar|entro|voltar|volta|navegar|consultar|"
    r"consulto|checar|conferir|encontro|acompanhar|acompanho)"
)


def _navegacao(*alvos: str) -> list[str]:
    """Padroes de intencao de navegacao para cada alvo (ja normalizado).

    Gera duas formas por alvo: verbo de navegacao a ate ~28 caracteres do
    alvo ("quero ir para a tela de minhas doacoes") e a mencao explicita de
    tela/pagina ("tela de minhas doacoes").
    """
    padroes: list[str] = []
    for alvo in alvos:
        padroes.append(rf"\b{_VERBOS_NAVEGACAO}\b[^.?!]{{0,28}}\b{alvo}\b")
        padroes.append(rf"\b(?:tela|pagina|aba|secao)\b[^.?!]{{0,16}}\b{alvo}\b")
    return padroes


# Catalogo em ORDEM DE PRIORIDADE (primeiro = maior prioridade).
# Padroes sao avaliados sobre o texto ja normalizado (minusculo, sem acento).
ACTION_RULES: list[_ActionRule] = [
    _ActionRule(
        slug="signup",
        label="Criar conta",
        anonymous_only=True,
        patterns=_compile(
            [
                r"\bcriar (uma )?conta\b",
                r"\bquero (me )?cadastr",
                r"\bcomo (faco|posso|fazer) (para )?(me )?cadastr",
                r"\bme cadastr(ar|o|e)\b",
                r"\bfazer (o |meu )?cadastro\b",
                r"\bcadastr(ar|o|e)? na (nutriz|plataforma)\b",
                r"\bquero (comecar a |comecar )?doar\b",
                r"\bcomo (comeco|comecar|inicio|iniciar) (a )?doar\b",
                r"\bquero ser (uma )?doadora\b",
                r"\bcomo (me torno|virar|ser|me tornar) (uma )?doadora\b",
                r"\bcomo (funciona para|faco para) (ser|virar) doadora\b",
            ]
        ),
        blockers=_compile(
            [
                # negacoes explicitas de cadastro (nao a intencao de cadastrar)
                r"\bnao (precisa|preciso|quero|vou|precisa de)\b.{0,25}cadastr",
                r"\bsem (precisar de |precisar )?cadastr",
            ]
        ),
    ),
    _ActionRule(
        slug="login",
        label="Entrar",
        anonymous_only=True,
        patterns=_compile(
            [
                r"\blogin\b",
                r"\bentrar na (minha )?conta\b",
                r"\bacessar (a )?(minha )?conta\b",
                r"\bja tenho (uma )?conta\b",
                r"\bja sou cadastrada\b",
            ]
        ),
    ),
    _ActionRule(
        slug="whatsapp",
        label="Falar no WhatsApp",
        patterns=_compile(
            [
                r"\bfalar com (alguem|uma pessoa|atendente|humano|a equipe|voces|gente)\b",
                r"\bquero (falar|conversar) com (alguem|uma pessoa|a equipe|voces|atendente)\b",
                r"\batendimento humano\b",
                r"\bwhats ?app\b",
                r"\bfalar no whats",
                r"\bzap\b",
                r"\bcontato (da|com a|com) (lactare|equipe|voces)\b",
                r"\b(telefone|numero) (de|da|para) (contato|voces|lactare)\b",
            ]
        ),
    ),
    _ActionRule(
        slug="collection_points",
        label="Ver pontos de coleta",
        patterns=_compile(
            [
                r"\bonde (posso|eu posso|eu|da para|voce sabe onde) (doar|entregar)",
                r"\bonde doar\b",
                r"\bonde (fica|ficam|tem|encontro|acho) (o |os |um )?(banco de leite|posto de coleta|ponto de coleta)",
                r"\bpontos? de coleta\b",
                r"\bpostos? de coleta\b",
                r"\bbanco de leite (perto|proximo|mais perto|mais proximo|aqui perto)",
                r"\b(coleta|doar|doacao) perto de mim\b",
                r"\bonde (levo|entrego|deixo) (o )?leite\b",
                r"\blocal (de|para) (doacao|doar|coleta)\b",
            ]
        ),
    ),
    # --- Telas internas: so com sessao. Slug desconhecido nao vira botao no
    # front (catalogo fechado la tambem), entao emitir para anonimo seria
    # inofensivo, mas o veto evita prometer uma tela que ela nao tem.
    _ActionRule(
        slug="my_donations",
        label="Ver minhas doacoes",
        authenticated_only=True,
        patterns=_compile(
            _navegacao(
                "minhas doacoes",
                "minha doacao",
                "historico de doacoes",
                "doacoes anteriores",
                "andamento da (?:minha )?doacao",
            )
        ),
    ),
    _ActionRule(
        slug="new_donation",
        label="Iniciar nova doacao",
        authenticated_only=True,
        patterns=_compile(
            _navegacao("nova doacao", "outra doacao")
            + [
                r"\bquero doar (?:de novo|novamente|outra vez)\b",
                r"\b(?:fazer|criar|iniciar|comecar) (?:uma )?(?:nova )?doacao\b",
            ]
        ),
    ),
    _ActionRule(
        slug="profile",
        label="Abrir meu perfil",
        authenticated_only=True,
        patterns=_compile(
            _navegacao(
                "meu perfil",
                "perfil",
                "meus dados",
                "minha conta",
                "meu cadastro",
                "dados do bebe",
                "meu bebe",
            )
            + [r"\b(?:editar|atualizar|corrigir|mudar|alterar) (?:os )?meus dados\b"]
        ),
    ),
    _ActionRule(
        slug="content_hub",
        label="Ver conteudo educativo",
        authenticated_only=True,
        patterns=_compile(
            _navegacao(
                "conteudo educativo",
                "conteudos educativos",
                "central de conteudo",
                "materiais educativos",
            )
        ),
    ),
    _ActionRule(
        slug="home",
        label="Ir para o inicio",
        authenticated_only=True,
        patterns=_compile(
            _navegacao(
                "pagina inicial",
                "tela inicial",
                "pagina principal",
                "tela de inicio",
                "home",
                "painel",
                "inicio",
            )
        ),
        # "inicio" e palavra comum: veta quando fala do inicio de um processo.
        blockers=_compile(
            [
                r"inicio (?:da|de|do) (?:ordenha|coleta|doacao|amamentacao|gestacao|processo|tratamento)",
                r"(?:no|desde o) inicio",
            ]
        ),
    ),
    _ActionRule(
        slug="articles",
        label="Ler artigo completo",
        patterns=_compile(
            [
                r"\bcomo (faco|fazer|e|funciona|realizar|se faz) (a )?ordenh",
                r"\bcomo ordenhar\b",
                r"\bpasso a passo (da |de )?ordenh",
                r"\bcomo (armazenar|guardar|conservar|estocar) (o )?leite",
                r"\bcomo congelar (o )?leite",
                r"\bpor quanto tempo (o )?leite (dura|pode|vale|aguenta)",
                r"\barmazenamento (do|de) leite",
                r"\bhigiene (na|da|para|antes da) (ordenha|coleta|amamentacao)",
                r"\bcomo (higienizar|esterilizar|limpar) (os |as )?(frascos|potes|utensilios|maos)",
            ]
        ),
    ),
]


def detect_action(user_message: str, is_anonymous: bool) -> EvaAction | None:
    """Retorna a acao de maior prioridade que casa com a pergunta, ou None.

    is_anonymous controla as regras anonymous_only (signup).
    """
    if not user_message:
        return None

    text = _normalize(user_message)

    for rule in ACTION_RULES:
        if rule.anonymous_only and not is_anonymous:
            continue
        if rule.authenticated_only and is_anonymous:
            continue
        if any(blocker.search(text) for blocker in rule.blockers):
            continue
        if any(pattern.search(text) for pattern in rule.patterns):
            return EvaAction(slug=rule.slug, label=rule.label)

    return None
