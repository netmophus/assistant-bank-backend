"""
Routes API pour le système PCB UEMOA
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from typing import List, Optional
from datetime import datetime
from bson.errors import InvalidId
from app.models.pcb import (
    create_or_update_gl_account,
    list_gl_accounts,
    get_gl_account_by_code,
    get_latest_gl_soldes,
    get_available_solde_dates,
    delete_gl_accounts_by_date,
    delete_all_gl_accounts,
    create_poste_reglementaire,
    update_poste_reglementaire,
    list_postes_reglementaires,
    get_poste_by_id,
    delete_poste_reglementaire,
    list_poste_exercice_values,
    upsert_poste_exercice_value,
    create_report,
    list_reports,
    get_report_by_id,
    delete_report,
    list_ratio_variable_catalog,
    create_ratio_variable_catalog_item,
    update_ratio_variable_catalog_item,
    delete_ratio_variable_catalog_item,
    list_ratio_variable_values_public,
    upsert_ratio_variable_value,
)
from app.schemas.pcb import (
    GLCreate,
    GLPublic,
    PosteReglementaireCreate,
    PosteReglementaireUpdate,
    PosteReglementairePublic,
    PosteExerciceValueUpsert,
    PosteExerciceValuePublic,
    ReportCreate,
    ReportPublic,
    GLImportResult,
    RatioVariableCatalogCreate,
    RatioVariableCatalogUpdate,
    RatioVariableCatalogPublic,
    RatioVariableValueUpsert,
    RatioVariableValuePublic,
)
from app.services.pcb_import import import_gl_from_excel
from app.services.pcb_calcul import calculer_structure_rapport, calculer_ratios_bancaires
from app.services.pcb_ai_service import generer_interpretation_ia
from app.models.pcb_ratios import (
    init_default_ratios, list_ratios_config, get_ratio_config_by_code,
    create_ratio_config, update_ratio_config, delete_ratio_config, toggle_ratio_active
)
from app.schemas.pcb_ratios import RatioConfigCreate, RatioConfigUpdate, RatioConfigPublic
from app.models.ratio_gestion_line import (
    list_ratio_gestion_lines,
    create_ratio_gestion_line,
    update_ratio_gestion_line,
    delete_ratio_gestion_line,
    toggle_ratio_gestion_line_active,
)
from app.schemas.ratio_gestion_line import (
    RatioGestionLineCreate,
    RatioGestionLineUpdate,
    RatioGestionLinePublic,
)
from app.core.deps import get_current_user

router = APIRouter(prefix="/api/pcb", tags=["PCB UEMOA"])


# ========== COMPTES GL ==========

@router.post("/gl/import", response_model=GLImportResult)
async def import_gl_accounts(
    file: UploadFile = File(...),
    date_solde: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """
    Importe les comptes GL depuis un fichier Excel
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    if not file.filename or not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le fichier doit être au format Excel (.xlsx ou .xls)",
        )
    
    # Lire le contenu du fichier
    file_content = await file.read()
    
    # Parser la date si fournie
    date_solde_parsed = None
    if date_solde:
        try:
            date_temp = datetime.fromisoformat(date_solde.replace('Z', '+00:00'))
            # Normaliser à minuit pour éviter les problèmes de comparaison
            date_solde_parsed = datetime(date_temp.year, date_temp.month, date_temp.day)
        except:
            try:
                date_temp = datetime.strptime(date_solde, "%Y-%m-%d")
                date_solde_parsed = datetime(date_temp.year, date_temp.month, date_temp.day)
            except:
                pass
    
    # Utiliser la date fournie ou la date actuelle (normalisée à minuit)
    if not date_solde_parsed:
        today = datetime.utcnow()
        date_solde_parsed = datetime(today.year, today.month, today.day)
    
    # Importer
    result = await import_gl_from_excel(file_content, str(user_org_id), date_solde_parsed)
    
    return result


