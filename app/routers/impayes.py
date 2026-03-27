"""
Endpoints pour la gestion des impayés.
"""
from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File
from typing import List, Optional
import io
import logging
from bson import ObjectId

logger = logging.getLogger(__name__)
logger.error("IMPAYES ROUTER LOADED - Archives endpoint available")  # Debug


def safe_cell_value(cell):
    """Convertit de manière sécurisée la valeur d'une cellule en string"""
    try:
        # Essayer d'abord de lire la valeur formatée (display_value) pour préserver le texte exact
        # Cela est important pour les références de crédit qui peuvent être de longs nombres
        value = cell.value
        if value is None:
            return None
        elif isinstance(value, str):
            return value
        elif isinstance(value, (int, float)):
            # Pour les nombres, préserver tous les chiffres sans notation scientifique
            # Important pour les références de crédit qui peuvent être de longs nombres
            if isinstance(value, int):
                return str(value)  # Les entiers Python n'ont pas de limite de précision
            elif isinstance(value, float):
                # Pour les floats, Excel peut avoir tronqué la précision (limite à 15 chiffres)
                # Essayer de lire la valeur formatée si disponible
                try:
                    # Si la cellule a un format texte ou général, essayer de récupérer la valeur telle qu'affichée
                    if hasattr(cell, 'number_format'):
                        # Pour les nombres entiers stockés comme float, convertir en int
                        if value.is_integer():
                            # Convertir en int puis en string pour éviter la notation scientifique
                            return str(int(value))
                        else:
                            # Pour les floats non-entiers, utiliser un format qui préserve la précision
                            return f"{value:.15f}".rstrip('0').rstrip('.')
                    else:
                        if value.is_integer():
                            return str(int(value))
                        else:
                            return f"{value:.15f}".rstrip('0').rstrip('.')
                except:
                    # En cas d'erreur, utiliser la conversion standard
                    if value.is_integer():
                        return str(int(value))
                    else:
                        return str(value)
        else:
            return str(value)
    except Exception as e:
        print(f"Erreur lors de la conversion de la valeur de cellule: {e}")
        return None


def normalize_column_name(name):
    """Normalise un nom de colonne pour la comparaison (insensible à la casse, sans espaces, caractères spéciaux)"""
    if not name:
        return ""
    # Normaliser : minuscules, supprimer espaces, underscores, slashes, et remplacer certains caractères
    normalized = str(name).strip().lower()
    # Remplacer les accents par leurs équivalents sans accent
    import unicodedata
    normalized = unicodedata.normalize('NFD', normalized)
    normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    # Remplacer les caractères spéciaux qui peuvent être des erreurs de frappe
    normalized = normalized.replace(" ", "").replace("_", "").replace("/", "i").replace("\\", "i")
    # Remplacer "l" par "i" dans certains contextes (erreur de frappe commune)
    # Mais seulement si c'est suivi de "mpay" pour éviter les faux positifs
    if "lmpay" in normalized:
        normalized = normalized.replace("lmpay", "impay")
    return normalized


def get_column_value(row_dict, column_mapping, column_name):
    """Récupère la valeur d'une colonne en utilisant le mapping normalisé"""
    normalized = normalize_column_name(column_name)
    if normalized in column_mapping:
        actual_header = column_mapping[normalized]
        return row_dict.get(actual_header, "")
    # Fallback: essayer directement avec le nom original
    return row_dict.get(column_name, "")


def normalize_segment_value(value):
    """Normalise une valeur de segment pour correspondre à SegmentEnum"""
    if not value:
        return "PARTICULIER"
    value_upper = str(value).strip().upper()
    # Mapping des variations courantes
    segment_mapping = {
        "PARTICULIER": "PARTICULIER",
        "PARTICULIERS": "PARTICULIER",
        "SOCIETE": "PME",
        "SOCIETES": "PME",
        "ENTREPRISE": "PME",
        "ENTREPRISES": "PME",
        "PME": "PME",
        "PMI": "PMI"
    }
    return segment_mapping.get(value_upper, "PARTICULIER")  # Par défaut PARTICULIER


def normalize_produit_value(value):
    """Normalise une valeur de produit pour correspondre à ProduitEnum"""
    if not value:
        return "Conso"
    value_lower = str(value).strip().lower()
    # Chercher des mots-clés dans la description du produit
    if "immo" in value_lower or "immobilier" in value_lower:
        return "Immo"
    elif "tresorerie" in value_lower or "trésorerie" in value_lower:
        return "Trésorerie"
    elif "conso" in value_lower or "consommation" in value_lower:
        return "Conso"
    else:
        return "Conso"  # Par défaut


def normalize_statut_value(value):
    """Normalise une valeur de statut pour correspondre à StatutInterneEnum"""
    if not value:
        return "Impayé"
    value_upper = str(value).strip().upper()
    statut_mapping = {
        "IMPAYE": "Impayé",
        "IMPAYÉ": "Impayé",
        "IMPAYES": "Impayé",
        "IMPAYÉS": "Impayé",
        "NORMAL": "Normal",
        "DOUTEUX": "Douteux",
        "COMPROMIS": "Compromis"
    }
    return statut_mapping.get(value_upper, "Impayé")  # Par défaut Impayé


def normalize_phone_number(phone: str) -> Optional[str]:
    """
    Normalise un numéro de téléphone au format 227XXXXXXXXX (sans le +)
    
    Formats acceptés:
    - +22796648383
    - 22796648383
    - 227 96 64 83 83
    - 0022796648383
    - etc.
    
    Returns:
        Numéro normalisé au format 227XXXXXXXXX (sans +) ou None si invalide
    """
    if not phone:
        return None
    
    # Nettoyer le numéro : enlever espaces, tirets, points
    cleaned = str(phone).strip().replace(" ", "").replace("-", "").replace(".", "").replace("(", "").replace(")", "")
    
    # Si le numéro commence par +227, enlever le +
    if cleaned.startswith("+227"):
        cleaned = cleaned[1:]  # Enlever le +
    
    # Si le numéro commence par 00227, remplacer par 227
    if cleaned.startswith("00227"):
        cleaned = cleaned[2:]  # Enlever le 00
    
    # Si le numéro commence déjà par 227, vérifier la longueur
    if cleaned.startswith("227"):
        # Vérifier que le numéro a la bonne longueur (227 + 8 chiffres = 11 caractères)
        if len(cleaned) == 11 and cleaned[3:].isdigit():
            return cleaned
        else:
            print(f"[WARNING] Numéro de téléphone invalide (longueur incorrecte): {phone} -> {cleaned}")
            return None
    
    # Si aucun format reconnu, retourner None
    print(f"[WARNING] Numéro de téléphone invalide (format non reconnu): {phone}")
    return None


