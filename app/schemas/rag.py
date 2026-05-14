from typing import Any

from pydantic import BaseModel, ConfigDict


class ChunkSearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    content: str
    source: str
    score: float
    metadata_json: dict[str, Any] | None
