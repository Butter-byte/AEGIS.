from fastapi import FastAPI
from backend.api.routes import router

app = FastAPI(title="Aegis Foundation API")
app.include_router(router)