def find_column_by_pattern(headers, patterns):
    """
    Trouve une colonne en cherchant des patterns dans les noms normalisés
    patterns: liste de chaînes à chercher (normalisées), triées du plus spécifique au moins spécifique
    """
    # Trier les patterns par longueur décroissante pour donner priorité aux plus spécifiques
    sorted_patterns = sorted(patterns, key=len, reverse=True)
    
    for header in headers:
        if not header:
            continue
        normalized = normalize_column_name(header)
        # Essayer d'abord les patterns les plus longs (plus spécifiques)
        for pattern in sorted_patterns:
            # Vérifier que le pattern correspond exactement ou est contenu dans le nom
            # Mais éviter les faux positifs (ex: "principal" ne doit pas matcher "encoursprincipal")
            if pattern == normalized:
                return header
            # Pour les correspondances partielles, être plus strict
            elif len(pattern) >= 8 and pattern in normalized:  # Patterns de 8+ caractères sont assez spécifiques
                return header
            # Pour les patterns courts, vérifier qu'ils ne sont pas dans un mot plus long
            elif len(pattern) < 8:
                # Vérifier que le pattern est au début ou à la fin, ou qu'il y a un séparateur
                if normalized.startswith(pattern) or normalized.endswith(pattern):
                    return header
    return None


def build_column_mapping(headers):
    """
    Construit un mapping intelligent entre les noms de colonnes Excel et les noms attendus
    Gère les variations de noms (tronqués, casse différente, etc.)
    """
    mapping = {}
    
    # Mapping des patterns vers les noms attendus
    column_patterns = {
        "datesituation": ["datesituation", "datesit", "situation"],
        "refcredit": ["refcredit", "refcredit", "referencecredit", "ref"],
        "idclient": ["idclient", "idclient", "clientid"],
        "nomclient": ["nomclient", "nom", "client"],
        "telephoneclient": ["telephoneclient", "telephone", "tel", "phone"],
        "segment": ["segment"],
        "agence": ["agence", "agency"],
        "produit": ["produit", "product"],
        "montantinitial": ["montantinitial", "montantiniti", "montantinit", "montant"],
        "encoursprincipal": ["encoursprincipal", "encoursprinc", "encours"],
        "principalimpaye": ["principalimpaye", "principallmp", "principallmpay", "principallmpayé", "principallmpaye", "principalimpay", "principalimpayé", "principalimpay"],
        "interetsimpayes": ["interetsimpayes", "interetlmpay", "interetsmpay", "interets/mpay", "interets/mpayés", "interetsimpayés", "interets"],
        "penalitesimpayees": ["penalitesimpayees", "penalitelmpanb", "penalitesimpayées", "penalites"],
        "nbecheancesimpayees": ["nbecheancesimpayees", "nbecheancel", "nbecheancesimpayées", "nbecheances", "echeances"],
        "joursretard": ["joursretard", "jourretard", "retard"],
        "datederniereecheanceimpayee": ["datederniereecheanceimpayee", "datederniereecheancelmpayee", "datedernierecheancelmpayee", "datedernier", "dateecheance"],
        "statutinterne": ["statutinterne", "statut"],
        "garanties": ["garanties", "garantie"],
        "revenumensuel": ["revenumensuel", "revenu"],
        "commentaire": ["commentaire", "comment", "note"]
    }
    
    # Créer le mapping inverse (normalized -> actual header)
    for expected_name, patterns in column_patterns.items():
        found_header = find_column_by_pattern(headers, patterns)
        if found_header:
            normalized = normalize_column_name(expected_name)
            mapping[normalized] = found_header
            print(f"[DEBUG] Mapping: '{expected_name}' -> '{found_header}'")
    
    return mapping

from app.schemas.impayes import (
    LigneImpayeImport,
    ImportImpayesRequest,
    ImportImpayesResponse,
    ArrearsSnapshot,
    OutboundMessage,
    OutboundMessagePublic,
    StatistiquesImpayes,
    EvolutionIndicateur,
    EvolutionStatistiques,
    ComparaisonStatistiques,
    ComparaisonParallele,
    FiltresImpayes,
    ActionRestructuration,
    IndicateursRecouvrement,
    DashboardDetaille,
    CreateArchiveRequest,
    ArchiveResponse,
)
from app.models.impayes import (
    save_arrears_snapshot,
    save_outbound_message,
    get_snapshots_by_filters,
    get_available_periodes_suivi,
    create_archive_situation,
    get_archives_by_organization,
    initialize_new_situation,
    get_statistiques_impayes,
    get_historique_statistiques,
    comparer_statistiques,
    get_pending_messages,
    update_message_status,
    delete_message,
    get_sms_history,
    get_sms_history_count,
    get_available_dates_situation,
    delete_message_from_history,
    delete_messages_from_history_bulk,
    calculer_indicateurs_recouvrement,
    check_existing_active_import,
    deactivate_existing_import,
    get_dashboard_detaille,
)
from app.services.impayes_service import (
    valider_fichier_import,
    traiter_import_impayes,
    regenerer_sms_pour_date_situation,
)
from app.services.sms_service import send_sms
from app.core.deps import get_current_user, get_org_admin

router = APIRouter(
    prefix="/impayes",
    tags=["impayes"],
)


