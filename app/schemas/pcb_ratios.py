"""
Schémas pour la configuration et le calcul des ratios bancaires UEMOA
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class RatioConfigBase(BaseModel):
    """Configuration d'un ratio bancaire"""
    code: str = Field(..., description="Code unique du ratio (ex: 'SOLVABILITE_1', 'LIQUIDITE_1')")
    libelle: str = Field(..., description="Libellé du ratio")
    description: Optional[str] = Field(None, description="Description détaillée du ratio")
    formule: str = Field(..., description="Formule de calcul (ex: 'FONDS_PROPRES / ACTIF_PONDERE')")
    type_rapport: str = Field(..., description="Type de rapport requis (bilan_reglementaire, compte_resultat, les_deux)")
    categorie: str = Field(..., description="Catégorie du ratio (solvabilite, liquidite, rentabilite, efficacite, qualite_portefeuille)")
    seuil_min: Optional[float] = Field(None, description="Seuil minimum réglementaire (en pourcentage)")
    seuil_max: Optional[float] = Field(None, description="Seuil maximum réglementaire (en pourcentage)")
    unite: str = Field("%", description="Unité d'affichage (% ou nombre)")
    is_reglementaire: bool = Field(True, description="Indique si c'est un ratio réglementaire BCEAO")
    is_active: bool = Field(True, description="Indique si le ratio est activé pour le calcul")
    postes_requis: List[str] = Field([], description="Liste des codes de postes nécessaires pour le calcul")
    ordre_affichage: int = Field(1, description="Ordre d'affichage dans les rapports")


class RatioConfigCreate(RatioConfigBase):
    organization_id: str


class RatioConfigUpdate(BaseModel):
    libelle: Optional[str] = None
    description: Optional[str] = None
    formule: Optional[str] = None
    type_rapport: Optional[str] = None
    categorie: Optional[str] = None
    seuil_min: Optional[float] = None
    seuil_max: Optional[float] = None
    unite: Optional[str] = None
    is_reglementaire: Optional[bool] = None
    is_active: Optional[bool] = None
    postes_requis: Optional[List[str]] = None
    ordre_affichage: Optional[int] = None


class RatioConfigPublic(RatioConfigBase):
    id: str
    organization_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RatioCalculated(BaseModel):
    """Résultat du calcul d'un ratio"""
    code: str
    libelle: str
    valeur: float
    unite: str
    seuil_min: Optional[float] = None
    seuil_max: Optional[float] = None
    statut: str = Field(..., description="conforme, alerte, non_conforme")
    interpretation: Optional[str] = None