@router.get("/gl", response_model=List[GLPublic])
async def get_gl_accounts(
    classe: Optional[int] = None,
    code: Optional[str] = None,
    date_solde: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les comptes GL de l'organisation
    
    Paramètres:
    - classe: Filtrer par classe PCB (1-7, 9)
    - code: Filtrer par code GL (recherche partielle)
    - date_solde: Filtrer par date de solde (format ISO: YYYY-MM-DD ou ISO string)
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    filters = {}
    if classe:
        filters["classe"] = classe
    if code:
        filters["code"] = code
    if date_solde:
        # Parser la date depuis la query string
        try:
            # Essayer le format YYYY-MM-DD d'abord (plus simple)
            if len(date_solde) == 10 and date_solde.count('-') == 2:
                date_temp = datetime.strptime(date_solde, "%Y-%m-%d")
                # Normaliser à minuit pour la comparaison
                date_solde_parsed = datetime(date_temp.year, date_temp.month, date_temp.day)
            else:
                # Essayer le format ISO complet
                date_temp = datetime.fromisoformat(date_solde.replace('Z', '+00:00'))
                # Normaliser à minuit pour la comparaison
                date_solde_parsed = datetime(date_temp.year, date_temp.month, date_temp.day)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Format de date invalide: {date_solde}. Format attendu: YYYY-MM-DD ou ISO string. Erreur: {str(e)}"
            )
        filters["date_solde"] = date_solde_parsed
    
    accounts = await list_gl_accounts(str(user_org_id), filters)
    return accounts


@router.get("/gl/dates", response_model=List[str])
async def get_solde_dates(
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère toutes les dates de solde disponibles pour l'organisation
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    dates = await get_available_solde_dates(str(user_org_id))
    # Convertir en format ISO string pour le JSON
    return [date.isoformat() if isinstance(date, datetime) else str(date) for date in dates]


@router.delete("/gl/by-date/{date_solde}")
async def delete_gl_by_date(
    date_solde: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Supprime tous les comptes GL d'une organisation pour une date de solde donnée
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    # Parser la date
    try:
        date_solde_parsed = datetime.fromisoformat(date_solde.replace('Z', '+00:00'))
    except:
        try:
            date_solde_parsed = datetime.strptime(date_solde, "%Y-%m-%d")
        except:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Format de date invalide. Utilisez YYYY-MM-DD ou format ISO.",
            )
    
    deleted_count = await delete_gl_accounts_by_date(str(user_org_id), date_solde_parsed)
    
    return {
        "message": f"{deleted_count} compte(s) GL supprimé(s) pour la date {date_solde}",
        "deleted_count": deleted_count,
        "date_solde": date_solde
    }


@router.delete("/gl/all")
async def delete_all_gl_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """
    Supprime tous les comptes GL d'une organisation
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    deleted_count = await delete_all_gl_accounts(str(user_org_id))
    
    return {
        "message": f"{deleted_count} compte(s) GL supprimé(s)",
        "deleted_count": deleted_count
    }


@router.get("/gl/latest", response_model=List[GLPublic])
async def get_latest_gl_soldes_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère les soldes les plus récents pour chaque compte GL
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    accounts = await get_latest_gl_soldes(str(user_org_id))
    return accounts


@router.get("/gl/{code}", response_model=GLPublic)
async def get_gl_account(
    code: str,
    date_solde: Optional[datetime] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère un compte GL par son code
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    account = await get_gl_account_by_code(code, str(user_org_id), date_solde)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compte GL introuvable.",
        )
    
    return account


# ========== POSTES RÉGLEMENTAIRES ==========

@router.post("/postes", response_model=PosteReglementairePublic)
async def create_poste(
    poste: PosteReglementaireCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Crée un poste réglementaire
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    poste_data = poste.model_dump()
    new_poste = await create_poste_reglementaire(poste_data, str(user_org_id))
    return new_poste


@router.get("/postes", response_model=List[PosteReglementairePublic])
async def get_postes(
    type: Optional[str] = None,
    parent_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les postes réglementaires de l'organisation
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    filters = {}
    if type:
        filters["type"] = type
    if parent_id:
        filters["parent_id"] = parent_id
    
    postes = await list_postes_reglementaires(str(user_org_id), filters)
    return postes


# ========== VALEURS POSTE PAR EXERCICE (N-1 / BUDGET) ==========

@router.get("/postes/values", response_model=List[PosteExerciceValuePublic])
async def get_poste_values_by_exercice(
    exercice: str,
    poste_ids: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Liste les valeurs N-1/Budget pour un exercice (optionnellement filtrées par poste_ids séparés par virgule)"""
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    postes_list: Optional[List[str]] = None
    if poste_ids:
        postes_list = [p.strip() for p in poste_ids.split(",") if p.strip()]

    try:
        values = await list_poste_exercice_values(str(user_org_id), str(exercice), postes_list)
        return values
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/postes/{poste_id}/values", response_model=PosteExerciceValuePublic)
async def upsert_poste_values_by_exercice(
    poste_id: str,
    exercice: str,
    payload: PosteExerciceValueUpsert,
    current_user: dict = Depends(get_current_user),
):
    """Crée ou met à jour N-1/Budget pour un poste et un exercice."""
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    poste = await get_poste_by_id(poste_id, str(user_org_id))
    if not poste:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Poste introuvable.",
        )

    try:
        value = await upsert_poste_exercice_value(
            str(user_org_id),
            poste_id,
            str(exercice),
            payload.n_1,
            payload.budget,
        )
        return value
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/postes/{poste_id}", response_model=PosteReglementairePublic)
async def get_poste(
    poste_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère un poste par son ID
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    poste = await get_poste_by_id(poste_id, str(user_org_id))
    if not poste:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Poste introuvable.",
        )
    
    return poste


