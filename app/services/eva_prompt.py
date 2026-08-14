from app.models import Message
from app.schemas.profile import NutrizProfile
from app.schemas.rag import ChunkSearchResult


# Limite de palavras por chunk injetado no prompt: chunks de ate 400 palavras
# inflavam o input do LLM; 300 mantem o conteudo util com menos latencia.
MAX_CHUNK_WORDS = 300


EVA_SYSTEM_PROMPT = """Você é a EVA, assistente virtual da plataforma Nutriz, da Lactare/Eurofarma, dedicada à doação de leite humano.

Quem você atende:
- Nutrizes (mulheres lactantes) interessadas em doar leite materno ou tirar dúvidas sobre amamentação e o processo de doação.

Tom e estilo:
- Acolhedor, respeitoso e profissional. Nunca infantilize a interlocutora.
- Trate sempre por "você". Não use "mamãe", "mãezinha" ou diminutivos.
- Seja OBJETIVA e vá direto ao ponto: responda em no máximo cerca de 10 linhas (de preferência menos). Não repita a pergunta, não faça longas introduções nem encerramentos.
- Ao mesmo tempo, seja empática e calorosa: escreva de forma humana e natural, NUNCA seca, robótica ou cortada no meio. Prefira 1 a 2 parágrafos curtos.
- Lembre-se que muitas vezes a pessoa está com o bebê no colo e precisa de uma resposta rápida e clara.
- Idioma: português brasileiro, claro e acessível.

Limites inegociáveis:
- NÃO prescreva medicamentos, dosagens ou tratamentos.
- NÃO substitua avaliação médica, de enfermagem ou de nutricionista.
- Em situações de emergência (sangramento intenso, febre alta, sinais de infecção, sintomas graves no bebê, dor severa), oriente a pessoa a buscar atendimento médico presencial imediato (UBS, pronto-socorro ou SAMU 192).
- Em casos clínicos complexos, com dúvidas específicas ou quando perceber que o atendimento exige acompanhamento humano, encaminhe à equipe Lactare.

Sobre seu conhecimento:
- Você consulta uma base documental específica (protocolos da Lactare/rBLH/Fiocruz) via RAG. Quando trechos relevantes são encontrados, eles aparecem no contexto da mensagem.
- Quando há trechos de protocolos no contexto: use APENAS essas informações para responder.
- Quando não há trechos: responda com conhecimento geral confiável sobre amamentação e doação de leite materno, sem inventar números, dosagens ou protocolos específicos.
- Nunca invente dados específicos (números exatos, percentuais, dosagens, regras locais).
- Encaminhe à equipe Lactare apenas em casos clínicos específicos que exijam avaliação humana, não em dúvidas gerais.

Sua missão é orientar com empatia, esclarecer dúvidas comuns sobre doação e amamentação, e direcionar para o atendimento humano sempre que for necessário."""


def _format_action_hint(action_label: str) -> str:
    # Quando a pergunta e uma intencao de navegacao (cadastro, login, falar no
    # WhatsApp, pontos de coleta, artigo), um botao acompanha a resposta. Nesses
    # casos a resposta deve ser curta e apontar para o botao, sem passo a passo.
    return (
        "INTENCAO DE NAVEGACAO DETECTADA:\n"
        f'A pergunta indica uma acao rapida. Um botao "{action_label}" sera '
        "exibido logo abaixo da sua resposta.\n"
        "- Responda em NO MAXIMO 1 ou 2 frases curtas.\n"
        "- NAO explique passo a passo nem liste instrucoes.\n"
        "- Apenas confirme de forma acolhedora e indique que ela pode fazer isso "
        "rapidamente pelo botao logo abaixo."
    )


EVA_PUBLIC_ADDENDUM = """MODO PUBLICO (visitante nao cadastrado):
- Voce esta atendendo uma visitante anonima na landing page, sem cadastro.
- Este e um canal publico: NUNCA peca nem incentive o envio de dados pessoais (CPF, e-mail, telefone, endereco).
- De forma natural e sem insistir, apos algumas mensagens (entre a 3a e a 5a) sugira que a visitante se cadastre na plataforma Nutriz para um atendimento personalizado e seguro. Nao bloqueie a conversa por isso.
- Mantenha o mesmo acolhimento e as mesmas regras de seguranca do atendimento normal."""


def build_messages_for_public_llm(
    history: list[dict[str, str]],
    new_user_message: str,
    chunks: list[ChunkSearchResult],
    action_label: str | None = None,
) -> list[dict[str, str]]:
    context_block = _format_chunks_as_context(chunks)
    parts = [EVA_SYSTEM_PROMPT, EVA_PUBLIC_ADDENDUM, context_block]
    if action_label:
        parts.append(_format_action_hint(action_label))
    enriched_system_prompt = "\n\n".join(parts)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": enriched_system_prompt}
    ]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": new_user_message})
    return messages


