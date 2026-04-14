import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from config import settings
from models.database import init_db
from routers import auth, documents

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Inicializando banco de dados...")
    await init_db()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs("outputs", exist_ok=True)
    logger.info("DocFinance API pronta!")
    yield

app = FastAPI(title="DocFinance API", version="1.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"])

app.include_router(auth.router)
app.include_router(documents.router)

# Servir frontend
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if not os.path.exists(frontend_dir):
    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")

@app.get("/", include_in_schema=False)
async def serve_frontend():
    for d in [frontend_dir, "frontend", "../frontend"]:
        index = os.path.join(d, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
    return JSONResponse({"message": "DocFinance API", "docs": "/docs"})

@app.get("/health", tags=["Sistema"])
async def health():
    return {"status": "ok", "version": "1.0.0"}