@router.put("/postes/{poste_id}", response_model=PosteReglementairePublic)
async def update_poste(
    poste_id: str,
    poste_update: PosteReglementaireUpdate,
    current_user: dict = Depends(get_current_user),
):
    """
    Met à jour un poste réglementaire
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    update_data = poste_update.model_dump(exclude_unset=True)
    try:
        updated_poste = await update_poste_reglementaire(
            poste_id, update_data, str(user_org_id)
        )
        return updated_poste
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/postes/{poste_id}")
async def delete_poste(
    poste_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Supprime (désactive) un poste réglementaire
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    success = await delete_poste_reglementaire(poste_id, str(user_org_id))
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Poste introuvable.",
        )
    
    return {"message": "Poste supprimé avec succès"}


# ========== RAPPORTS ==========

@router.post("/reports/generate", response_model=ReportPublic)
async def generate_report(
    type_rapport: str,
    date_cloture: datetime,
    section: Optional[str] = None,
    date_realisation: Optional[datetime] = None,
    date_debut: Optional[datetime] = None,
    include_ia: bool = True,
    modele_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Génère un rapport financier (bilan, hors bilan, compte de résultat)
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    user_id = current_user.get("id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    # Valider le type de rapport
    valid_types = ["bilan_reglementaire", "hors_bilan", "compte_resultat", "ratios_gestion", "ratios_bancaires"]
    if type_rapport not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Type de rapport invalide. Types valides: {', '.join(valid_types)}",
        )

    if section and type_rapport != "ratios_gestion":
        valid_sections_by_type = {
            "bilan_reglementaire": {"actif", "passif"},
            "compte_resultat": {"produits", "charges", "exploitation"},
            "hors_bilan": set(),
        }
        valid_sections = valid_sections_by_type.get(type_rapport, set())
        if section not in valid_sections:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Section invalide pour {type_rapport}. Valeurs valides: {', '.join(sorted(valid_sections))}",
            )
    
    # Rapport spécial: ratios de gestion
    if type_rapport == "ratios_gestion":
        from app.models.ratio_gestion_line import list_ratio_gestion_lines
        from app.models.pcb import list_postes_reglementaires
        from app.services.pcb_ratios_gestion_calcul import compute_ratios_gestion

        # On calcule une structure bilan complète pour obtenir les soldes des postes à date de clôture
        structure_cloture = await calculer_structure_rapport(
            "bilan_reglementaire", str(user_org_id), date_cloture, section=None
        )

        # Dictionnaires de valeurs par code
        values_cloture_by_code = {p.get("code"): float(p.get("solde_brut", p.get("solde", 0)) or 0) for p in structure_cloture.get("postes", []) if p.get("code")}

        # Charger N-1 / Réalisation (saisies manuelles) et les rattacher à chaque poste
        values = await list_poste_exercice_values(str(user_org_id), str(date_cloture.year))
        by_poste_id = {v.get("poste_id"): v for v in values}
        postes = await list_postes_reglementaires(str(user_org_id), {})
        values_n1_by_code = {}
        values_real_by_code = {}
        for p in postes:
            pid = p.get("id")
            code = p.get("code")
            if not code or not pid:
                continue
            v = by_poste_id.get(pid) or {}
            values_n1_by_code[code] = v.get("n_1")
            values_real_by_code[code] = v.get("budget")

        ratio_lines = await list_ratio_gestion_lines(str(user_org_id), {"is_active": True})
        ratios_gestion = compute_ratios_gestion(
            ratio_lines,
            values_cloture_by_code,
            values_n1_by_code,
            values_real_by_code,
        )

        structure = {
            "ratios_gestion": ratios_gestion,
            "meta": {
                "date_realisation": date_realisation,
                "date_cloture": date_cloture,
            },
        }

        interpretation_ia = ""
        if include_ia:
            try:
                # On passe les ratios sous forme de dict: code -> objet (compatible prompt IA)
                ratios_for_ai = {r.get("code") or "": r for r in (ratios_gestion or []) if r.get("code")}
                interpretation_ia = await generer_interpretation_ia(
                    type_rapport,
                    {"postes": structure_cloture.get("postes", []), "totaux": structure_cloture.get("totaux", {}), "meta": structure.get("meta")},
                    ratios_for_ai,
                    date_cloture.strftime("%Y-%m-%d") if date_cloture else None,
                )
            except Exception as e:
                print(f"Erreur lors de la génération de l'interprétation IA (ratios_gestion): {e}")
                msg = f"{e.__class__.__name__}: {str(e)}"
                interpretation_ia = f"⚠️ Analyse IA non disponible pour le moment. ({msg[:280]})"

        report_data = {
            "type": type_rapport,
            "section": None,
            "exercice": str(date_cloture.year),
            "date_cloture": date_cloture,
            "date_realisation": date_realisation,
            "date_debut": date_debut,
            "modele_id": modele_id,
            "structure": structure,
            "ratios_bancaires": {},
            "interpretation_ia": interpretation_ia,
            "statut": "generated",
        }

        report = await create_report(report_data, str(user_org_id), str(user_id))
        return report

    # Rapport spécial: ratios bancaires (réglementaires + personnalisés) issus de la configuration
    if type_rapport == "ratios_bancaires":
        # On calcule une structure bilan complète pour obtenir les soldes des postes à date de clôture
        structure_cloture = await calculer_structure_rapport(
            "bilan_reglementaire", str(user_org_id), date_cloture, section=None
        )

        structure = {
            "postes": structure_cloture.get("postes", []),
            "totaux": structure_cloture.get("totaux", {}),
            "meta": {
                "date_realisation": date_realisation,
                "date_cloture": date_cloture,
            },
        }

        ratios = await calculer_ratios_bancaires(structure, str(user_org_id), "ratios_bancaires", use_config=True)

        interpretation_ia = ""
        if include_ia:
            try:
                interpretation_ia = await generer_interpretation_ia(
                    type_rapport,
                    structure,
                    ratios,
                    date_cloture.strftime("%Y-%m-%d") if date_cloture else None,
                )
            except Exception as e:
                print(f"Erreur lors de la génération de l'interprétation IA (ratios_bancaires): {e}")
                msg = f"{e.__class__.__name__}: {str(e)}"
                interpretation_ia = f"⚠️ Analyse IA non disponible pour le moment. ({msg[:280]})"

        report_data = {
            "type": type_rapport,
            "section": None,
            "exercice": str(date_cloture.year),
            "date_cloture": date_cloture,
            "date_realisation": date_realisation,
            "date_debut": date_debut,
            "modele_id": modele_id,
            "structure": structure,
            "ratios_bancaires": ratios,
            "interpretation_ia": interpretation_ia,
            "statut": "generated",
        }

        report = await create_report(report_data, str(user_org_id), str(user_id))
        return report

    # Calculer la structure du rapport à date de clôture
    structure_cloture = await calculer_structure_rapport(
        type_rapport, str(user_org_id), date_cloture, section=section
    )

    # Récupérer N-1 (saisie manuelle) pour l'exercice
    values = await list_poste_exercice_values(str(user_org_id), str(date_cloture.year))
    n1_by_poste_id = {v.get("poste_id"): v.get("n_1") for v in values}

    # Récupérer la réalisation de référence (saisie manuelle, stockée dans 'budget')
    budget_by_poste_id = {v.get("poste_id"): v.get("budget") for v in values}

    def _enrich_tree(nodes: list) -> list:
        enriched = []
        for n in nodes or []:
            enfants = _enrich_tree(n.get("enfants") or [])

            poste_id = n.get("id")
            n1 = n1_by_poste_id.get(poste_id)
            if n1 is None and enfants:
                n1 = sum((c.get("n_1") or 0) for c in enfants)

            # Réalisation à date: valeur saisie dans N-1 / Réalisation (champ 'budget')
            real_date = budget_by_poste_id.get(poste_id)
            if real_date is None and enfants:
                real_date = sum((c.get("realisation_reference") or 0) for c in enfants)
            real_cloture = n.get("solde_brut", n.get("solde", 0))

            taux = None
            if real_date not in (None, 0):
                try:
                    taux = (real_cloture / real_date) * 100
                except Exception:
                    taux = None

            nn = dict(n)
            nn["enfants"] = enfants
            nn["n_1"] = n1
            nn["realisation_reference"] = real_date
            nn["realisation_cloture"] = real_cloture
            nn["taux_evaluation"] = taux
            enriched.append(nn)
        return enriched

    postes_hierarchiques = _enrich_tree(structure_cloture.get("postes_hierarchiques", []))

    def _flatten(nodes: list, niveau: int = 0) -> list:
        items = []
        for n in nodes or []:
            items.append({
                "id": n.get("id"),
                "code": n.get("code"),
                "libelle": n.get("libelle"),
                "type": n.get("type", ""),
                "solde": n.get("solde_brut", n.get("solde", 0)),
                "solde_brut": n.get("solde_brut", 0),
                "solde_affiche": n.get("solde_affiche", n.get("solde", 0)),
                "warning_signe": n.get("warning_signe", False),
                "gl_details": n.get("gl_details", []),
                "niveau": niveau,
                "parent_id": n.get("parent_id"),
                "source": n.get("source", "gl_codes"),
                "n_1": n.get("n_1"),
                "realisation_reference": n.get("realisation_reference"),
                "realisation_cloture": n.get("realisation_cloture"),
                "taux_evaluation": n.get("taux_evaluation"),
            })
            items.extend(_flatten(n.get("enfants") or [], niveau + 1))
        return items

    structure = {
        "postes": _flatten(postes_hierarchiques, 0),
        "postes_hierarchiques": postes_hierarchiques,
        "totaux": structure_cloture.get("totaux", {}),
        "meta": {
            "date_realisation": date_realisation,
            "date_cloture": date_cloture,
        }
    }

    # Calculer les ratios bancaires (utilise la configuration si disponible)
    ratios = await calculer_ratios_bancaires(structure, str(user_org_id), type_rapport, use_config=True)

    # Générer l'interprétation IA
    interpretation_ia = ""
    try:
        if include_ia:
            interpretation_ia = await generer_interpretation_ia(
                type_rapport,
                structure,
                ratios,
                date_cloture.strftime("%Y-%m-%d") if date_cloture else None
            )
    except Exception as e:
        print(f"Erreur lors de la génération de l'interprétation IA: {e}")
        msg = f"{e.__class__.__name__}: {str(e)}"
        interpretation_ia = f"⚠️ Analyse IA non disponible pour le moment. ({msg[:280]})"

    # Préparer les données du rapport
    report_data = {
        "type": type_rapport,
        "section": section,
        "exercice": str(date_cloture.year),
        "date_cloture": date_cloture,
        "date_realisation": date_realisation,
        "date_debut": date_debut,
        "modele_id": modele_id,
        "structure": structure,
        "ratios_bancaires": ratios,
        "interpretation_ia": interpretation_ia,
        "statut": "generated",
    }

    # Créer le rapport
    report = await create_report(report_data, str(user_org_id), str(user_id))
    return report


# ========== CONFIGURATION DES RATIOS ==========

@router.post("/ratios/init", response_model=List[RatioConfigPublic])
async def init_ratios(
    current_user: dict = Depends(get_current_user),
):
    """
    Initialise les ratios par défaut pour l'organisation
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    ratios = await init_default_ratios(str(user_org_id))
    return ratios


