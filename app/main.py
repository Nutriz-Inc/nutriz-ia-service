from fastapi import FastAPI


app = FastAPI(title="Nutriz IA Service", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "nutriz-ia-service"}