@router.post("/import/preview", response_model=ImportImpayesResponse)
async def preview_impayes_import(
    file: UploadFile = File(...),
    date_situation: str = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Prévisualise l'import d'un fichier Excel/CSV d'impayés sans sauvegarder
    """
    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    try:
        print(f"[DEBUG] ========== DÉBUT PRÉVISUALISATION IMPORT ==========")
        print(f"[DEBUG] Fichier reçu: {file.filename}")
        print(f"[DEBUG] Date situation: {date_situation}")
        
        # Utiliser le service unique pour le parsing
        from app.services.impayes_import_service import ImpayesImportService
        
        lignes, metadata = await ImpayesImportService.parse_file_to_lignes(
            file, date_situation
        )
        
        print(f"[DEBUG] Parsing terminé: {metadata['total_lignes']} lignes")
        print(f"[DEBUG] Type de fichier: {metadata['file_type']}")
        
        # Valider le fichier
        errors = await valider_fichier_import(lignes)
        
        print(f"[DEBUG] Nombre d'erreurs de validation: {len(errors)}")
        
        if errors:
            return ImportImpayesResponse(
                success=False,
                errors=errors,
                message=f"{len(errors)} erreur(s) détectée(s). Veuillez corriger le fichier.",
                snapshots_preview=[],
                messages_preview=[],
                stats_preview={}
            )
        
        # Utiliser la date de situation fournie ou celle de la première ligne
        if not date_situation and lignes:
            date_situation = lignes[0].dateSituation
        
        # Si toujours pas de date, utiliser la date du jour
        if not date_situation:
            from datetime import datetime
            date_situation = datetime.now().strftime("%Y-%m-%d")
        
        # Vérifier s'il existe déjà un import actif pour cette date
        existing_import = await check_existing_active_import(org_id, date_situation)
        
        if existing_import:
            return ImportImpayesResponse(
                success=False,
                errors=[],
                message=f"Un import existe déjà pour la date {date_situation} avec {existing_import['total_credits']} crédits et {existing_import['total_montant']:,.0f} FCFA.",
                snapshots_preview=[],
                messages_preview=[],
                stats_preview={},
                existing_import=existing_import
            )
        
        # Traiter l'import (sans sauvegarder)
        snapshots, messages = await traiter_import_impayes(
            lignes,
            date_situation,
            org_id,
            user_id
        )
        
        # Calculer les statistiques prévisionnelles
        total_montant = sum(s.montant_total_impaye for s in snapshots)
        total_credits = len(snapshots)
        candidats_restruct = sum(1 for s in snapshots if s.candidat_restructuration)
        
        # Répartitions
        repartition_tranches = {}
        repartition_segments = {}
        repartition_agences = {}
        
        for s in snapshots:
            # Par tranche
            tranche = s.bucket_retard
            repartition_tranches[tranche] = repartition_tranches.get(tranche, 0) + 1
            
            # Par segment
            segment = s.segment
            repartition_segments[segment] = repartition_segments.get(segment, 0) + 1
            
            # Par agence
            agence = s.agence
            repartition_agences[agence] = repartition_agences.get(agence, 0) + 1
        
        stats_preview = {
            "total_montant_impaye": total_montant,
            "total_credits": total_credits,
            "candidats_restructuration": candidats_restruct,
            "repartition_tranches": repartition_tranches,
            "repartition_segments": repartition_segments,
            "repartition_agences": repartition_agences,
        }
        
        # Convertir les snapshots et messages en dict pour la prévisualisation
        snapshots_preview = [s.dict() for s in snapshots]
        messages_preview = [m.dict() for m in messages]
        
        return ImportImpayesResponse(
            success=True,
            errors=[],
            message=f"Prévisualisation : {len(snapshots)} crédit(s) seront traités, {len(messages)} SMS seront générés.",
            snapshots_preview=snapshots_preview,
            messages_preview=messages_preview,
            stats_preview=stats_preview
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'import : {str(e)}"
        )


@router.post("/import/replace", response_model=ImportImpayesResponse)
async def replace_impayes_import(
    file: UploadFile = File(...),
    date_situation: str = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Remplace un import existant pour la même date de situation
    """
    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    try:
        # Utiliser la date de situation fournie ou celle de la première ligne
        if not date_situation:
            # Parser le fichier pour obtenir la date
            lignes, metadata = await ImpayesImportService.parse_file_to_lignes(file, date_situation)
            if lignes:
                date_situation = lignes[0].dateSituation
            else:
                from datetime import datetime
                date_situation = datetime.now().strftime("%Y-%m-%d")
        
        # Vérifier qu'il existe bien un import actif pour cette date
        existing_import = await check_existing_active_import(org_id, date_situation)
        if not existing_import:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Aucun import actif trouvé pour la date {date_situation}"
            )
        
        # Désactiver l'ancien import
        from app.models.impayes import deactivate_existing_import
        deactivated_count = await deactivate_existing_import(org_id, date_situation)
        
        # Parser le fichier avec la date_situation
        lignes, metadata = await ImpayesImportService.parse_file_to_lignes(file, date_situation)
        
        # Valider le fichier
        errors = await valider_fichier_import(lignes)
        
        if errors:
            # En cas d'erreur de validation, réactiver l'ancien import
            # TODO: Implémenter la réactivation si nécessaire
            return ImportImpayesResponse(
                success=False,
                errors=errors,
                message=f"{len(errors)} erreur(s) détectée(s). L'ancien import reste actif.",
                snapshots_preview=[],
                messages_preview=[],
                stats_preview={}
            )
        
        # Traiter le nouvel import
        snapshots, messages = await traiter_import_impayes(
            lignes,
            date_situation,
            org_id,
            user_id
        )
        
        # Sauvegarder les nouveaux snapshots (ils seront actifs par défaut)
        for snapshot in snapshots:
            await save_arrears_snapshot(snapshot)
        
        # Sauvegarder les nouveaux messages
        for message in messages:
            await save_outbound_message(message)
        
        return ImportImpayesResponse(
            success=True,
            errors=[],
            message=f"Import remplacé avec succès : {deactivated_count} ancien(s) crédit(s) désactivé(s), {len(snapshots)} nouveau(x) crédit(s) activé(s), {len(messages)} SMS généré(s).",
            snapshots_preview=[],
            messages_preview=[],
            stats_preview={}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du remplacement : {str(e)}"
        )