@router.get("/ratios", response_model=List[RatioConfigPublic])
async def get_ratios(
    categorie: Optional[str] = None,
    type_rapport: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les ratios configurés pour l'organisation
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    filters = {}
    if categorie:
        filters["categorie"] = categorie
    if type_rapport:
        filters["type_rapport"] = type_rapport
    if is_active is not None:
        filters["is_active"] = is_active
    
    ratios = await list_ratios_config(str(user_org_id), filters)
    return ratios


@router.get("/ratios/preview")
async def preview_ratios(
    type_rapport: str = Query(..., description="bilan_reglementaire, compte_resultat, les_deux"),
    date_cloture: str = Query(..., description="Date de clôture YYYY-MM-DD"),
    current_user: dict = Depends(get_current_user),
):
    """Prévisualise le calcul des ratios configurés à une date (sans générer de rapport)."""
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    try:
        d = datetime.strptime(date_cloture, "%Y-%m-%d")
        d = datetime(d.year, d.month, d.day)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format date_cloture invalide. Utilisez YYYY-MM-DD",
        )

    try:
        structure = await calculer_structure_rapport(type_rapport, str(user_org_id), date_solde=d, section=None)
        if isinstance(structure, dict):
            structure.setdefault("meta", {})
            structure["meta"]["date_cloture"] = d
        ratios_details = await calculer_ratios_bancaires(structure, str(user_org_id), type_rapport, use_config=True)
        ratios: dict = {}
        if isinstance(ratios_details, dict):
            for k, v in ratios_details.items():
                if isinstance(v, dict) and "valeur" in v:
                    ratios[k] = v.get("valeur")
                else:
                    ratios[k] = v
        return {
            "type_rapport": type_rapport,
            "date_cloture": d,
            "ratios": ratios,
            "ratios_details": ratios_details,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/ratios", response_model=RatioConfigPublic)
async def create_ratio(
    ratio_data: RatioConfigCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Crée une nouvelle configuration de ratio
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    ratio_data_dict = ratio_data.model_dump()
    ratio_data_dict["organization_id"] = str(user_org_id)
    
    try:
        ratio = await create_ratio_config(ratio_data_dict, str(user_org_id))
        return ratio
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.put("/ratios/{ratio_id}", response_model=RatioConfigPublic)
async def update_ratio(
    ratio_id: str,
    ratio_update: RatioConfigUpdate,
    current_user: dict = Depends(get_current_user),
):
    """
    Met à jour une configuration de ratio
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    update_data = ratio_update.model_dump(exclude_unset=True)
    
    try:
        ratio = await update_ratio_config(ratio_id, update_data, str(user_org_id))
        return ratio
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ratio_id invalide",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete("/ratios/{ratio_id}")
async def delete_ratio(
    ratio_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Supprime une configuration de ratio
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    try:
        success = await delete_ratio_config(ratio_id, str(user_org_id))
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ratio_id invalide",
        )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ratio introuvable.",
        )
    
    return {"message": "Ratio supprimé avec succès"}


@router.patch("/ratios/{ratio_id}/toggle", response_model=RatioConfigPublic)
async def toggle_ratio(
    ratio_id: str,
    is_active: bool = Query(..., description="État actif/inactif"),
    current_user: dict = Depends(get_current_user),
):
    """
    Active ou désactive un ratio
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    try:
        ratio = await toggle_ratio_active(ratio_id, str(user_org_id), is_active)
        return ratio
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ratio_id invalide",
        )


# ========== CATALOGUE VARIABLES RATIOS + VALEURS PAR DATE ==========


@router.get("/ratio-variables/catalog", response_model=List[RatioVariableCatalogPublic])
async def get_ratio_variable_catalog(
    include_inactive: bool = True,
    current_user: dict = Depends(get_current_user),
):
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    return await list_ratio_variable_catalog(str(user_org_id), include_inactive=include_inactive)


@router.post("/ratio-variables/catalog", response_model=RatioVariableCatalogPublic)
async def create_ratio_variable_catalog(
    payload: RatioVariableCatalogCreate,
    current_user: dict = Depends(get_current_user),
):
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    try:
        return await create_ratio_variable_catalog_item(payload.model_dump(), str(user_org_id))
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.put("/ratio-variables/catalog/{item_id}", response_model=RatioVariableCatalogPublic)
async def update_ratio_variable_catalog(
    item_id: str,
    payload: RatioVariableCatalogUpdate,
    current_user: dict = Depends(get_current_user),
):
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    try:
        return await update_ratio_variable_catalog_item(item_id, payload.model_dump(exclude_unset=True), str(user_org_id))
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete("/ratio-variables/catalog/{item_id}")
async def delete_ratio_variable_catalog(
    item_id: str,
    current_user: dict = Depends(get_current_user),
):
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    success = await delete_ratio_variable_catalog_item(item_id, str(user_org_id))
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variable introuvable.",
        )
    return {"message": "Variable supprimée avec succès"}


