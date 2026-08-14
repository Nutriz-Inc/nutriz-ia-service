from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BabyProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_user_baby: str
    name: str | None
    birth_date: datetime
    age_in_days: int
    age_description: str


class AddressProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    zipcode: str
    city: str
    state: str
    neighborhood: str


class NutrizProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_user: str
    name: str
    baby: BabyProfile | None
    address: AddressProfile | None