@router.post("/import/confirm", response_model=ImportImpayesResponse)
async def confirm_impayes_import(
    file: UploadFile = File(...),
    date_situation: str = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Confirme et sauvegarde l'import d'un fichier Excel/CSV d'impayés
    """
    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    try:
        print(f"[DEBUG] ========== DÉBUT CONFIRMATION IMPORT ==========")
        print(f"[DEBUG] Fichier reçu: {file.filename}")
        print(f"[DEBUG] Date situation: {date_situation}")
        
        # Utiliser le service unique pour le parsing
        from app.services.impayes_import_service import ImpayesImportService
        
        lignes, metadata = await ImpayesImportService.parse_file_to_lignes(
            file, date_situation
        )
        
        print(f"[DEBUG] Parsing terminé: {metadata['total_lignes']} lignes")
        print(f"[DEBUG] Type de fichier: {metadata['file_type']}")
        
        # Valider le fichier
        errors = await valider_fichier_import(lignes)
        
        print(f"[DEBUG] Nombre d'erreurs de validation: {len(errors)}")
        
        if errors:
            return ImportImpayesResponse(
                success=False,
                errors=errors,
                message=f"{len(errors)} erreur(s) détectée(s). Veuillez corriger le fichier.",
                snapshots_preview=[],
                messages_preview=[],
                stats_preview={}
            )
        
        # Utiliser la date de situation fournie ou celle de la première ligne
        if not date_situation and lignes:
            date_situation = lignes[0].dateSituation
        
        # Si toujours pas de date, utiliser la date du jour
        if not date_situation:
            from datetime import datetime
            date_situation = datetime.now().strftime("%Y-%m-%d")
        
        # Traiter l'import
        snapshots, messages = await traiter_import_impayes(
            lignes,
            date_situation,
            org_id,
            user_id
        )
        
        # Sauvegarder les snapshots
        for snapshot in snapshots:
            await save_arrears_snapshot(snapshot)
        
        # Sauvegarder les messages
        for message in messages:
            await save_outbound_message(message)
        
        return ImportImpayesResponse(
            success=True,
            errors=[],
            message=f"Import réussi : {len(snapshots)} crédit(s) traité(s), {len(messages)} SMS généré(s).",
            snapshots_preview=[],
            messages_preview=[],
            stats_preview={}
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'import : {str(e)}"
        )


@router.get("/snapshots")
async def get_snapshots(
    filtres: FiltresImpayes = Depends(),
    limit: int = 100,
    skip: int = 0,
    periode_suivi: Optional[str] = None,  # Nouveau paramètre optionnel
    current_user: dict = Depends(get_current_user),
):
    """Récupère les snapshots selon les filtres avec le total"""
    from app.models.impayes import count_snapshots_by_filters
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    # Si periode_suivi n'est pas fourni, utiliser la période courante
    if not periode_suivi:
        from app.models.impayes import get_available_periodes_suivi
        periodes_info = await get_available_periodes_suivi(org_id)
        periode_suivi = periodes_info.get("periode_courante")
    
    # Ajouter periode_suivi aux filtres
    if periode_suivi:
        filtres.periode_suivi = periode_suivi
    
    snapshots = await get_snapshots_by_filters(org_id, filtres, limit, skip)
    total = await count_snapshots_by_filters(org_id, filtres)
    
    return {
        "data": snapshots,
        "total": total,
        "periode_suivi": periode_suivi  # Retourner la période utilisée
    }


@router.get("/dates-situation")
async def get_dates_situation_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère la liste des dates de situation disponibles
    
    Les dates sont triées par ordre décroissant (plus récentes en premier).
    Chaque date correspond à un batch/fichier importé.
    """
    from app.services.impayes_snapshot_service import get_available_situation_dates
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    dates = await get_available_situation_dates(org_id)
    return {"dates": dates}


@router.get("/dates-situation/latest")
async def get_latest_situation_date_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """Récupère la date de situation la plus récente"""
    from app.services.impayes_snapshot_service import get_latest_situation_date
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    latest_date = await get_latest_situation_date(org_id)
    if not latest_date:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucune date de situation disponible.",
        )
    
    return {"date": latest_date}


@router.get("/dates-situation/{current_date}/previous")
async def get_previous_situation_date_endpoint(
    current_date: str,
    current_user: dict = Depends(get_current_user),
):
    """Récupère la date de situation précédente par rapport à une date donnée"""
    from app.services.impayes_snapshot_service import get_previous_situation_date
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    previous_date = await get_previous_situation_date(org_id, current_date)
    if not previous_date:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aucune date de situation précédente disponible pour {current_date}.",
        )
    
    return {"date": previous_date}