@router.get("/ratio-variables/values", response_model=List[RatioVariableValuePublic])
async def get_ratio_variable_values(
    date_solde: str = Query(..., description="Date de solde YYYY-MM-DD"),
    current_user: dict = Depends(get_current_user),
):
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    try:
        d = datetime.strptime(date_solde, "%Y-%m-%d")
        d = datetime(d.year, d.month, d.day)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format date_solde invalide. Utilisez YYYY-MM-DD",
        )

    return await list_ratio_variable_values_public(str(user_org_id), d)


@router.post("/ratio-variables/values", response_model=RatioVariableValuePublic)
async def upsert_ratio_variable_value_for_date(
    payload: RatioVariableValueUpsert,
    date_solde: str = Query(..., description="Date de solde YYYY-MM-DD"),
    current_user: dict = Depends(get_current_user),
):
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    try:
        d = datetime.strptime(date_solde, "%Y-%m-%d")
        d = datetime(d.year, d.month, d.day)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format date_solde invalide. Utilisez YYYY-MM-DD",
        )

    try:
        return await upsert_ratio_variable_value(str(user_org_id), d, payload.key, payload.value)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ========== RATIOS DE GESTION (PERSONNALISÉS) ==========


@router.get("/ratio-gestion-lines", response_model=List[RatioGestionLinePublic])
async def get_ratio_gestion_lines(
    is_active: Optional[bool] = None,
    current_user: dict = Depends(get_current_user),
):
    """Liste les ratios de gestion personnalisés"""
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    filters = {}
    if is_active is not None:
        filters["is_active"] = is_active

    return await list_ratio_gestion_lines(str(user_org_id), filters)


