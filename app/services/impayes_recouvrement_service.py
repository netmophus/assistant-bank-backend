"""
Service pour le calcul des indicateurs de recouvrement

Ce service calcule les indicateurs de performance de recouvrement en comparant
automatiquement les snapshots entre différentes dates de situation.
"""
from typing import List, Optional, Dict
from datetime import datetime
from app.models.impayes import (
    ARREARS_SNAPSHOTS_COLLECTION,
    SMS_HISTORY_COLLECTION,
    get_available_dates_situation,
)
from app.services.impayes_snapshot_service import compare_snapshots
from app.core.db import get_database
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)


async def detecter_regularisations_automatiques(
    organization_id: str,
    date_situation_debut: Optional[str] = None,
    date_situation_fin: Optional[str] = None
) -> List[dict]:
    """
    Détecte automatiquement les régularisations en comparant les snapshots entre différentes dates de situation.
    
    Logique :
    - Pour chaque crédit dans un snapshot à une date donnée
    - Chercher le même crédit dans un snapshot plus récent
    - Si le crédit n'existe plus OU si le montant_total_impaye a diminué → régularisation détectée
    
    Args:
        organization_id: ID de l'organisation
        date_situation_debut: Date de début pour filtrer les comparaisons (optionnel)
        date_situation_fin: Date de fin pour filtrer les comparaisons (optionnel)
        
    Returns:
        Liste des régularisations détectées avec :
        - ref_credit: Référence du crédit
        - montant_recupere: Montant récupéré
        - date_regularisation: Date de régularisation
        - date_snapshot_initial: Date du snapshot initial
        - date_snapshot_final: Date du snapshot final
        - type: "complete" ou "partielle"
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return []
    
    # Récupérer toutes les dates de situation disponibles, triées
    dates_situation = await get_available_dates_situation(organization_id)
    
    if not dates_situation:
        return []
    
    # Trier par ordre chronologique (croissant)
    dates_situation.sort()
    
    logger.info(f"[REGULARISATIONS] Dates de situation trouvées: {dates_situation}")
    
    if len(dates_situation) < 2:
        logger.warning(f"[REGULARISATIONS] Pas assez de dates pour comparer ({len(dates_situation)} dates)")
        return []
    
    # Filtrer les dates si demandé
    if date_situation_debut:
        dates_situation = [d for d in dates_situation if d >= date_situation_debut]
    if date_situation_fin:
        dates_situation = [d for d in dates_situation if d <= date_situation_fin]
    
    logger.info(f"[REGULARISATIONS] Dates de situation après filtrage: {dates_situation}")
    
    if len(dates_situation) < 2:
        logger.warning(f"[REGULARISATIONS] Pas assez de dates après filtrage ({len(dates_situation)} dates)")
        return []
    
    regularisations_detectees = []
    
    # Comparer chaque date avec la suivante
    for i in range(len(dates_situation) - 1):
        date_actuelle = dates_situation[i]
        date_suivante = dates_situation[i + 1]
        
        # Utiliser la fonction de comparaison pour détecter les régularisations
        comparaison = await compare_snapshots(organization_id, date_actuelle, date_suivante)
        
        # Extraire les régularisations complètes
        for reg_complete in comparaison.get("regularisations_completes", []):
            regularisations_detectees.append({
                "ref_credit": reg_complete.get("ref_credit"),
                "snapshot_id": None,  # On pourrait le récupérer si nécessaire
                "montant_recupere": reg_complete.get("montant_recupere", 0),
                "date_regularisation": date_suivante,
                "date_snapshot_initial": date_actuelle,
                "date_snapshot_final": date_suivante,
                "type": "complete"
            })
        
        # Extraire les régularisations partielles
        for reg_partielle in comparaison.get("regularisations_partielles", []):
            regularisations_detectees.append({
                "ref_credit": reg_partielle.get("ref_credit"),
                "snapshot_id": None,
                "montant_recupere": reg_partielle.get("montant_recupere", 0),
                "date_regularisation": date_suivante,
                "date_snapshot_initial": date_actuelle,
                "date_snapshot_final": date_suivante,
                "type": "partielle"
            })
    
    return regularisations_detectees


async def calculer_indicateurs_recouvrement(
    organization_id: str,
    date_debut: Optional[str] = None,
    date_fin: Optional[str] = None,
    date_situation: Optional[str] = None
) -> dict:
    """
    Calcule les indicateurs de performance de recouvrement en comparant automatiquement les snapshots.
    
    Les régularisations sont détectées automatiquement en comparant les snapshots entre différentes dates de situation :
    - Si un crédit disparaît d'un snapshot à l'autre → régularisation complète
    - Si le montant impayé diminue → régularisation partielle
    
    Indicateurs calculés:
    - Taux de recouvrement (montant récupéré / montant impayé)
    - Délai moyen de recouvrement (jours)
    - Taux de réponse aux SMS (après envoi)
    - Efficacité par tranche de retard
    - Taux de régularisation après SMS
    
    Args:
        organization_id: ID de l'organisation
        date_debut: Date de début pour la période d'analyse (optionnel)
        date_fin: Date de fin pour la période d'analyse (optionnel)
        date_situation: Date de situation spécifique pour filtrer les snapshots initiaux (optionnel)
        
    Returns:
        Dictionnaire contenant tous les indicateurs de recouvrement
    """
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return {}
    
    # 1. Détecter les régularisations automatiquement en comparant les snapshots
    regularisations = await detecter_regularisations_automatiques(
        organization_id=organization_id,
        date_situation_debut=date_debut,
        date_situation_fin=date_fin
    )
    
    logger.info(f"[INDICATEURS] Régularisations détectées: {len(regularisations)}")
    for reg in regularisations[:5]:  # Afficher les 5 premières
        logger.info(f"[INDICATEURS] - {reg.get('ref_credit')}: {reg.get('montant_recupere')} FCFA ({reg.get('type')})")
    
    # 2. Récupérer les snapshots d'impayés pour la période analysée
    query_snapshots = {"organization_id": org_oid}
    if date_situation:
        query_snapshots["date_situation"] = date_situation
    elif date_debut or date_fin:
        if date_debut:
            query_snapshots["date_situation"] = {"$gte": date_debut}
        if date_fin:
            if "date_situation" in query_snapshots and isinstance(query_snapshots["date_situation"], dict):
                query_snapshots["date_situation"]["$lte"] = date_fin
            else:
                query_snapshots["date_situation"] = {"$lte": date_fin}
    
    snapshots = await db[ARREARS_SNAPSHOTS_COLLECTION].find(query_snapshots).to_list(length=10000)
    logger.info(f"[INDICATEURS] Snapshots trouvés: {len(snapshots)}")
    
    if not snapshots:
        return {
            "taux_recouvrement": 0.0,
            "montant_total_impaye": 0.0,
            "montant_total_recupere": 0.0,
            "delai_moyen_recouvrement": None,
            "nombre_regularisations": 0,
            "taux_reponse_sms": 0.0,
            "nombre_sms_envoyes": 0,
            "nombre_reponses_sms": 0,
            "efficacite_par_tranche": {},
            "taux_regularisation_apres_sms": 0.0,
            "nombre_regularisations_apres_sms": 0,
            "nombre_sms_avec_regularisation": 0,
            "date_debut": date_debut,
            "date_fin": date_fin
        }
    
    # Créer un mapping ref_credit -> snapshot pour les calculs
    ref_credit_to_snapshot = {}
    for snap in snapshots:
        ref_credit = snap.get("ref_credit", "")
        if ref_credit:
            if ref_credit not in ref_credit_to_snapshot:
                ref_credit_to_snapshot[ref_credit] = snap
            else:
                # Prendre le snapshot le plus récent pour chaque ref_credit
                current_date = snap.get("created_at", "")
                existing_date = ref_credit_to_snapshot[ref_credit].get("created_at", "")
                if current_date > existing_date:
                    ref_credit_to_snapshot[ref_credit] = snap
    
    # Créer un mapping ref_credit -> régularisations
    regularisations_by_ref_credit = {}
    for reg in regularisations:
        ref_credit = reg.get("ref_credit", "")
        if ref_credit:
            if ref_credit not in regularisations_by_ref_credit:
                regularisations_by_ref_credit[ref_credit] = []
            regularisations_by_ref_credit[ref_credit].append(reg)
    
    # 3. Récupérer les SMS envoyés depuis l'historique SMS
    # Les SMS envoyés sont dans SMS_HISTORY_COLLECTION avec status="SENT"
    query_sms = {"organization_id": org_oid, "status": "SENT"}
    if date_debut or date_fin:
        date_query = {}
        if date_debut:
            try:
                date_query["$gte"] = datetime.fromisoformat(date_debut.replace("Z", "+00:00"))
            except:
                pass
        if date_fin:
            try:
                date_query["$lte"] = datetime.fromisoformat(date_fin.replace("Z", "+00:00"))
            except:
                pass
        if date_query:
            query_sms["sent_at"] = date_query
    
    sms_envoyes = await db[SMS_HISTORY_COLLECTION].find(query_sms).to_list(length=10000)
    
    # Créer un mapping ref_credit -> SMS (via linked_credit)
    sms_by_ref_credit = {}
    for sms in sms_envoyes:
        ref_credit = sms.get("linked_credit", "")
        if ref_credit:
            if ref_credit not in sms_by_ref_credit:
                sms_by_ref_credit[ref_credit] = []
            sms_by_ref_credit[ref_credit].append(sms)
    
    # 4. Calculer les montants totaux
    if date_situation:
        montant_total_impaye = sum(s.get("montant_total_impaye", 0) for s in snapshots)
    else:
        # Prendre les snapshots de la première date disponible
        dates_disponibles = await get_available_dates_situation(organization_id)
        if dates_disponibles:
            first_date = dates_disponibles[-1]  # La plus ancienne (dernière dans la liste triée)
            snapshots_first_date = await db[ARREARS_SNAPSHOTS_COLLECTION].find({
                "organization_id": org_oid,
                "date_situation": first_date
            }).to_list(length=10000)
            montant_total_impaye = sum(s.get("montant_total_impaye", 0) for s in snapshots_first_date)
            logger.info(f"[INDICATEURS] Montant total impayé calculé sur {len(snapshots_first_date)} snapshots de la date {first_date}")
        else:
            montant_total_impaye = sum(s.get("montant_total_impaye", 0) for s in snapshots)
    
    montant_total_recupere = sum(reg.get("montant_recupere", 0) for reg in regularisations)
    logger.info(f"[INDICATEURS] Montant total impayé: {montant_total_impaye} FCFA")
    logger.info(f"[INDICATEURS] Montant total récupéré: {montant_total_recupere} FCFA")
    
    # Taux de recouvrement
    taux_recouvrement = (montant_total_recupere / montant_total_impaye * 100) if montant_total_impaye > 0 else 0.0
    
    # Délai moyen de recouvrement
    delais_recouvrement = []
    for reg in regularisations:
        date_snapshot_initial = reg.get("date_snapshot_initial", "")
        date_regularisation = reg.get("date_regularisation", "")
        
        if date_snapshot_initial and date_regularisation:
            try:
                if isinstance(date_snapshot_initial, str):
                    date_init = datetime.strptime(date_snapshot_initial, "%Y-%m-%d")
                else:
                    continue
                
                if isinstance(date_regularisation, str):
                    date_reg = datetime.strptime(date_regularisation, "%Y-%m-%d")
                else:
                    continue
                
                delai = (date_reg - date_init).days
                if delai >= 0:
                    delais_recouvrement.append(delai)
            except:
                continue
    
    delai_moyen_recouvrement = sum(delais_recouvrement) / len(delais_recouvrement) if delais_recouvrement else None
    
    # Taux de réponse aux SMS
    nombre_sms_envoyes = len(sms_envoyes)
    nombre_reponses_sms = 0
    
    for sms in sms_envoyes:
        ref_credit = sms.get("linked_credit", "")
        sent_at = sms.get("sent_at")
        
        if ref_credit and sent_at:
            if isinstance(sent_at, str):
                try:
                    sent_at = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
                except:
                    continue
            elif not isinstance(sent_at, datetime):
                continue
            
            # Vérifier s'il y a une régularisation après l'envoi du SMS
            if ref_credit in regularisations_by_ref_credit:
                for reg in regularisations_by_ref_credit[ref_credit]:
                    date_reg_str = reg.get("date_regularisation", "")
                    if date_reg_str:
                        try:
                            date_reg = datetime.strptime(date_reg_str, "%Y-%m-%d")
                            if date_reg >= sent_at:
                                nombre_reponses_sms += 1
                                break
                        except:
                            continue
    
    taux_reponse_sms = (nombre_reponses_sms / nombre_sms_envoyes * 100) if nombre_sms_envoyes > 0 else 0.0
    
    # Efficacité par tranche de retard
    efficacite_par_tranche = {}
    tranches_credits = {}
    
    for reg in regularisations:
        ref_credit = reg.get("ref_credit", "")
        if ref_credit in ref_credit_to_snapshot:
            snapshot = ref_credit_to_snapshot[ref_credit]
            tranche = snapshot.get("bucket_retard", "Non défini")
            
            if tranche not in tranches_credits:
                tranches_credits[tranche] = {
                    "montant_impaye": 0.0,
                    "montant_recupere": 0.0,
                    "nombre": 0
                }
            
            montant_impaye_initial = snapshot.get("montant_total_impaye", 0)
            tranches_credits[tranche]["montant_impaye"] += montant_impaye_initial
            tranches_credits[tranche]["montant_recupere"] += reg.get("montant_recupere", 0)
            tranches_credits[tranche]["nombre"] += 1
    
    for tranche, data in tranches_credits.items():
        montant_impaye = data["montant_impaye"]
        montant_recupere = data["montant_recupere"]
        taux = (montant_recupere / montant_impaye * 100) if montant_impaye > 0 else 0.0
        efficacite_par_tranche[tranche] = {
            "taux_recouvrement": round(taux, 2),
            "nombre": data["nombre"],
            "montant_impaye": round(montant_impaye, 2),
            "montant_recupere": round(montant_recupere, 2)
        }
    
    # Taux de régularisation après SMS
    nombre_regularisations_apres_sms = 0
    nombre_sms_avec_regularisation = 0
    
    for sms in sms_envoyes:
        ref_credit = sms.get("linked_credit", "")
        sent_at = sms.get("sent_at")
        
        if ref_credit and sent_at:
            if isinstance(sent_at, str):
                try:
                    sent_at = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
                except:
                    continue
            elif not isinstance(sent_at, datetime):
                continue
            
            if ref_credit in regularisations_by_ref_credit:
                for reg in regularisations_by_ref_credit[ref_credit]:
                    date_reg_str = reg.get("date_regularisation", "")
                    if date_reg_str:
                        try:
                            date_reg = datetime.strptime(date_reg_str, "%Y-%m-%d")
                            if date_reg >= sent_at:
                                nombre_regularisations_apres_sms += 1
                                nombre_sms_avec_regularisation += 1
                                break
                        except:
                            continue
    
    taux_regularisation_apres_sms = (nombre_sms_avec_regularisation / nombre_sms_envoyes * 100) if nombre_sms_envoyes > 0 else 0.0
    
    return {
        "taux_recouvrement": round(taux_recouvrement, 2),
        "montant_total_impaye": round(montant_total_impaye, 2),
        "montant_total_recupere": round(montant_total_recupere, 2),
        "delai_moyen_recouvrement": round(delai_moyen_recouvrement, 2) if delai_moyen_recouvrement is not None else None,
        "nombre_regularisations": len(regularisations),
        "taux_reponse_sms": round(taux_reponse_sms, 2),
        "nombre_sms_envoyes": nombre_sms_envoyes,
        "nombre_reponses_sms": nombre_reponses_sms,
        "efficacite_par_tranche": efficacite_par_tranche,
        "taux_regularisation_apres_sms": round(taux_regularisation_apres_sms, 2),
        "nombre_regularisations_apres_sms": nombre_regularisations_apres_sms,
        "nombre_sms_avec_regularisation": nombre_sms_avec_regularisation,
        "date_debut": date_debut,
        "date_fin": date_fin
    }

