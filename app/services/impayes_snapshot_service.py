"""
Service pour la gestion et la comparaison des snapshots d'impayés

Ce service gère :
- La récupération des snapshots par date_situation
- La comparaison entre deux dates de situation
- Les fonctions utilitaires pour naviguer dans l'historique
"""
from typing import List, Optional, Dict, Tuple
from datetime import datetime
from app.models.impayes import (
    get_available_dates_situation,
    get_snapshots_by_filters,
    ARREARS_SNAPSHOTS_COLLECTION,
)
from app.schemas.impayes import FiltresImpayes
from app.core.db import get_database
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)


async def get_available_situation_dates(organization_id: str) -> List[str]:
    """
    Récupère la liste des dates de situation disponibles, triées par ordre décroissant (plus récentes en premier)
    
    Args:
        organization_id: ID de l'organisation
        
    Returns:
        Liste des dates de situation (format YYYY-MM-DD), triées du plus récent au plus ancien
    """
    dates = await get_available_dates_situation(organization_id)
    return dates


async def get_latest_situation_date(organization_id: str) -> Optional[str]:
    """
    Récupère la date de situation la plus récente
    
    Args:
        organization_id: ID de l'organisation
        
    Returns:
        Date de situation la plus récente (format YYYY-MM-DD) ou None si aucune date disponible
    """
    dates = await get_available_situation_dates(organization_id)
    return dates[0] if dates else None


async def get_previous_situation_date(organization_id: str, current_date: str) -> Optional[str]:
    """
    Récupère la date de situation précédente par rapport à une date donnée
    
    Args:
        organization_id: ID de l'organisation
        current_date: Date de situation actuelle (format YYYY-MM-DD)
        
    Returns:
        Date de situation précédente ou None si aucune date précédente disponible
    """
    dates = await get_available_situation_dates(organization_id)
    
    # Trouver l'index de la date actuelle
    try:
        current_index = dates.index(current_date)
        # La date précédente est à l'index suivant (car triées du plus récent au plus ancien)
        if current_index + 1 < len(dates):
            return dates[current_index + 1]
    except ValueError:
        # Date actuelle non trouvée dans la liste
        pass
    
    return None


async def get_snapshots_by_date(
    organization_id: str,
    date_situation: str,
    limit: int = 10000,
    skip: int = 0
) -> List[dict]:
    """
    Récupère tous les snapshots pour une date de situation donnée
    
    Args:
        organization_id: ID de l'organisation
        date_situation: Date de situation (format YYYY-MM-DD)
        limit: Nombre maximum de snapshots à récupérer
        skip: Nombre de snapshots à ignorer (pour pagination)
        
    Returns:
        Liste des snapshots pour cette date
    """
    filtres = FiltresImpayes(date_situation=date_situation)
    snapshots = await get_snapshots_by_filters(organization_id, filtres, limit=limit, skip=skip)
    return snapshots


async def get_snapshot_id_by_date(organization_id: str, date_situation: str) -> Optional[str]:
    """
    Récupère le snapshot_id (identifiant de batch/fichier) pour une date de situation donnée
    
    Comme tous les snapshots d'un même fichier partagent le même snapshot_id,
    on récupère simplement le premier snapshot pour cette date.
    
    Args:
        organization_id: ID de l'organisation
        date_situation: Date de situation (format YYYY-MM-DD)
        
    Returns:
        snapshot_id (UUID du batch) ou None si aucun snapshot trouvé
    """
    snapshots = await get_snapshots_by_date(organization_id, date_situation, limit=1)
    if snapshots and len(snapshots) > 0:
        return snapshots[0].get("snapshot_id")
    return None


