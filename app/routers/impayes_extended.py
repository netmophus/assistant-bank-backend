"""
Endpoints etendus pour la gestion avancee des impayes :
- Workflow d'escalade
- Promesses de paiement
- Scoring de recouvrabilite
- Attribution portefeuille agent
- Journal d'activite
- Dashboard agence avec ranking
- Evolution temporelle (graphiques)
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import Optional
import logging

from app.core.deps import get_current_user, get_org_admin
from app.schemas.impayes import (
    EscaladeActionRequest,
    SmsRappelEscaladeRequest,
    UpdateEscaladeConfigRequest,
    ValidationEscaladeConfigRequest,
    CreatePromesseRequest,
    UpdatePromesseStatutRequest,
    AttributionAgentRequest,
    CreateActionJournalRequest,
    UpdateScoringConfigRequest,
)
from app.models.impayes_extended import (
    get_escalade_config,
    save_escalade_config,
    save_escalade_config_with_validation,
    get_escalade_dossiers,
    escalader_manuellement,
    create_promesse,
    get_promesses,
    update_promesse_statut,
    get_promesses_stats,
    verifier_promesses_echues,
    calculer_scores_recouvrabilite,
    get_scoring_config,
    save_scoring_config,
    attribuer_credits_agent,
    get_portefeuilles_agents,
    desattribuer_credits,
    add_journal_entry,
    get_journal,
    get_dashboard_agences,
    get_evolution_temporelle,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/impayes",
    tags=["impayes-extended"],
)


# ===================== Escalade =====================

@router.get("/escalade/config")
async def api_get_escalade_config(
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    return await get_escalade_config(org_id)


@router.put("/escalade/config")
async def api_update_escalade_config(
    request: UpdateEscaladeConfigRequest,
    current_user: dict = Depends(get_org_admin),
):
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    
    # Convertir la requête en dict
    config = request.dict()
    
    # Sauvegarder avec validation
    success, result, errors = await save_escalade_config_with_validation(org_id, config)
    
    if not success:
        raise HTTPException(
            status_code=400, 
            detail={"errors": errors, "message": "Configuration invalide"}
        )
    
    return {"success": True, "config": result}


@router.post("/escalade/config/validate")
async def api_validate_escalade_config(
    request: ValidationEscaladeConfigRequest,
    current_user: dict = Depends(get_current_user),
):
    """Valide une configuration sans la sauvegarder"""
    from app.models.impayes_extended import _validate_escalade_config
    
    config = request.config.dict()
    valide, erreurs = _validate_escalade_config(config)
    
    return {
        "valide": valide,
        "erreurs": erreurs
    }


@router.get("/escalade/dossiers")
async def api_get_escalade_dossiers(
    date_situation: Optional[str] = None,
    niveau: Optional[str] = None,
    agence: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    return await get_escalade_dossiers(
        org_id, date_situation=date_situation,
        niveau_filtre=niveau, agence_filtre=agence,
        limit=limit, skip=skip
    )


@router.post("/escalade/action")
async def api_escalader_dossier(
    request: EscaladeActionRequest,
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    user_nom = current_user.get("full_name", current_user.get("email", ""))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    return await escalader_manuellement(
        org_id, request.ref_credit, request.nouveau_niveau,
        commentaire=request.commentaire,
        user_id=user_id, user_nom=user_nom
    )


@router.post("/escalade/sms-rappel")
async def api_envoyer_sms_rappel(
    request: SmsRappelEscaladeRequest,
    current_user: dict = Depends(get_current_user),
):
    """Envoie un SMS de rappel direct depuis l'onglet escalade"""
    from app.services.sms_service import send_sms
    from app.models.impayes_extended import add_journal_entry

    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    user_nom = current_user.get("full_name", current_user.get("email", ""))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")

    if not request.telephone:
        raise HTTPException(status_code=400, detail="Numéro de téléphone requis")
    if not request.message:
        raise HTTPException(status_code=400, detail="Message requis")

    try:
        result = await send_sms(request.telephone, request.message)
    except Exception as e:
        logger.error(f"Erreur send_sms: {e}", exc_info=True)
        result = {"success": False, "error": str(e)}

    # Journaliser l'action
    try:
        await add_journal_entry(
            org_id,
            request.ref_credit,
            "sms_rappel_escalade",
            f"SMS de rappel envoyé à {request.telephone} (niveau: {request.niveau_actuel or 'N/A'})",
            resultat="succes" if result.get("success") else "echec",
            user_id=user_id,
            user_nom=user_nom,
        )
    except Exception as e:
        logger.warning(f"Erreur journalisation SMS rappel: {e}")

    if result.get("success"):
        return {
            "success": True,
            "message": f"SMS de rappel envoyé à {request.telephone}",
            "data": result.get("data"),
        }
    else:
        return {
            "success": False,
            "message": f"Échec de l'envoi SMS: {result.get('error', 'Erreur inconnue')}",
        }


# ===================== Promesses de Paiement =====================

