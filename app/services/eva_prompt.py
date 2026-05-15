from app.models import Message
from app.schemas.profile import NutrizProfile
from app.schemas.rag import ChunkSearchResult


EVA_SYSTEM_PROMPT = """Você é a EVA, assistente virtual da plataforma Nutriz, da Lactare/Eurofarma, dedicada à doação de leite humano.

Quem você atende:
- Nutrizes (mulheres lactantes) interessadas em doar leite materno ou tirar dúvidas sobre amamentação e o processo de doação.

Tom e estilo:
- Acolhedor, respeitoso e profissional. Nunca infantilize a interlocutora.
- Trate sempre por "você". Não use "mamãe", "mãezinha" ou diminutivos.
- Respostas curtas e objetivas: no máximo 4 parágrafos. Lembre-se que muitas vezes a pessoa está com o bebê no colo.
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
) -> list[dict[str, str]]:
    context_block = _format_chunks_as_context(chunks)

    system_parts = [EVA_SYSTEM_PROMPT]
    if profile is not None:
        system_parts.append(_format_profile_as_context(profile))
    system_parts.append(context_block)
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
        context_parts.append(chunk.content)
        context_parts.append("")

    return "\n".join(context_parts)


def _format_profile_as_context(profile: NutrizProfile) -> str:
    parts = ["PERFIL DA NUTRIZ (use para personalizar a resposta):"]
    parts.append(f"- Nome: {profile.name}")

    if profile.baby is not None:
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
        "- Personalize a resposta com base no perfil quando relevante (idade do bebe, localizacao)"
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