async def compare_snapshots(
    organization_id: str,
    date_ancienne: str,
    date_recente: str
) -> Dict:
    """
    Compare les snapshots entre deux dates de situation
    
    Cette fonction compare les crédits entre deux dates et détecte :
    - Les crédits régularisés complètement (présents à date_ancienne, absents à date_recente)
    - Les crédits régularisés partiellement (montant impayé qui diminue)
    - Les nouveaux crédits impayés (absents à date_ancienne, présents à date_recente)
    - Les crédits stables (présents aux deux dates avec montant identique)
    - Les crédits qui se sont aggravés (montant impayé qui augmente)
    
    Args:
        organization_id: ID de l'organisation
        date_ancienne: Date de situation ancienne (format YYYY-MM-DD)
        date_recente: Date de situation récente (format YYYY-MM-DD)
        
    Returns:
        Dictionnaire contenant :
        - regularisations_completes: Liste des crédits régularisés complètement
        - regularisations_partielles: Liste des crédits régularisés partiellement
        - nouveaux_credits: Liste des nouveaux crédits impayés
        - credits_stables: Liste des crédits stables
        - credits_aggraves: Liste des crédits qui se sont aggravés
        - statistiques: Statistiques de comparaison (montants, nombres, etc.)
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {}
    
    # Récupérer les snapshots pour les deux dates
    snapshots_anciens = await get_snapshots_by_date(organization_id, date_ancienne, limit=10000)
    snapshots_recents = await get_snapshots_by_date(organization_id, date_recente, limit=10000)
    
    # Créer des dictionnaires indexés par ref_credit pour faciliter la comparaison
    snapshots_anciens_dict = {s.get("ref_credit"): s for s in snapshots_anciens}
    snapshots_recents_dict = {s.get("ref_credit"): s for s in snapshots_recents}
    
    # Initialiser les listes de résultats
    regularisations_completes = []
    regularisations_partielles = []
    nouveaux_credits = []
    credits_stables = []
    credits_aggraves = []
    
    # Comparer les crédits
    ref_credits_anciens = set(snapshots_anciens_dict.keys())
    ref_credits_recents = set(snapshots_recents_dict.keys())
    
    # Crédits présents aux deux dates
    credits_communs = ref_credits_anciens & ref_credits_recents
    
    # Crédits régularisés complètement (présents à date_ancienne, absents à date_recente)
    credits_reguliers_complets = ref_credits_anciens - ref_credits_recents
    for ref_credit in credits_reguliers_complets:
        snapshot_ancien = snapshots_anciens_dict[ref_credit]
        regularisations_completes.append({
            "ref_credit": ref_credit,
            "nom_client": snapshot_ancien.get("nom_client", ""),
            "montant_recupere": snapshot_ancien.get("montant_total_impaye", 0),
            "date_situation_ancienne": date_ancienne,
            "date_situation_recente": date_recente,
            "type": "complete"
        })
    
    # Crédits nouveaux (absents à date_ancienne, présents à date_recente)
    credits_nouveaux = ref_credits_recents - ref_credits_anciens
    for ref_credit in credits_nouveaux:
        snapshot_recent = snapshots_recents_dict[ref_credit]
        nouveaux_credits.append({
            "ref_credit": ref_credit,
            "nom_client": snapshot_recent.get("nom_client", ""),
            "montant_impaye": snapshot_recent.get("montant_total_impaye", 0),
            "date_situation": date_recente,
        })
    
    # Comparer les crédits communs
    for ref_credit in credits_communs:
        snapshot_ancien = snapshots_anciens_dict[ref_credit]
        snapshot_recent = snapshots_recents_dict[ref_credit]
        
        montant_ancien = snapshot_ancien.get("montant_total_impaye", 0)
        montant_recent = snapshot_recent.get("montant_total_impaye", 0)
        
        if montant_recent < montant_ancien:
            # Régularisation partielle
            regularisations_partielles.append({
                "ref_credit": ref_credit,
                "nom_client": snapshot_ancien.get("nom_client", ""),
                "montant_ancien": montant_ancien,
                "montant_recent": montant_recent,
                "montant_recupere": montant_ancien - montant_recent,
                "date_situation_ancienne": date_ancienne,
                "date_situation_recente": date_recente,
                "type": "partielle"
            })
        elif montant_recent > montant_ancien:
            # Crédit aggravé
            credits_aggraves.append({
                "ref_credit": ref_credit,
                "nom_client": snapshot_ancien.get("nom_client", ""),
                "montant_ancien": montant_ancien,
                "montant_recent": montant_recent,
                "augmentation": montant_recent - montant_ancien,
                "date_situation_ancienne": date_ancienne,
                "date_situation_recente": date_recente,
            })
        else:
            # Crédit stable
            credits_stables.append({
                "ref_credit": ref_credit,
                "nom_client": snapshot_ancien.get("nom_client", ""),
                "montant_impaye": montant_ancien,
                "date_situation_ancienne": date_ancienne,
                "date_situation_recente": date_recente,
            })
    
    # Calculer les statistiques
    montant_total_ancien = sum(s.get("montant_total_impaye", 0) for s in snapshots_anciens)
    montant_total_recent = sum(s.get("montant_total_impaye", 0) for s in snapshots_recents)
    montant_recupere_total = (
        sum(r.get("montant_recupere", 0) for r in regularisations_completes) +
        sum(r.get("montant_recupere", 0) for r in regularisations_partielles)
    )
    montant_nouveaux_total = sum(n.get("montant_impaye", 0) for n in nouveaux_credits)
    montant_aggravation_total = sum(a.get("augmentation", 0) for a in credits_aggraves)
    
    # Calculer les variations
    variation_montant = montant_total_recent - montant_total_ancien
    variation_pourcentage = (
        (variation_montant / montant_total_ancien * 100) if montant_total_ancien > 0 else 0
    )
    
    variation_nombre = len(snapshots_recents) - len(snapshots_anciens)
    variation_nombre_pourcentage = (
        (variation_nombre / len(snapshots_anciens) * 100) if len(snapshots_anciens) > 0 else 0
    )
    
    return {
        "date_ancienne": date_ancienne,
        "date_recente": date_recente,
        "regularisations_completes": regularisations_completes,
        "regularisations_partielles": regularisations_partielles,
        "nouveaux_credits": nouveaux_credits,
        "credits_stables": credits_stables,
        "credits_aggraves": credits_aggraves,
        "statistiques": {
            "nombre_credits_ancien": len(snapshots_anciens),
            "nombre_credits_recent": len(snapshots_recents),
            "variation_nombre": variation_nombre,
            "variation_nombre_pourcentage": round(variation_nombre_pourcentage, 2),
            "montant_total_ancien": montant_total_ancien,
            "montant_total_recent": montant_total_recent,
            "variation_montant": variation_montant,
            "variation_montant_pourcentage": round(variation_pourcentage, 2),
            "montant_recupere_total": montant_recupere_total,
            "montant_nouveaux_total": montant_nouveaux_total,
            "montant_aggravation_total": montant_aggravation_total,
            "nombre_regularisations_completes": len(regularisations_completes),
            "nombre_regularisations_partielles": len(regularisations_partielles),
            "nombre_nouveaux_credits": len(nouveaux_credits),
            "nombre_credits_stables": len(credits_stables),
            "nombre_credits_aggraves": len(credits_aggraves),
        }
    }


async def get_snapshot_summary(organization_id: str, date_situation: str) -> Optional[Dict]:
    """
    Récupère un résumé d'un snapshot (batch) pour une date de situation donnée
    
    Args:
        organization_id: ID de l'organisation
        date_situation: Date de situation (format YYYY-MM-DD)
        
    Returns:
        Dictionnaire contenant :
        - snapshot_id: Identifiant du batch
        - date_situation: Date de situation
        - nombre_snapshots: Nombre de crédits dans ce batch
        - statistiques: Statistiques agrégées (montants, répartitions, etc.)
    """
    snapshots = await get_snapshots_by_date(organization_id, date_situation, limit=10000)
    
    if not snapshots:
        return None
    
    # Récupérer le snapshot_id (tous les snapshots d'un batch ont le même snapshot_id)
    snapshot_id = snapshots[0].get("snapshot_id") if snapshots else None
    
    # Calculer les statistiques
    total_montant = sum(s.get("montant_total_impaye", 0) for s in snapshots)
    total_encours = sum(s.get("encours_principal", 0) for s in snapshots)
    candidats_restruct = sum(1 for s in snapshots if s.get("candidat_restructuration", False))
    
    # Répartitions
    repartition_tranches = {}
    repartition_segments = {}
    repartition_agences = {}
    
    for s in snapshots:
        tranche = s.get("bucket_retard", "Non défini")
        repartition_tranches[tranche] = repartition_tranches.get(tranche, 0) + 1
        
        segment = s.get("segment", "Non défini")
        repartition_segments[segment] = repartition_segments.get(segment, 0) + 1
        
        agence = s.get("agence", "Non défini")
        repartition_agences[agence] = repartition_agences.get(agence, 0) + 1
    
    return {
        "snapshot_id": snapshot_id,
        "date_situation": date_situation,
        "nombre_snapshots": len(snapshots),
        "statistiques": {
            "total_montant_impaye": total_montant,
            "total_encours": total_encours,
            "total_credits": len(snapshots),
            "candidats_restructuration": candidats_restruct,
            "ratio_impaye_encours": round((total_montant / total_encours * 100) if total_encours > 0 else 0, 2),
            "repartition_tranches": repartition_tranches,
            "repartition_segments": repartition_segments,
            "repartition_agences": repartition_agences,
        }
    }

