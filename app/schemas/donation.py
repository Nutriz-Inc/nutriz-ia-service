# Contexto de doacao enviado a EVA no modo logado.
#
# LIMITE INVIOLAVEL: nenhum campo aqui pode carregar dado sensivel de saude.
# So entram identificador, nome de etapa, status, datas e local de coleta. O
# teor clinico (descricao de etapa, timeline, feedback, resultado de exame)
# nunca e lido do banco - ver app/models/donation.py e donation_context_service.

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CollectionPlace(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # Nome do posto/banco de leite quando a coleta e em unidade; None quando a
    # coleta e no endereco da propria nutriz. Rua e numero NUNCA entram: o
    # bairro/cidade ja bastam para ela se situar e sao o que o perfil ja envia.
    donation_point_name: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None


class ActiveDonation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_donation: str
    is_active: bool
    created_at: datetime
    # None quando todas as 4 etapas estao concluidas.
    current_step_name: str | None = None
    # Rotulo ja tratado (pt-BR e, na etapa de exame, mascarado). None quando a
    # etapa ainda nem foi aberta pela equipe Lactare.
    current_step_status_label: str | None = None
    current_step_set_date: datetime | None = None
    next_step_name: str | None = None
    place: CollectionPlace | None = None


class DonationHistory(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_donations: int
    concluded_donations: int
    total_volume_ml: Decimal | None = None
    last_donation_at: datetime | None = None


class DonationContext(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # Cada bloco e independente: None significa "a busca falhou, siga sem isso".
    # Historico com total_donations=0 e um estado valido (nutriz sem doacoes),
    # diferente de None.
    donation: ActiveDonation | None = None
    history: DonationHistory | None = None

    def is_empty(self) -> bool:
        return self.donation is None and self.history is None