@router.post("/promesses")
async def api_create_promesse(
    request: CreatePromesseRequest,
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    user_nom = current_user.get("full_name", current_user.get("email", ""))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    return await create_promesse(
        org_id, request.ref_credit, request.nom_client,
        request.montant_promis, request.date_promesse,
        commentaire=request.commentaire,
        user_id=user_id, user_nom=user_nom
    )


@router.get("/promesses/stats")
async def api_get_promesses_stats(
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    return await get_promesses_stats(org_id)


@router.get("/promesses")
async def api_get_promesses(
    ref_credit: Optional[str] = None,
    statut: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    return await get_promesses(org_id, ref_credit=ref_credit, statut=statut, limit=limit, skip=skip)


@router.put("/promesses/{promesse_id}")
async def api_update_promesse(
    promesse_id: str,
    request: UpdatePromesseStatutRequest,
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    user_nom = current_user.get("full_name", current_user.get("email", ""))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    result = await update_promesse_statut(
        org_id, promesse_id, request.statut,
        montant_recu=request.montant_recu,
        commentaire=request.commentaire,
        user_id=user_id, user_nom=user_nom
    )
    if not result:
        raise HTTPException(status_code=404, detail="Promesse non trouvee")
    return result


@router.post("/promesses/verifier-echues")
async def api_verifier_promesses_echues(
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    echues = await verifier_promesses_echues(org_id)
    return {"echues": echues, "count": len(echues)}


# ===================== Scoring =====================

@router.get("/scoring/config")
async def api_get_scoring_config(current_user: dict = Depends(get_current_user)):
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    return await get_scoring_config(org_id)


@router.put("/scoring/config")
async def api_save_scoring_config(
    request: UpdateScoringConfigRequest,
    current_user: dict = Depends(get_org_admin),
):
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    config_dict = request.config.model_dump()
    await save_scoring_config(org_id, config_dict)
    return {"message": "Configuration scoring sauvegardée", "config": config_dict}


@router.get("/scoring")
async def api_get_scores(
    date_situation: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    return await calculer_scores_recouvrabilite(org_id, date_situation=date_situation)


# ===================== Portefeuille Agents =====================

@router.post("/portefeuille/attribuer")
async def api_attribuer(
    request: AttributionAgentRequest,
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    user_nom = current_user.get("full_name", current_user.get("email", ""))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    return await attribuer_credits_agent(
        org_id, request.agent_id, request.agent_nom, request.ref_credits,
        department_id=request.department_id, service_id=request.service_id,
        user_id=user_id, user_nom=user_nom
    )


@router.get("/portefeuille")
async def api_get_portefeuilles(
    date_situation: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    user_role = current_user.get("role", "user")
    user_id = str(current_user.get("id"))
    
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    
    # Logique de filtrage par rôle
    agent_id_filter = None
    if user_role == "user":
        # Agent simple : ne voit que ses dossiers
        agent_id_filter = user_id
    elif user_role == "admin":
        # Admin : voit tous les portefeuilles (pas de filtre)
        agent_id_filter = None
    # TODO: Ajouter logique pour directeur département plus tard
    
    return await get_portefeuilles_agents(org_id, date_situation=date_situation, agent_id=agent_id_filter)


@router.post("/portefeuille/desattribuer")
async def api_desattribuer(
    data: dict,
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    user_role = current_user.get("role", "user")
    user_id = str(current_user.get("id"))
    
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    
    # Seul l'admin peut désattribuer des dossiers
    if user_role != "admin":
        raise HTTPException(
            status_code=403, 
            detail="Seuls les administrateurs peuvent désattribuer des dossiers."
        )
    
    agent_id = data.get("agent_id", "")
    ref_credits = data.get("ref_credits", [])
    if not agent_id or not ref_credits:
        raise HTTPException(status_code=400, detail="agent_id et ref_credits requis")
    return await desattribuer_credits(org_id, agent_id, ref_credits)


# ===================== Journal d'Activite =====================

@router.post("/journal")
async def api_add_journal(
    request: CreateActionJournalRequest,
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    user_nom = current_user.get("full_name", current_user.get("email", ""))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    return await add_journal_entry(
        org_id, request.ref_credit, request.type_action,
        request.description, montant=request.montant,
        resultat=request.resultat,
        user_id=user_id, user_nom=user_nom
    )


@router.get("/journal")
async def api_get_journal(
    ref_credit: Optional[str] = None,
    type_action: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    print(f"DEBUG: org_id={org_id}, ref_credit={ref_credit}, type_action={type_action}")
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    result = await get_journal(org_id, ref_credit=ref_credit, type_action=type_action, limit=limit, skip=skip)
    print(f"DEBUG: result={result}")
    return result


@router.post("/promesses")
async def api_create_promesse(
    request: CreatePromesseRequest,
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    user_nom = current_user.get("full_name", current_user.get("email", ""))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    
    return await create_promesse(
        org_id, request.ref_credit, request.nom_client,
        request.montant_promis, request.date_promesse,
        request.commentaire, user_id=user_id, user_nom=user_nom
    )


# ===================== Dashboard Agence =====================

@router.get("/dashboard/agences")
async def api_get_dashboard_agences(
    date_situation: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    return await get_dashboard_agences(org_id, date_situation=date_situation)


# ===================== Evolution temporelle (graphiques) =====================

@router.get("/dashboard/evolution")
async def api_get_evolution(
    limit: int = 12,
    current_user: dict = Depends(get_current_user),
):
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(status_code=400, detail="Organisation requise")
    return await get_evolution_temporelle(org_id, limit=limit)
