import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.db import get_database

from app.routers.auth import router as auth_router
from app.routers.organization import router as org_router
from app.routers.license import router as license_router
from app.routers.department import router as department_router
from app.routers.question import router as question_router
from app.routers.formation import router as formation_router
from app.routers.qcm import router as qcm_router
from app.routers.ressource import router as ressource_router
from app.routers.stock.consommables import router as stock_consommables_router
from app.routers.stock.demandes import router as stock_demandes_router
from app.routers.stock.dashboard import router as stock_dashboard_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
)

# Allow all localhost origins for development
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:5173",  # Vite default port
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",  # Allow any localhost port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.get("/health", tags=["system"])
async def health_check():
    db = get_database()
    await db.command("ping")
    return {"status": "ok", "db": settings.MONGO_DB_NAME}


app.include_router(auth_router)
app.include_router(org_router)
app.include_router(license_router)
app.include_router(department_router)
app.include_router(question_router)
app.include_router(formation_router)
app.include_router(qcm_router)
app.include_router(ressource_router)
app.include_router(stock_consommables_router)
app.include_router(stock_demandes_router)
app.include_router(stock_dashboard_router)
