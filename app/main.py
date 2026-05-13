from fastapi import FastAPI

from app.routers import chat_ws, health, me


app = FastAPI(title="Nutriz IA Service", version="0.1.0")

app.include_router(health.router)
app.include_router(me.router)
app.include_router(chat_ws.router)