@router.get("/snapshots/compare")
async def compare_snapshots_endpoint(
    date_ancienne: str,
    date_recente: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Compare les snapshots entre deux dates de situation
    
    Cette comparaison détecte :
    - Les régularisations complètes (crédits présents à date_ancienne, absents à date_recente)
    - Les régularisations partielles (montant impayé qui diminue)
    - Les nouveaux crédits impayés
    - Les crédits stables
    - Les crédits qui se sont aggravés
    
    Args:
        date_ancienne: Date de situation ancienne (format YYYY-MM-DD)
        date_recente: Date de situation récente (format YYYY-MM-DD)
    """
    from app.services.impayes_snapshot_service import compare_snapshots
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    try:
        comparaison = await compare_snapshots(org_id, date_ancienne, date_recente)
        return comparaison
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la comparaison : {str(e)}"
        )


@router.get("/snapshots/by-date/{date_situation}")
async def get_snapshots_by_date_endpoint(
    date_situation: str,
    limit: int = 100,
    skip: int = 0,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère tous les snapshots pour une date de situation donnée
    
    Args:
        date_situation: Date de situation (format YYYY-MM-DD)
        limit: Nombre maximum de snapshots à récupérer
        skip: Nombre de snapshots à ignorer (pour pagination)
    """
    from app.services.impayes_snapshot_service import get_snapshots_by_date
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    snapshots = await get_snapshots_by_date(org_id, date_situation, limit=limit, skip=skip)
    return {"data": snapshots, "total": len(snapshots)}


@router.get("/snapshots/by-date/{date_situation}/summary")
async def get_snapshot_summary_endpoint(
    date_situation: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère un résumé d'un snapshot (batch) pour une date de situation donnée
    
    Le résumé inclut :
    - Le snapshot_id (identifiant du batch)
    - Le nombre de crédits
    - Les statistiques agrégées (montants, répartitions, etc.)
    """
    from app.services.impayes_snapshot_service import get_snapshot_summary
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    summary = await get_snapshot_summary(org_id, date_situation)
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aucun snapshot trouvé pour la date {date_situation}.",
        )
    
    return summary


@router.get("/statistiques", response_model=StatistiquesImpayes)
async def get_statistiques(
    date_situation: str = None,
    current_user: dict = Depends(get_current_user),
):
    """Récupère les statistiques des impayés"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    stats = await get_statistiques_impayes(org_id, date_situation)
    return stats


@router.get("/statistiques/historique", response_model=List[StatistiquesImpayes])
async def get_historique_statistiques_endpoint(
    limit: int = 12,
    current_user: dict = Depends(get_current_user),
):
    """Récupère l'historique des statistiques par date de situation"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    historique = await get_historique_statistiques(org_id, limit)
    return historique


@router.get("/statistiques/comparaison", response_model=ComparaisonStatistiques)
async def get_comparaison_statistiques(
    date_actuelle: str,
    date_precedente: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Compare les statistiques entre deux dates et calcule l'évolution"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    comparaison = await comparer_statistiques(org_id, date_actuelle, date_precedente)
    return comparaison


@router.get("/situations/comparaison")
async def get_comparaison_situations_snapshots(
    date_actuelle: str,
    date_precedente: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Compare deux situations de snapshots basée sur ref_credit (logique métier)
    
    Endpoint pour la comparaison métier qui analyse:
    - Régularisations totales (crédits disparus)
    - Régularisations partielles (baisse montant)
    - Dossiers aggravés (hausse montant)
    - Nouveaux impayés (crédits apparus)
    - Dossiers stables (montant identique)
    """
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    from app.models.impayes import comparer_situations_snapshots
    
    comparaison = await comparer_situations_snapshots(org_id, date_actuelle, date_precedente)
    return comparaison


@router.get("/messages/pending")
async def get_pending_messages_endpoint(
    limit: int = 100,
    skip: int = 0,
    current_user: dict = Depends(get_current_user),
):
    """Récupère les messages SMS en attente avec pagination"""
    from app.models.impayes import get_all_messages, count_all_messages
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    messages = await get_all_messages(org_id, status="PENDING", limit=limit, skip=skip)
    total = await count_all_messages(org_id, status="PENDING")
    
    return {
        "data": messages,
        "total": total
    }


@router.get("/messages/all")
async def get_all_messages_endpoint(
    status: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    current_user: dict = Depends(get_current_user),
):
    """Récupère tous les messages SMS avec filtres optionnels"""
    from app.models.impayes import get_all_messages, count_all_messages
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    messages = await get_all_messages(org_id, status, limit, skip)
    total = await count_all_messages(org_id, status)
    
    return {
        "data": messages,
        "total": total
    }


@router.post("/messages/send")
async def send_pending_messages(
    current_user: dict = Depends(get_current_user),
):
    """Envoie tous les messages SMS en attente (accessible à tous les utilisateurs authentifiés)"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    messages = await get_pending_messages(org_id)
    
    if not messages:
        return {
            "message": "Aucun SMS en attente à envoyer",
            "results": {"sent": 0, "failed": 0}
        }
    
    import asyncio
    
    results = {"sent": 0, "failed": 0}
    errors_detail = []
    
    # Regrouper les messages par numéro pour éviter les envois multiples au même numéro en même temps
    # et détecter les doublons
    messages_by_phone = {}
    for msg in messages:
        phone = msg.get("to", "")
        if phone not in messages_by_phone:
            messages_by_phone[phone] = []
        messages_by_phone[phone].append(msg)
    
    # Avertir si plusieurs SMS sont envoyés au même numéro
    for phone, msgs in messages_by_phone.items():
        if len(msgs) > 1:
            print(f"⚠️ ATTENTION: {len(msgs)} SMS seront envoyés au même numéro {phone}")
    
    last_phone = None
    for idx, message in enumerate(messages):
        try:
            # Vérifier que le numéro est valide
            if not message.get("to") or not message.get("to").startswith("227"):
                await update_message_status(
                    message["message_id"],
                    "FAILED",
                    error_message="Numéro de téléphone invalide"
                )
                results["failed"] += 1
                errors_detail.append(f"SMS {message['message_id'][:8]}: Numéro invalide")
                continue
            
            current_phone = message.get("to")
            
            # Ajouter un délai entre les envois pour éviter le rate limiting
            if idx > 0:
                if last_phone == current_phone:
                    # Si c'est le même numéro, attendre plus longtemps (2 secondes)
                    await asyncio.sleep(2.0)
                    print(f"⏳ Délai de 2s appliqué (même numéro: {current_phone})")
                else:
                    # Sinon, délai normal de 500ms
                    await asyncio.sleep(0.5)
            
            last_phone = current_phone
            
            # Tentative d'envoi avec retry en cas d'erreur réseau
            result = None
            max_retries = 2
            for retry in range(max_retries + 1):
                result = await send_sms(message["to"], message["body"])
                
                # Si succès ou erreur non-réseau, arrêter les retries
                if result.get("success") or ("Server disconnected" not in str(result.get("error", "")) and "timeout" not in str(result.get("error", "")).lower()):
                    break
                
                # Si c'est une erreur réseau et qu'il reste des tentatives, attendre avant de réessayer
                if retry < max_retries:
                    wait_time = (retry + 1) * 1  # 1s, 2s
                    print(f"⚠️ Erreur réseau pour SMS {message['message_id'][:8]}, nouvelle tentative dans {wait_time}s...")
                    await asyncio.sleep(wait_time)
            
            if result.get("success"):
                provider_id = None
                if isinstance(result.get("data"), dict):
                    provider_id = result.get("data", {}).get("message_id") or result.get("data", {}).get("id")
                elif isinstance(result.get("data"), str):
                    provider_id = result.get("data")
                
                await update_message_status(
                    message["message_id"],
                    "SENT",
                    provider_message_id=provider_id
                )
                results["sent"] += 1
            else:
                error_msg = result.get("error", "Erreur inconnue lors de l'envoi")
                await update_message_status(
                    message["message_id"],
                    "FAILED",
                    error_message=error_msg
                )
                results["failed"] += 1
                errors_detail.append(f"SMS {message['message_id'][:8]}: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            await update_message_status(
                message["message_id"],
                "FAILED",
                error_message=error_msg
            )
            results["failed"] += 1
            errors_detail.append(f"SMS {message['message_id'][:8]}: {error_msg}")
    
    response = {
        "message": f"{results['sent']} SMS envoyé(s), {results['failed']} échec(s)",
        "results": results
    }
    
    if errors_detail:
        response["errors_detail"] = errors_detail[:10]  # Limiter à 10 erreurs pour ne pas surcharger
    
    return response


@router.get("/candidats-restructuration")
async def get_candidats_restructuration(
    limit: int = 100,
    skip: int = 0,
    current_user: dict = Depends(get_current_user),
):
    """Récupère la liste des candidats à restructuration avec pagination"""
    from app.models.impayes import count_snapshots_by_filters
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    # Récupérer uniquement les candidats via le filtre avec pagination
    filtres = FiltresImpayes(candidat_restructuration=True)
    snapshots = await get_snapshots_by_filters(org_id, filtres, limit=limit, skip=skip)
    total = await count_snapshots_by_filters(org_id, filtres)
    
    return {
        "data": snapshots,
        "total": total
    }


@router.delete("/messages/{message_id}")
async def delete_message_endpoint(
    message_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Supprime un message SMS (ne supprime pas les SMS envoyés)"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    deleted = await delete_message(message_id, org_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de supprimer ce message. Les SMS envoyés sont conservés dans l'historique et ne peuvent pas être supprimés.",
        )
    
    return {"message": "Message supprimé avec succès"}


@router.post("/messages/bulk-delete")
async def delete_messages_bulk(
    message_ids: List[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Supprime plusieurs messages SMS en une fois (par IDs ou par statut)"""
    from app.models.impayes import delete_all_messages_by_status
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    # Si un statut est fourni, supprimer tous les messages de ce statut
    if status and status != "ALL":
        deleted_count = await delete_all_messages_by_status(org_id, status)
        status_label = {"PENDING": "en attente", "SENT": "envoyés", "FAILED": "échoués"}.get(status, status.lower())
        return {
            "message": f"{deleted_count} message(s) {status_label} supprimé(s)",
            "deleted": deleted_count,
            "total": deleted_count
        }
    
    # Si status est "ALL" ou vide et pas de message_ids, supprimer tous les messages non envoyés
    if (not status or status == "ALL") and (not message_ids or len(message_ids) == 0):
        deleted_count = await delete_all_messages_by_status(org_id, "ALL" if status == "ALL" else None)
        return {
            "message": f"{deleted_count} message(s) supprimé(s)",
            "deleted": deleted_count,
            "total": deleted_count
        }
    
    # Sinon, supprimer par IDs (comportement original)
    if not message_ids or len(message_ids) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucun message à supprimer.",
        )
    
    from app.models.impayes import delete_message
    deleted_count = 0
    for msg_id in message_ids:
        if await delete_message(msg_id, org_id):
            deleted_count += 1
    
    return {
        "message": f"{deleted_count} message(s) supprimé(s) sur {len(message_ids)}",
        "deleted": deleted_count,
        "total": len(message_ids)
    }


@router.get("/messages/history", response_model=List[OutboundMessagePublic])
async def get_sms_history_endpoint(
    limit: int = 100,
    skip: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Récupère l'historique des SMS envoyés"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    history = await get_sms_history(org_id, limit, skip, start_date, end_date)
    return history


@router.get("/messages/stats")
async def get_messages_stats_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """Récupère les statistiques des messages SMS (totaux par statut)"""
    from app.models.impayes import count_all_messages
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    pending = await count_all_messages(org_id, status="PENDING")
    sent = await count_all_messages(org_id, status="SENT")
    failed = await count_all_messages(org_id, status="FAILED")
    total = await count_all_messages(org_id, status=None)
    
    return {
        "pending": pending,
        "sent": sent,
        "failed": failed,
        "total": total
    }


@router.delete("/situation")
async def delete_situation_endpoint(
    date_situation: str,
    current_user: dict = Depends(get_current_user),
):
    """Supprime une situation importée (snapshots + SMS liés) pour une date_situation donnée"""
    from app.models.impayes import delete_situation_by_date_situation

    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )

    if not date_situation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La date_situation est requise.",
        )

    result = await delete_situation_by_date_situation(org_id, date_situation)
    deleted_total = (
        result.get("snapshots_deleted", 0)
        + result.get("messages_deleted", 0)
        + result.get("history_deleted", 0)
    )
    return {
        "message": f"Situation {date_situation} supprimée : {result.get('snapshots_deleted', 0)} snapshot(s), {result.get('messages_deleted', 0)} SMS en attente, {result.get('history_deleted', 0)} SMS historique.",
        "deleted_total": deleted_total,
        **result,
    }