@router.post("/ratio-gestion-lines", response_model=RatioGestionLinePublic)
async def create_ratio_gestion(
    payload: RatioGestionLineCreate,
    current_user: dict = Depends(get_current_user),
):
    """Crée un ratio de gestion personnalisé"""
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    data = payload.model_dump()
    data["organization_id"] = str(user_org_id)

    try:
        return await create_ratio_gestion_line(data, str(user_org_id))
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.put("/ratio-gestion-lines/{ratio_id}", response_model=RatioGestionLinePublic)
async def update_ratio_gestion(
    ratio_id: str,
    payload: RatioGestionLineUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Met à jour un ratio de gestion personnalisé"""
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    try:
        return await update_ratio_gestion_line(ratio_id, update_data, str(user_org_id))
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete("/ratio-gestion-lines/{ratio_id}")
async def delete_ratio_gestion(
    ratio_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Supprime un ratio de gestion personnalisé"""
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    success = await delete_ratio_gestion_line(ratio_id, str(user_org_id))
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ratio de gestion introuvable.",
        )

    return {"message": "Ratio de gestion supprimé avec succès"}


@router.patch(
    "/ratio-gestion-lines/{ratio_id}/toggle",
    response_model=RatioGestionLinePublic,
)
async def toggle_ratio_gestion(
    ratio_id: str,
    is_active: bool = Query(..., description="État actif/inactif"),
    current_user: dict = Depends(get_current_user),
):
    """Active ou désactive un ratio de gestion personnalisé"""
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    return await toggle_ratio_gestion_line_active(ratio_id, str(user_org_id), is_active)


