"""
Service de calcul des ratios bancaires basé sur la configuration
"""
from typing import Dict, List, Optional

from app.services.pcb_ratios_gestion_calcul import eval_formula_with_codes
from app.models.pcb_ratios import list_ratios_config
from app.models.pcb import list_postes_reglementaires


async def calculer_ratios_configures(
    structure: Dict,
    organization_id: str,
    type_rapport: str
) -> Dict:
    """
    Calcule les ratios bancaires configurés pour une organisation
    """
    # Récupérer les ratios configurés et actifs
    filters = {
        "is_active": True,
    }
    
    # Filtrer par type de rapport
    if type_rapport == "ratios_bancaires":
        filters["type_rapport"] = {"$in": ["bilan_reglementaire", "compte_resultat", "les_deux"]}
    elif type_rapport == "bilan_reglementaire":
        filters["type_rapport"] = {"$in": ["bilan_reglementaire", "les_deux"]}
    elif type_rapport == "compte_resultat":
        filters["type_rapport"] = {"$in": ["compte_resultat", "les_deux"]}
    else:
        filters["type_rapport"] = {"$in": [type_rapport, "les_deux"]}
    
    ratios_config = await list_ratios_config(organization_id, filters)

    # Si des ratios "les_deux" sont utilisés, on essaye de compléter l'environnement
    # avec l'autre état (bilan <-> compte résultat) à la date de clôture du rapport.
    needs_both = any(r.get("type_rapport") == "les_deux" for r in ratios_config)

    # Créer un dictionnaire des postes et totaux pour accès rapide
    postes_dict: Dict[str, float] = {
        p.get("code"): float(p.get("solde_brut", p.get("solde", 0)) or 0)
        for p in structure.get("postes", [])
        if p.get("code")
    }
    totaux = structure.get("totaux", {})

    # Date du rapport (sert pour le fallback strict des variables de ratios)
    date_cloture = None
    try:
        date_cloture = (structure.get("meta") or {}).get("date_cloture")
    except Exception:
        date_cloture = None

    if needs_both and type_rapport in {"bilan_reglementaire", "compte_resultat"}:
        if date_cloture:
            other_type = "compte_resultat" if type_rapport == "bilan_reglementaire" else "bilan_reglementaire"
            try:
                from app.services.pcb_calcul import calculer_structure_rapport

                other_structure = await calculer_structure_rapport(
                    other_type,
                    organization_id,
                    date_solde=date_cloture,
                    section=None,
                )
                other_postes = {
                    p.get("code"): float(p.get("solde_brut", p.get("solde", 0)) or 0)
                    for p in other_structure.get("postes", [])
                    if p.get("code")
                }
                postes_dict.update(other_postes)

                other_totaux = other_structure.get("totaux", {})
                if isinstance(other_totaux, dict):
                    for k, v in other_totaux.items():
                        if k not in totaux:
                            totaux[k] = v
            except Exception as e:
                print(f"Erreur lors du chargement de la structure {other_type} pour ratios 'les_deux': {e}")
    
    # Récupérer les postes réglementaires pour mapper les codes
    all_postes = await list_postes_reglementaires(organization_id, {})
    postes_code_map = {p["code"]: p for p in all_postes}
    
    # Ajouter les totaux comme variables utilisables dans les formules
    # (ex: TOTAL_ACTIF, TOTAL_CHARGES, etc.)
    for k, v in (totaux or {}).items():
        if isinstance(k, str):
            try:
                postes_dict[k] = float(v or 0)
            except Exception:
                postes_dict[k] = 0.0

    # Fallback strict: si une variable n'est pas présente dans les postes/totaux,
    # et qu'une valeur manuelle existe pour (organization_id, date_cloture, key),
    # on l'injecte dans l'environnement.
    if date_cloture:
        try:
            from app.models.pcb import get_ratio_variable_values_for_date

            fallback_values = await get_ratio_variable_values_for_date(organization_id, date_cloture)
            for k, v in (fallback_values or {}).items():
                if k and k not in postes_dict:
                    postes_dict[k] = float(v or 0.0)
        except Exception as e:
            print(f"Erreur lors du chargement des variables fallback de ratios: {e}")

    aliases = {
        "FOND_PROPRE": "FONDS_PROPRES",
    }
    for src, dst in aliases.items():
        if src in postes_dict and dst not in postes_dict:
            postes_dict[dst] = float(postes_dict.get(src) or 0.0)
        if dst in postes_dict and src not in postes_dict:
            postes_dict[src] = float(postes_dict.get(dst) or 0.0)

    # Calculer chaque ratio configuré
    ratios_calcules = {}
    
    for ratio_config in ratios_config:
        code_ratio = ratio_config["code"]
        formule = ratio_config["formule"]
        
        try:
            valeur = eval_formula_with_codes(formule, postes_dict)
            
            if valeur is not None:
                # Déterminer le statut selon les seuils
                statut = _determiner_statut_ratio(valeur, ratio_config)
                
                ratios_calcules[code_ratio] = {
                    "valeur": valeur,
                    "libelle": ratio_config["libelle"],
                    "unite": ratio_config["unite"],
                    "seuil_min": ratio_config.get("seuil_min"),
                    "seuil_max": ratio_config.get("seuil_max"),
                    "statut": statut,
                    "categorie": ratio_config["categorie"],
                    "is_reglementaire": ratio_config["is_reglementaire"],
                }
        except Exception as e:
            # En cas d'erreur, on ignore ce ratio
            print(f"Erreur lors du calcul du ratio {code_ratio}: {e}")
            continue
    
    return ratios_calcules


def _determiner_statut_ratio(valeur: float, ratio_config: Dict) -> str:
    """
    Détermine le statut d'un ratio selon ses seuils
    """
    seuil_min = ratio_config.get("seuil_min")
    seuil_max = ratio_config.get("seuil_max")
    
    if seuil_min is not None and valeur < seuil_min:
        return "non_conforme"
    
    if seuil_max is not None and valeur > seuil_max:
        return "non_conforme"
    
    # Zone d'alerte (80% du seuil minimum ou 120% du seuil maximum)
    if seuil_min is not None:
        seuil_alerte = seuil_min * 0.8
        if valeur < seuil_alerte:
            return "alerte"
    
    if seuil_max is not None:
        seuil_alerte = seuil_max * 1.2
        if valeur > seuil_alerte:
            return "alerte"
    
    return "conforme"