@router.get("/messages/history/count")
async def get_sms_history_count_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """Compte le nombre total de SMS dans l'historique"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    count = await get_sms_history_count(org_id)
    return {"count": count}


@router.delete("/messages/history/{message_id}")
async def delete_message_from_history_endpoint(
    message_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Supprime un message SMS de l'historique"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    deleted = await delete_message_from_history(message_id, org_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message introuvable dans l'historique.",
        )
    
    return {"message": "Message supprimé de l'historique avec succès"}


@router.post("/messages/history/bulk-delete")
async def delete_messages_from_history_bulk_endpoint(
    message_ids: List[str],
    current_user: dict = Depends(get_current_user),
):
    """Supprime plusieurs messages SMS de l'historique"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    if not message_ids or len(message_ids) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucun message à supprimer.",
        )
    
    deleted_count = await delete_messages_from_history_bulk(message_ids, org_id)
    
    return {
        "message": f"{deleted_count} message(s) supprimé(s) de l'historique sur {len(message_ids)}",
        "deleted": deleted_count,
        "total": len(message_ids)
    }


@router.post("/messages/regenerate")
async def regenerate_sms(
    date_situation: str,
    current_user: dict = Depends(get_current_user),
):
    """Régénère les SMS pour une date de situation donnée à partir des snapshots existants"""
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    if not date_situation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La date de situation est requise.",
        )
    
    try:
        sms_generes, snapshots_traites = await regenerer_sms_pour_date_situation(org_id, date_situation)
        return {
            "message": f"Régénération terminée : {sms_generes} SMS généré(s) à partir de {snapshots_traites} snapshot(s)",
            "sms_generes": sms_generes,
            "snapshots_traites": snapshots_traites
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la régénération : {str(e)}"
        )


@router.post("/restructuration/action")
async def action_restructuration(
    action: ActionRestructuration,
    current_user: dict = Depends(get_org_admin),
):
    """
    Enregistre une action sur un candidat à restructuration
    
    Actions possibles:
    - "restructure": Le crédit a été restructuré
    - "refuse": La restructuration a été refusée
    - "douteux": Le crédit est classé comme douteux
    - "en_cours": La restructuration est en cours d'étude
    """
    from app.models.impayes import update_snapshot_restructuration, get_snapshots_by_filters
    from app.schemas.impayes import FiltresImpayes
    
    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    # Valider l'action
    actions_valides = ["restructure", "refuse", "douteux", "en_cours"]
    if action.action not in actions_valides:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Action invalide. Actions possibles: {', '.join(actions_valides)}"
        )
    
    # Vérifier que le snapshot existe et appartient à l'organisation
    snapshots = await get_snapshots_by_filters(org_id, FiltresImpayes(), limit=10000)
    snapshot_trouve = None
    for s in snapshots:
        if s.get("snapshot_id") == action.snapshot_id:
            snapshot_trouve = s
            break
    
    if not snapshot_trouve:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot avec l'ID {action.snapshot_id} introuvable."
        )
    
    # Mettre à jour le snapshot
    updated_snapshot = await update_snapshot_restructuration(
        snapshot_id=action.snapshot_id,
        organization_id=org_id,
        action=action.action,
        date_restructuration=action.date_restructuration,
        commentaire=action.commentaire,
        restructure_par=user_id
    )
    
    if not updated_snapshot:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la mise à jour du snapshot."
        )
    
    # Déterminer le message de réponse
    messages_action = {
        "restructure": "Restructuration enregistrée avec succès",
        "refuse": "Refus de restructuration enregistré",
        "douteux": "Crédit classé comme douteux",
        "en_cours": "Restructuration en cours d'étude"
    }
    
    return {
        "message": messages_action.get(action.action, "Action enregistrée"),
        "snapshot": updated_snapshot
    }


# ===================== Indicateurs de Performance =====================

