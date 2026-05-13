from fastapi import APIRouter, Depends

from app.services.auth import get_current_user_id


router = APIRouter(tags=["me"])


@router.get("/me")
async def read_me(user_id: str = Depends(get_current_user_id)) -> dict[str, str]:
    return {"user_id": user_id}