@router.get("/reports", response_model=List[ReportPublic])
async def get_reports(
    type: Optional[str] = None,
    exercice: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les rapports de l'organisation
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    filters = {}
    if type:
        filters["type"] = type
    if exercice:
        filters["exercice"] = exercice
    
    reports = await list_reports(str(user_org_id), filters)
    return reports


@router.get("/reports/{report_id}", response_model=ReportPublic)
async def get_report(
    report_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère un rapport par son ID
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    report = await get_report_by_id(report_id, str(user_org_id))
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rapport introuvable.",
        )
    
    return report


@router.delete("/reports/{report_id}")
async def delete_report_endpoint(
    report_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Supprime un rapport par son ID (scopé à l'organisation)."""
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )

    success = await delete_report(report_id, str(user_org_id))
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rapport introuvable.",
        )

    return {"success": True}


# ========== CALCULS ET TESTS ==========

@router.post("/postes/{poste_id}/calculer")
async def calculer_poste(
    poste_id: str,
    date_solde: Optional[str] = Query(None, description="Date de solde au format YYYY-MM-DD ou ISO string"),
    current_user: dict = Depends(get_current_user),
):
    """
    Calcule le solde d'un poste réglementaire
    
    Retourne:
    {
        "solde_brut": float,  # Solde brut (peut être négatif)
        "solde_affiche": float,  # Solde affiché (toujours positif)
        "warning_signe": bool,  # True si solde_brut < 0
        "gl_details": List[dict]  # Détails des GL contribuant
    }
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role not in ["admin", "user"] or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs authentifiés.",
        )
    
    poste = await get_poste_by_id(poste_id, str(user_org_id))
    if not poste:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Poste introuvable.",
        )
    
    # Parser la date_solde si fournie
    date_solde_parsed = None
    if date_solde:
        try:
            # Essayer le format YYYY-MM-DD d'abord
            if len(date_solde) == 10 and date_solde.count('-') == 2:
                date_temp = datetime.strptime(date_solde, "%Y-%m-%d")
                date_solde_parsed = datetime(date_temp.year, date_temp.month, date_temp.day)
            else:
                # Essayer le format ISO complet
                date_temp = datetime.fromisoformat(date_solde.replace('Z', '+00:00'))
                date_solde_parsed = datetime(date_temp.year, date_temp.month, date_temp.day)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Format de date invalide: {date_solde}. Format attendu: YYYY-MM-DD ou ISO string. Erreur: {str(e)}"
            )
    
    from app.services.pcb_calcul import calculer_poste_hierarchique
    result = await calculer_poste_hierarchique(poste_id, str(user_org_id), date_solde_parsed)
    
    return result