# Ratios par défaut pour les établissements de crédit UEMOA
RATIOS_DEFAUT_UEMOA = [
    # === RATIOS DE SOLVABILITÉ ===
    {
        "code": "SOLVABILITE_1",
        "libelle": "Ratio de solvabilité (Fonds propres / Actifs pondérés)",
        "description": "Ratio de fonds propres réglementaires selon Bâle III adapté UEMOA",
        "formule": "FONDS_PROPRES / ACTIF_PONDERE",
        "type_rapport": "bilan_reglementaire",
        "categorie": "solvabilite",
        "seuil_min": 8.0,  # Minimum réglementaire BCEAO
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["FONDS_PROPRES", "ACTIF_PONDERE"],
        "ordre_affichage": 1,
    },
    {
        "code": "SOLVABILITE_2",
        "libelle": "Ratio de capital Tier 1",
        "description": "Capital de base (Tier 1) / Actifs pondérés",
        "formule": "TIER1 / ACTIF_PONDERE",
        "type_rapport": "bilan_reglementaire",
        "categorie": "solvabilite",
        "seuil_min": 6.0,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["TIER1", "ACTIF_PONDERE"],
        "ordre_affichage": 2,
    },
    {
        "code": "SOLVABILITE_3",
        "libelle": "Ratio de fonds propres / Total bilan",
        "description": "Fonds propres / Total du bilan",
        "formule": "FONDS_PROPRES / TOTAL_BILAN",
        "type_rapport": "bilan_reglementaire",
        "categorie": "solvabilite",
        "seuil_min": 5.0,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["FONDS_PROPRES", "TOTAL_BILAN"],
        "ordre_affichage": 3,
    },
    
    # === RATIOS DE LIQUIDITÉ ===
    {
        "code": "LIQUIDITE_1",
        "libelle": "Ratio de liquidité à court terme",
        "description": "Actifs liquides / Passifs à court terme",
        "formule": "ACTIFS_LIQUIDES / PASSIFS_COURT_TERME",
        "type_rapport": "bilan_reglementaire",
        "categorie": "liquidite",
        "seuil_min": 100.0,  # Doit être >= 100%
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["ACTIFS_LIQUIDES", "PASSIFS_COURT_TERME"],
        "ordre_affichage": 4,
    },
    {
        "code": "LIQUIDITE_2",
        "libelle": "Ratio de liquidité immédiate",
        "description": "Disponibilités / Dépôts à vue",
        "formule": "DISPONIBILITES / DEPOTS_VUE",
        "type_rapport": "bilan_reglementaire",
        "categorie": "liquidite",
        "seuil_min": 20.0,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["DISPONIBILITES", "DEPOTS_VUE"],
        "ordre_affichage": 5,
    },
    {
        "code": "LIQUIDITE_3",
        "libelle": "Ratio de transformation",
        "description": "Crédits / Dépôts",
        "formule": "CREDITS / DEPOTS",
        "type_rapport": "bilan_reglementaire",
        "categorie": "liquidite",
        "seuil_min": None,
        "seuil_max": 75.0,  # Maximum recommandé
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["CREDITS", "DEPOTS"],
        "ordre_affichage": 6,
    },
    
    # === RATIOS DE RENTABILITÉ ===
    {
        "code": "RENTABILITE_1",
        "libelle": "ROE (Return on Equity) - Rentabilité des fonds propres",
        "description": "Résultat net / Fonds propres moyens",
        "formule": "RESULTAT_NET / FONDS_PROPRES",
        "type_rapport": "les_deux",
        "categorie": "rentabilite",
        "seuil_min": 10.0,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["RESULTAT_NET", "FONDS_PROPRES"],
        "ordre_affichage": 7,
    },
    {
        "code": "RENTABILITE_2",
        "libelle": "ROA (Return on Assets) - Rentabilité des actifs",
        "description": "Résultat net / Total actif moyen",
        "formule": "RESULTAT_NET / TOTAL_ACTIF",
        "type_rapport": "les_deux",
        "categorie": "rentabilite",
        "seuil_min": 1.0,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["RESULTAT_NET", "TOTAL_ACTIF"],
        "ordre_affichage": 8,
    },
    {
        "code": "RENTABILITE_3",
        "libelle": "Marge nette d'intérêt",
        "description": "(Produits d'intérêts - Charges d'intérêts) / Actifs productifs",
        "formule": "(PRODUITS_INTERETS - CHARGES_INTERETS) / ACTIFS_PRODUCTIFS",
        "type_rapport": "compte_resultat",
        "categorie": "rentabilite",
        "seuil_min": 2.0,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["PRODUITS_INTERETS", "CHARGES_INTERETS", "ACTIFS_PRODUCTIFS"],
        "ordre_affichage": 9,
    },
    {
        "code": "RENTABILITE_4",
        "libelle": "Marge nette bancaire",
        "description": "Résultat net / Produits nets bancaires",
        "formule": "RESULTAT_NET / PRODUITS_NETS_BANCAIRES",
        "type_rapport": "compte_resultat",
        "categorie": "rentabilite",
        "seuil_min": 15.0,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["RESULTAT_NET", "PRODUITS_NETS_BANCAIRES"],
        "ordre_affichage": 10,
    },
    
    # === RATIOS D'EFFICACITÉ ===
    {
        "code": "EFFICACITE_1",
        "libelle": "Ratio d'efficacité (Coûts / Revenus)",
        "description": "Charges d'exploitation / Produits d'exploitation",
        "formule": "CHARGES_EXPLOITATION / PRODUITS_EXPLOITATION",
        "type_rapport": "compte_resultat",
        "categorie": "efficacite",
        "seuil_min": None,
        "seuil_max": 70.0,  # Maximum recommandé
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["CHARGES_EXPLOITATION", "PRODUITS_EXPLOITATION"],
        "ordre_affichage": 11,
    },
    {
        "code": "EFFICACITE_2",
        "libelle": "Ratio de productivité",
        "description": "Produits nets bancaires / Effectif",
        "formule": "PRODUITS_NETS_BANCAIRES / EFFECTIF",
        "type_rapport": "compte_resultat",
        "categorie": "efficacite",
        "seuil_min": None,
        "seuil_max": None,
        "unite": "XOF",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["PRODUITS_NETS_BANCAIRES", "EFFECTIF"],
        "ordre_affichage": 12,
    },
    
    # === RATIOS DE QUALITÉ DU PORTEFEUILLE ===
    {
        "code": "QUALITE_1",
        "libelle": "Ratio de créances douteuses",
        "description": "Créances douteuses / Total crédits",
        "formule": "CREANCES_DOUTEUSES / TOTAL_CREDITS",
        "type_rapport": "bilan_reglementaire",
        "categorie": "qualite_portefeuille",
        "seuil_min": None,
        "seuil_max": 5.0,  # Maximum recommandé
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["CREANCES_DOUTEUSES", "TOTAL_CREDITS"],
        "ordre_affichage": 13,
    },
    {
        "code": "QUALITE_2",
        "libelle": "Ratio de couverture des créances douteuses",
        "description": "Provisions / Créances douteuses",
        "formule": "PROVISIONS / CREANCES_DOUTEUSES",
        "type_rapport": "bilan_reglementaire",
        "categorie": "qualite_portefeuille",
        "seuil_min": 100.0,  # Doit être >= 100%
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["PROVISIONS", "CREANCES_DOUTEUSES"],
        "ordre_affichage": 14,
    },
    {
        "code": "QUALITE_3",
        "libelle": "Ratio de concentration du portefeuille",
        "description": "Crédits aux 5 plus gros clients / Fonds propres",
        "formule": "CREDITS_5_CLIENTS / FONDS_PROPRES",
        "type_rapport": "bilan_reglementaire",
        "categorie": "qualite_portefeuille",
        "seuil_min": None,
        "seuil_max": 25.0,  # Maximum réglementaire
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["CREDITS_5_CLIENTS", "FONDS_PROPRES"],
        "ordre_affichage": 15,
    },
]