@router.get("/indicateurs-recouvrement", response_model=IndicateursRecouvrement)
async def get_indicateurs_recouvrement(
    date_debut: Optional[str] = None,
    date_fin: Optional[str] = None,
    date_situation: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère les indicateurs de performance de recouvrement
    
    Indicateurs calculés:
    - Taux de recouvrement (montant récupéré / montant impayé)
    - Délai moyen de recouvrement (jours)
    - Taux de réponse aux SMS (après envoi)
    - Efficacité par tranche de retard
    - Taux de régularisation après SMS
    
    Note: Les régularisations sont détectées automatiquement en comparant les snapshots entre différentes dates de situation.
    Il suffit d'importer plusieurs fichiers d'impayés avec des dates de situation différentes pour que les indicateurs soient calculés automatiquement.
    """
    org_id = str(current_user.get("organization_id"))
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[INDICATEURS] Calcul des indicateurs pour org_id={org_id}, date_debut={date_debut}, date_fin={date_fin}, date_situation={date_situation}")
        
        indicateurs = await calculer_indicateurs_recouvrement(
            organization_id=org_id,
            date_debut=date_debut,
            date_fin=date_fin,
            date_situation=date_situation
        )
        
        logger.info(f"[INDICATEURS] Résultat: {indicateurs.get('nombre_regularisations', 0)} régularisations, taux_recouvrement={indicateurs.get('taux_recouvrement', 0)}%, montant_recupere={indicateurs.get('montant_total_recupere', 0)} FCFA")
        
        return indicateurs
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du calcul des indicateurs : {str(e)}"
        )


# ===================== Tableau de bord détaillé =====================

@router.get("/dashboard", response_model=DashboardDetaille)
async def get_dashboard_detaille_endpoint(
    date_situation: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère un tableau de bord très détaillé avec toutes les métriques et analyses
    
    Le dashboard inclut :
    - KPIs principaux (montants, crédits, ratios)
    - Évolution par rapport à la période précédente
    - Répartitions détaillées (tranches, segments, agences, produits, statuts)
    - Top 10 crédits (par montant, jours de retard, ratio)
    - Évolution temporelle (12 dernières dates)
    - Indicateurs de recouvrement
    - Statistiques SMS détaillées
    - Analyses approfondies (garanties, téléphones, pénalités, intérêts)
    - Alertes et risques
    - Concentrations (top 5 agences, segments, produits)
    - Qualité des données
    """
    org_id = str(current_user.get("organization_id"))
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    try:
        dashboard = await get_dashboard_detaille(org_id, date_situation)
        return dashboard
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du calcul du dashboard : {str(e)}"
        )


# ===================== Archivage et réinitialisation =====================

@router.post("/archive", response_model=dict)
async def create_archive_endpoint(
    archive_data: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Crée une archive des données actuelles d'impayés
    
    Cette opération :
    1. Copie tous les snapshots, messages et historique SMS dans des collections d'archives
    2. Crée une entrée de métadonnées avec les statistiques
    3. Les données actuelles restent intactes (elles ne sont pas supprimées)
    
    Body:
        - archive_name (optionnel): Nom descriptif de l'archive
        - archive_description (optionnel): Description de l'archive
        - include_snapshots (défaut: true): Inclure les snapshots
        - include_messages (défaut: true): Inclure les messages
        - include_sms_history (défaut: true): Inclure l'historique SMS
    """
    from app.services.impayes_archive_service import create_archive
    from app.schemas.impayes_archive import ArchiveCreate
    
    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    try:
        archive_create = ArchiveCreate(**archive_data)
        archive = await create_archive(org_id, user_id, archive_create)
        return {
            "success": True,
            "message": f"Archive créée avec succès: {archive.archive_id}",
            "archive": archive.model_dump() if hasattr(archive, 'model_dump') else archive.dict()
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création de l'archive : {str(e)}"
        )




@router.get("/archives/{archive_id}", response_model=dict)
async def get_archive_endpoint(
    archive_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère les métadonnées d'une archive spécifique
    """
    from app.services.impayes_archive_service import get_archive
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    archive = await get_archive(org_id, archive_id)
    if not archive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Archive {archive_id} non trouvée.",
        )
    
    return archive.model_dump() if hasattr(archive, 'model_dump') else archive.dict()


@router.get("/periodes")
async def get_periodes_suivi_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère les périodes de suivi disponibles et la période courante pour l'organisation.
    """
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Utilisateur non associé à une organisation",
        )
    
    try:
        result = await get_available_periodes_suivi(org_id)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des périodes: {str(e)}",
        )


@router.post("/archives/create")
async def create_archive_endpoint(
    request: CreateArchiveRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Crée une archive avec collections datées et vide les tables actuelles.
    Archive TOUS les snapshots et messages existants dans des collections datées.
    """
    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Utilisateur non associé à une organisation",
        )
    
    try:
        result = await create_archive_situation(
            organization_id=org_id,
            date_archive=request.date_archive,
            created_by=user_id,
            commentaire=request.commentaire
        )
        
        return ArchiveResponse(
            success=True,
            archive_id=result["archive_id"],
            message=f"Archive créée avec succès pour la date {request.date_archive} - {result['total_snapshots']} crédits et {result['total_messages']} messages",
            statistiques={
                "total_snapshots": result["total_snapshots"],
                "total_messages": result["total_messages"],
                "montant_total_impaye": result["montant_total_impaye"],
                "date_archive": result["date_archive"],
                "snapshots_collection": result["snapshots_collection"],
                "messages_collection": result["messages_collection"]
            },
            credits_archives=result["credits_archives"]
        )
        
    except ValueError as e:
        error_message = str(e)
        if "Aucune donnée à archiver" in error_message:
            error_message = "Aucune donnée à archiver. Veuillez d'abord importer des fichiers avant de créer une archive."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création de l'archive: {str(e)}",
        )


