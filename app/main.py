import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.db import get_database
from app.routers.auth import router as auth_router
from app.routers.credit import router as credit_router
from app.routers.credit_particulier import router as credit_particulier_router
from app.routers.credit_pme import router as credit_pme_router
from app.routers.department import router as department_router
from app.routers.formation import router as formation_router
from app.routers.license import router as license_router
from app.routers.organization import router as org_router
from app.routers.qcm import router as qcm_router
from app.routers.question import router as question_router
from app.routers.conversation import router as conversation_router
from app.routers.ressource import router as ressource_router
from app.routers.stock.consommables import router as stock_consommables_router
from app.routers.stock.dashboard import router as stock_dashboard_router
from app.routers.stock.demandes import router as stock_demandes_router
from app.routers.stock.introductions_stock import router as stock_introductions_router
from app.routers.stock.validation_consommables import router as stock_validation_consommables_router
from app.routers.impayes_config import router as impayes_config_router
from app.routers.impayes import router as impayes_router
from app.routers.impayes_extended import router as impayes_extended_router
from app.routers.tab_permissions import router as tab_permissions_router
from app.routers.documents import router as documents_router
from app.routers.pcb import router as pcb_router
from app.routers.global_knowledge import router as global_knowledge_router
from app.routers.ai_config import router as ai_config_router
from app.routers.voice import router as voice_router
from app.routers.rag_new import router as rag_new_router
from app.routers.credit_policy import router as credit_policy_router
from app.routers.credit_pme_policy import router as credit_pme_policy_router
from app.routers.public_subscription import router as public_subscription_router
from app.routers.admin_subscription import router as admin_subscription_router
from app.routers.public_institution_demo import router as public_institution_demo_router
from app.routers.admin_institution_demo import router as admin_institution_demo_router
from app.models.subscription_request import ensure_subscription_request_indexes
from app.models.institution_demo_request import ensure_institution_demo_indexes
from app.models.otp import ensure_otp_indexes

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
)

# Allow all localhost origins for development + production domains
# origins = [
#     "http://localhost:3000",
#     "http://127.0.0.1:3000",
#     "http://localhost:3001",
#     "http://127.0.0.1:3001",
#     "http://localhost:5173",  # Vite default port
#     "http://127.0.0.1:5173",
#     "http://localhost:5174",
#     "http://127.0.0.1:5174",
#     # Production Heroku
#     "https://novabank-frontend-f9d4c030d386.herokuapp.com",
# ]


origins = [
    # ─── Dev local — Next.js frontend ───
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",

    # ─── Dev local — Expo Web ───
    "http://localhost:8081",
    "http://127.0.0.1:8081",
    "http://localhost:19006",
    "http://127.0.0.1:19006",

    # ─── Production — Next.js (site web) ───
    "https://www.miznas.co",
    "https://miznas.co",

    # ─── Production — Expo Web (app mobile) ───
    "https://app.miznas.co",

    # ─── Fallback Vercel (sans domaine custom) ───
    "https://miznas-pilot-mobile.vercel.app",

    # ─── Legacy Heroku frontend ───
    "https://novabank-frontend-f9d4c030d386.herokuapp.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+):\d+",
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
app.include_router(conversation_router)
app.include_router(formation_router)
app.include_router(qcm_router)
app.include_router(ressource_router)
app.include_router(stock_consommables_router)
app.include_router(stock_demandes_router)
app.include_router(stock_dashboard_router)
app.include_router(stock_introductions_router)
app.include_router(stock_validation_consommables_router)
app.include_router(credit_router)
app.include_router(credit_particulier_router)
app.include_router(credit_pme_router)
app.include_router(impayes_config_router)
app.include_router(impayes_router)
app.include_router(impayes_extended_router)
app.include_router(tab_permissions_router)
app.include_router(documents_router)
app.include_router(pcb_router)
app.include_router(global_knowledge_router)
app.include_router(ai_config_router)
app.include_router(voice_router)
app.include_router(rag_new_router)
app.include_router(credit_policy_router)
app.include_router(credit_pme_policy_router)
app.include_router(public_subscription_router)
app.include_router(admin_subscription_router)
app.include_router(public_institution_demo_router)
app.include_router(admin_institution_demo_router)


@app.on_event("startup")
async def _ensure_indexes():
    await ensure_subscription_request_indexes()
    await ensure_institution_demo_indexes()
    await ensure_otp_indexes()