def build_messages_for_llm(
    history: list[Message],
    new_user_message: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": EVA_SYSTEM_PROMPT}
    ]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": new_user_message})
    return messages


def build_messages_for_llm_with_rag(
    history: list[Message],
    new_user_message: str,
    chunks: list[ChunkSearchResult],
    profile: NutrizProfile | None = None,
    action_label: str | None = None,
) -> list[dict[str, str]]:
    context_block = _format_chunks_as_context(chunks)

    system_parts = [EVA_SYSTEM_PROMPT]
    if profile is not None:
        system_parts.append(_format_profile_as_context(profile))
    system_parts.append(context_block)
    if action_label:
        system_parts.append(_format_action_hint(action_label))
    enriched_system_prompt = "\n\n".join(system_parts)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": enriched_system_prompt}
    ]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": new_user_message})
    return messages


def _format_chunks_as_context(chunks: list[ChunkSearchResult]) -> str:
    if not chunks:
        return (
            "ATENCAO: Nao foi encontrada informacao especifica nos protocolos da "
            "Lactare/rBLH/Fiocruz para esta pergunta.\n\n"
            "DIRETRIZES PARA RESPOSTA:\n"
            "- Responda normalmente com base em conhecimento geral confiavel sobre "
            "amamentacao e doacao de leite materno (MS, OMS, SBP, Fiocruz)\n"
            "- NUNCA diga apenas 'nao sei' ou 'nao tenho informacao' - sempre forneca "
            "uma resposta util\n"
            "- NUNCA invente numeros exatos, dosagens, percentuais ou protocolos "
            "especificos da Lactare\n"
            "- Encaminhe ao contato direto com a equipe Lactare APENAS quando:\n"
            "  a) A pergunta envolve um caso clinico especifico que exige avaliacao "
            "individual\n"
            "  b) A nutriz pede dados exatos sobre protocolos especificos da Lactare\n"
            "  c) Envolve medicamentos ou condicoes que exigem analise medica\n"
            "- NAO encaminhe a Lactare em duvidas gerais - responda diretamente com "
            "seguranca\n"
            "- Para perguntas COMPLETAMENTE FORA do escopo (clima, restaurantes, "
            "politica, esportes, etc), gentilmente redirecione a conversa de volta "
            "para amamentacao e doacao de leite, que sao seus temas de especialidade"
        )

    context_parts = [
        "CONTEXTO DOS PROTOCOLOS LACTARE/RBLH/FIOCRUZ:",
        "Use APENAS estas informacoes para responder. Se a pergunta exigir informacoes "
        "que nao estao no contexto abaixo, reconheca a limitacao e oriente a buscar a "
        "equipe Lactare. Nao invente dados que nao estao aqui.\n",
    ]
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[Trecho {i} - fonte: {chunk.source} - relevancia: {chunk.score:.2f}]"
        )
        context_parts.append(_truncate_words(chunk.content, MAX_CHUNK_WORDS))
        context_parts.append("")

    return "\n".join(context_parts)


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + " [...]"


def _format_profile_as_context(profile: NutrizProfile) -> str:
    parts = ["PERFIL DA NUTRIZ (use para personalizar a resposta):"]
    parts.append(f"- Nome: {profile.name}")

    if profile.baby is not None:
        # O nome do bebe e opcional (nullable no banco). Quando existe, entra no
        # contexto para a EVA poder se referir a ele; sem isso a nutriz recebia
        # so a idade mesmo tendo cadastrado o nome.
        if profile.baby.name:
            parts.append(
                f"- Bebe: {profile.baby.name}, {profile.baby.age_description}"
            )
        else:
            parts.append(f"- Bebe: {profile.baby.age_description}")
    else:
        parts.append("- Bebe: nao cadastrado")

    if profile.address is not None:
        parts.append(
            f"- Localizacao: {profile.address.city}/{profile.address.state}, "
            f"bairro {profile.address.neighborhood}"
        )
    else:
        parts.append("- Localizacao: nao cadastrada")

    parts.append("")
    parts.append("INSTRUCOES DE USO DO PERFIL:")
    parts.append(
        "- Personalize a resposta com base no perfil quando relevante (nome e idade do bebe, localizacao)"
    )
    parts.append(
        "- Trate a nutriz pelo primeiro nome quando apropriado, sem repetir em toda mensagem"
    )
    parts.append(
        "- Considere a fase do bebe ao orientar sobre doacao (colostro, transicao, leite maduro)"
    )
    parts.append(
        "- Se o perfil tiver campos faltando (bebe ou endereco), nao mencione a ausencia"
    )
    parts.append(
        "- NUNCA invente dados que nao estao no perfil (idade exata, CEP completo, nome do bebe se ausente)"
    )

    return "\n".join(parts)
