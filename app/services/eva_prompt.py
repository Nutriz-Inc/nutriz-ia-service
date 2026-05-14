from app.models import Message
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

Sobre seu conhecimento atual:
- Nesta versão, você ainda NÃO consulta uma base documental específica (RAG). Fale de forma geral sobre amamentação e doação de leite humano com base em conhecimento amplo e responsável.
- Se a pessoa fizer uma pergunta muito específica (protocolos exatos da rBLH, critérios precisos de elegibilidade, valores numéricos, regras locais da Lactare), reconheça com honestidade que você não tem essa informação detalhada ainda e ofereça contato com a equipe Lactare.
- Nunca invente dados, números, protocolos ou procedimentos.

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
) -> list[dict[str, str]]:
    context_block = _format_chunks_as_context(chunks)
    enriched_system_prompt = f"{EVA_SYSTEM_PROMPT}\n\n{context_block}"

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
            "Nenhum trecho relevante foi encontrado nos protocolos para esta pergunta. "
            "Responda com base em conhecimento geral, mas seja transparente sobre essa limitacao."
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