@router.get("/archives/{archive_id}/snapshots")
async def get_archive_snapshots_endpoint(
    archive_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère les snapshots d'une archive spécifique.
    """
    from app.core.db import get_database
    from app.models.impayes import (
        ARREARS_ARCHIVES_COLLECTION,
        ARREARS_ARCHIVED_SNAPSHOTS_COLLECTION,
    )
    
    org_id = str(current_user.get("organization_id"))
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Utilisateur non associé à une organisation",
        )
    
    try:
        # Récupérer les informations de l'archive
        db = get_database()
        archive = await db[ARREARS_ARCHIVES_COLLECTION].find_one({
            "archive_id": archive_id,
            "organization_id": ObjectId(org_id)
        })
        
        if not archive:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Archive non trouvée",
            )
        
        # Récupérer les snapshots de la collection d'archive
        # Nouveau modèle: collections fixes + archive_id => filtrer
        snapshots_query = {"organization_id": ObjectId(org_id)}
        if archive.get("snapshots_collection") == ARREARS_ARCHIVED_SNAPSHOTS_COLLECTION:
            snapshots_query["archive_id"] = archive_id

        snapshots = await db[archive["snapshots_collection"]].find(snapshots_query).to_list(length=10000)
        
        # Convertir tous les ObjectId en strings
        for snapshot in snapshots:
            if "_id" in snapshot:
                snapshot["_id"] = str(snapshot["_id"])
            if "organization_id" in snapshot and isinstance(snapshot["organization_id"], ObjectId):
                snapshot["organization_id"] = str(snapshot["organization_id"])
            if "created_by" in snapshot and isinstance(snapshot["created_by"], ObjectId):
                snapshot["created_by"] = str(snapshot["created_by"])
            if "created_at" in snapshot and hasattr(snapshot["created_at"], 'isoformat'):
                snapshot["created_at"] = snapshot["created_at"].isoformat()
        
        return {"snapshots": snapshots}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des snapshots: {str(e)}",
        )


@router.get("/archives/{archive_id}/messages")
async def get_archive_messages_endpoint(
    archive_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère les messages d'une archive spécifique.
    """
    from app.core.db import get_database
    from app.models.impayes import (
        ARREARS_ARCHIVES_COLLECTION,
        ARREARS_ARCHIVED_MESSAGES_COLLECTION,
    )
    
    org_id = str(current_user.get("organization_id"))
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Utilisateur non associé à une organisation",
        )
    
    try:
        # Récupérer les informations de l'archive
        db = get_database()
        archive = await db[ARREARS_ARCHIVES_COLLECTION].find_one({
            "archive_id": archive_id,
            "organization_id": ObjectId(org_id)
        })
        
        if not archive:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Archive non trouvée",
            )
        
        # Récupérer les messages de la collection d'archive
        # Nouveau modèle: collections fixes + archive_id => filtrer
        messages_query = {"organization_id": ObjectId(org_id)}
        if archive.get("messages_collection") == ARREARS_ARCHIVED_MESSAGES_COLLECTION:
            messages_query["archive_id"] = archive_id

        messages = await db[archive["messages_collection"]].find(messages_query).to_list(length=10000)
        
        # Convertir tous les ObjectId en strings
        for message in messages:
            if "_id" in message:
                message["_id"] = str(message["_id"])
            if "organization_id" in message and isinstance(message["organization_id"], ObjectId):
                message["organization_id"] = str(message["organization_id"])
            if "created_by" in message and isinstance(message["created_by"], ObjectId):
                message["created_by"] = str(message["created_by"])
            if "created_at" in message and hasattr(message["created_at"], 'isoformat'):
                message["created_at"] = message["created_at"].isoformat()
            if "sent_at" in message and hasattr(message["sent_at"], 'isoformat'):
                message["sent_at"] = message["sent_at"].isoformat()
        
        return {"messages": messages}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des messages: {str(e)}",
        )


@router.get("/archives")
async def get_archives_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère toutes les archives de l'organisation.
    """
    org_id = str(current_user.get("organization_id"))
    
    print(f"DEBUG: get_archives appelé avec org_id: {org_id}")  # Debug
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Utilisateur non associé à une organisation",
        )
    
    try:
        archives = await get_archives_by_organization(org_id)
        print(f"DEBUG: archives trouvées: {len(archives)}")  # Debug
        print(f"DEBUG: archives data: {archives}")  # Debug
        return {"archives": archives}
    except Exception as e:
        print(f"DEBUG: erreur dans get_archives: {str(e)}")  # Debug
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des archives: {str(e)}",
        )


@router.post("/situation/initialize")
async def initialize_new_situation_endpoint(
    new_periode_suivi: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Initialise une nouvelle situation (période vide).
    Prépare le système pour recevoir de nouvelles données.
    """
    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Utilisateur non associé à une organisation",
        )
    
    try:
        result = await initialize_new_situation(
            organization_id=org_id,
            new_periode_suivi=new_periode_suivi,
            created_by=user_id
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'initialisation: {str(e)}",
        )


@router.get("/archives/{archive_id}/snapshots", response_model=dict)
async def get_archived_snapshots_endpoint(
    archive_id: str,
    limit: int = 1000,
    skip: int = 0,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère les snapshots d'une archive
    
    Permet de consulter les données archivées sans les restaurer.
    """
    from app.services.impayes_archive_service import get_archived_snapshots, get_archive
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    # Vérifier que l'archive existe
    archive = await get_archive(org_id, archive_id)
    if not archive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Archive {archive_id} non trouvée.",
        )
    
    snapshots = await get_archived_snapshots(org_id, archive_id, limit=limit, skip=skip)
    
    return {
        "data": snapshots,
        "total": len(snapshots),
        "archive_id": archive_id
    }


@router.post("/archive/clear", response_model=dict)
async def clear_current_data_endpoint(
    confirm: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """
    Vide toutes les données actuelles d'impayés (snapshots, messages, historique SMS)
    
    ⚠️ ATTENTION: Cette opération est IRRÉVERSIBLE.
    Assurez-vous d'avoir archivé vos données avant d'utiliser cette fonction.
    
    Query parameter:
        - confirm (requis): Doit être True pour confirmer la suppression
    """
    from app.services.impayes_archive_service import clear_current_data
    
    org_id = str(current_user.get("organization_id"))
    user_id = str(current_user.get("id"))
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez confirmer la suppression en passant confirm=true",
        )
    
    try:
        result = await clear_current_data(org_id, user_id)
        return {
            "success": True,
            "message": "Données supprimées avec succès",
            "result": result
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression : {str(e)}"
        )


@router.post("/archives/{archive_id}/restore", response_model=dict)
async def restore_archive_endpoint(
    archive_id: str,
    restore_data: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Restaure une archive (copie les données archivées vers les collections actuelles)
    
    Body:
        - restore_snapshots (défaut: true): Restaurer les snapshots
        - restore_messages (défaut: true): Restaurer les messages
        - restore_sms_history (défaut: true): Restaurer l'historique SMS
        - clear_existing (défaut: false): Vider les données existantes avant restauration
    """
    from app.services.impayes_archive_service import restore_archive
    
    org_id = str(current_user.get("organization_id"))
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez être rattaché à une organisation.",
        )
    
    try:
        restore_snapshots = restore_data.get("restore_snapshots", True)
        restore_messages = restore_data.get("restore_messages", True)
        restore_sms_history = restore_data.get("restore_sms_history", True)
        clear_existing = restore_data.get("clear_existing", False)
        
        result = await restore_archive(
            org_id,
            archive_id,
            restore_snapshots=restore_snapshots,
            restore_messages=restore_messages,
            restore_sms_history=restore_sms_history,
            clear_existing=clear_existing
        )
        
        return {
            "success": True,
            "message": f"Archive {archive_id} restaurée avec succès",
            "result": result
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la restauration : {str(e)}"
        )

