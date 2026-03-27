"""
Routes pour la politique de crédit PME et l'analyse de dossiers.
Préfixe : /credit-policy/pme
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Any

from app.schemas.credit_pme_policy import (
    PMEPolicyConfig,
    PMEApplicationInput,
    PMEDecisionResult,
)
from app.models.credit_pme_policy import (
    get_pme_policy,
    save_pme_policy,
    save_pme_application,
    get_user_pme_applications,
    get_org_pme_applications,
)
from app.services.pme_decision_engine import run_pme_decision_engine
from app.core.deps import get_current_user, get_org_admin

router = APIRouter(
    prefix="/credit-policy/pme",
    tags=["credit-pme-policy"],
)

DEFAULT_RATE = 10.0


def _clean_policy_doc(doc: dict) -> dict:
    for k in ("id", "organization_id", "updated_at", "created_at"):
        doc.pop(k, None)
    return doc


# ── Policy management ──────────────────────────────────────────────────────────

@router.get("/policy", response_model=PMEPolicyConfig)
async def get_pme_policy_endpoint(current_user: dict = Depends(get_current_user)):
    """Récupère la politique PME active de l'organisation."""
    org_id = str(current_user.get("organization_id", ""))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation introuvable.")
    doc = await get_pme_policy(org_id)
    if not doc:
        return PMEPolicyConfig()
    return PMEPolicyConfig(**_clean_policy_doc(doc))


@router.put("/policy", response_model=PMEPolicyConfig)
async def save_pme_policy_endpoint(
    config: PMEPolicyConfig,
    current_user: dict = Depends(get_org_admin),
):
    """Enregistre ou met à jour la politique PME (admin uniquement)."""
    org_id = str(current_user.get("organization_id", ""))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation introuvable.")
    await save_pme_policy(org_id, config)
    return config


# ── Analysis ───────────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=PMEDecisionResult)
async def analyze_pme_endpoint(
    application: PMEApplicationInput,
    current_user: dict = Depends(get_current_user),
):
    """Analyse une demande de crédit PME avec le moteur de décision déterministe."""
    org_id = str(current_user.get("organization_id", ""))
    user_id = str(current_user.get("id") or current_user.get("_id", ""))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation introuvable.")

    # Charger la politique
    policy_doc = await get_pme_policy(org_id)
    if policy_doc:
        try:
            policy = PMEPolicyConfig(**_clean_policy_doc(policy_doc))
        except Exception:
            policy = PMEPolicyConfig()
    else:
        policy = PMEPolicyConfig()

    if not policy.general.enabled:
        raise HTTPException(status_code=400, detail="La politique de crédit PME est désactivée.")

    annual_rate = application.taux_annuel_pct or DEFAULT_RATE

    result = run_pme_decision_engine(application, policy, annual_rate)
    await save_pme_application(user_id, org_id, application, result)
    return result


# ── History ────────────────────────────────────────────────────────────────────

@router.get("/applications", response_model=List[Any])
async def get_my_pme_applications(current_user: dict = Depends(get_current_user)):
    """Historique des analyses PME de l'utilisateur."""
    user_id = str(current_user.get("id") or current_user.get("_id", ""))
    return await get_user_pme_applications(user_id)


@router.get("/applications/org", response_model=List[Any])
async def get_org_pme_applications_endpoint(current_user: dict = Depends(get_org_admin)):
    """Toutes les analyses PME de l'organisation (admin)."""
    org_id = str(current_user.get("organization_id", ""))
    return await get_org_pme_applications(org_id)
