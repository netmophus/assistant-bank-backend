from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Dict, Optional

from app.services.stock.stock_analytics import (
    get_stock_stats,
    get_consumption_data,
    get_top_consumables,
    get_department_consumption,
)
from app.services.stock.stock_ai import (
    analyze_stock_prediction,
    detect_anomalies,
    get_ai_recommendations,
)
from app.core.deps import get_current_user

router = APIRouter(
    prefix="/stock/dashboard",
    tags=["stock-dashboard"],
)


@router.get("/stats")
async def get_dashboard_stats_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Récupère les statistiques générales du tableau de bord.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent accéder au tableau de bord.",
        )
    
    try:
        stats = await get_stock_stats(str(user_org_id))
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.get("/graphiques")
async def get_graphiques_data_endpoint(
    days: int = Query(30, ge=7, le=365),
    current_user: dict = Depends(get_current_user)
):
    """
    Récupère les données pour les graphiques.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent accéder aux graphiques.",
        )
    
    try:
        consumption_data = await get_consumption_data(str(user_org_id), days=days)
        top_consumables = await get_top_consumables(str(user_org_id), limit=10)
        department_consumption = await get_department_consumption(str(user_org_id))
        
        return {
            "consumption_timeline": consumption_data,
            "top_consumables": top_consumables,
            "department_consumption": department_consumption,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération: {str(e)}",
        )


@router.post("/analyses/prediction")
async def get_prediction_endpoint(
    consommable_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Génère une prédiction de consommation via IA.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent accéder aux analyses IA.",
        )
    
    try:
        prediction = await analyze_stock_prediction(str(user_org_id), consommable_id)
        return prediction
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'analyse: {str(e)}",
        )


@router.post("/analyses/anomalies")
async def get_anomalies_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Détecte les anomalies dans la consommation.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent accéder aux analyses IA.",
        )
    
    try:
        anomalies = await detect_anomalies(str(user_org_id))
        return {"anomalies": anomalies}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la détection: {str(e)}",
        )


@router.post("/analyses/recommandations")
async def get_recommendations_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Génère des recommandations intelligentes via IA.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent accéder aux analyses IA.",
        )
    
    try:
        recommendations = await get_ai_recommendations(str(user_org_id))
        return {"recommandations": recommendations}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la génération: {str(e)}",
        )


@router.get("/optimisation")
async def get_optimisation_score_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Calcule un score d'optimisation du stock.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent accéder au score d'optimisation.",
        )
    
    try:
        from app.models.stock.consommable import list_consommables_by_org, get_consommables_low_stock
        
        consommables = await list_consommables_by_org(str(user_org_id))
        alertes = await get_consommables_low_stock(str(user_org_id))
        
        if not consommables:
            return {"score": 0, "message": "Aucun consommable enregistré"}
        
        # Calculer le score basé sur plusieurs facteurs
        # Score = 100 - (pourcentage d'alertes * 30) - (taux de rupture * 50)
        
        taux_alertes = (len(alertes) / len(consommables)) * 100 if consommables else 0
        
        # Vérifier les ruptures de stock
        ruptures = sum(1 for c in consommables if c["quantite_stock"] == 0)
        taux_ruptures = (ruptures / len(consommables)) * 100 if consommables else 0
        
        score = max(0, 100 - (taux_alertes * 0.3) - (taux_ruptures * 0.5))
        
        return {
            "score": round(score, 2),
            "taux_alertes": round(taux_alertes, 2),
            "taux_ruptures": round(taux_ruptures, 2),
            "message": "Excellent" if score >= 80 else "Bon" if score >= 60 else "À améliorer"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du calcul: {str(e)}",
        )

