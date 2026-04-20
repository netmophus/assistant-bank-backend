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
    # ═══════════════════════════════════════════════════════════════════
    # CATÉGORIE A — NORMES DE SOLVABILITÉ (Titre III, §100-109)
    # ═══════════════════════════════════════════════════════════════════
    {
        "code": "RA001",
        "libelle": "Ratio de fonds propres CET1",
        "description": "Fonds propres de base durs (CET1) rapportés aux actifs pondérés des risques. Ref: Titre III §100. FODEP EP02. Norme minimale 7,5 % (cible 10 % avec coussin de conservation de 2,5 %).",
        "formule": "CET1 / APR",
        "type_rapport": "bilan_reglementaire",
        "categorie": "solvabilite",
        "seuil_min": 7.5,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["CET1", "APR"],
        "ordre_affichage": 1,
    },
    {
        "code": "RA002",
        "libelle": "Ratio de fonds propres de base Tier 1",
        "description": "Fonds propres de base (CET1 + AT1) rapportés aux APR. Ref: Titre III §100. FODEP EP02. Norme minimale 8,5 % (cible 11 % avec coussin).",
        "formule": "T1 / APR",
        "type_rapport": "bilan_reglementaire",
        "categorie": "solvabilite",
        "seuil_min": 8.5,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["T1", "APR"],
        "ordre_affichage": 2,
    },
    {
        "code": "RA003",
        "libelle": "Ratio de solvabilité total",
        "description": "Fonds propres effectifs (T1 + T2) rapportés aux APR. Ref: Titre III §100. FODEP EP02. Norme minimale 11,5 % (cible 14 % avec coussin de conservation).",
        "formule": "FPE / APR",
        "type_rapport": "bilan_reglementaire",
        "categorie": "solvabilite",
        "seuil_min": 11.5,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["FPE", "APR"],
        "ordre_affichage": 3,
    },

    # ═══════════════════════════════════════════════════════════════════
    # CATÉGORIE B — DIVISION DES RISQUES (Titre VII, §460-474)
    # ═══════════════════════════════════════════════════════════════════
    {
        "code": "RA004",
        "libelle": "Norme de division des risques",
        "description": "Plus grande exposition sur un seul bénéficiaire (ou groupe lié) rapportée aux fonds propres effectifs. Ref: Titre VII §460-474. FODEP EP29. Un grand risque doit être déclaré dès qu'il dépasse 10 % des FPE.",
        "formule": "MAX(EXPOSITION_i) / FPE",
        "type_rapport": "bilan_reglementaire",
        "categorie": "division_risques",
        "seuil_min": None,
        "seuil_max": 25.0,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["PLUS_GRANDE_EXPOSITION", "FPE"],
        "ordre_affichage": 4,
    },

    # ═══════════════════════════════════════════════════════════════════
    # CATÉGORIE C — RATIO DE LEVIER (Titre VIII, §475-483)
    # ═══════════════════════════════════════════════════════════════════
    {
        "code": "RA005",
        "libelle": "Ratio de levier",
        "description": "Fonds propres de base (T1) rapportés à la mesure de l'exposition totale (bilan + hors-bilan, sans pondération). Ref: Titre VIII §475-483. FODEP EP33.",
        "formule": "T1 / EXPOSITION_TOTALE_LEVIER",
        "type_rapport": "bilan_reglementaire",
        "categorie": "levier",
        "seuil_min": 3.0,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["T1", "EXPOSITION_TOTALE_LEVIER"],
        "ordre_affichage": 5,
    },

    # ═══════════════════════════════════════════════════════════════════
    # CATÉGORIE D — AUTRES NORMES PRUDENTIELLES (Titre IX, §484-490)
    # ═══════════════════════════════════════════════════════════════════
    {
        "code": "RA006",
        "libelle": "Limite individuelle de participation (entreprises non financières)",
        "description": "Participation dans une entreprise non financière rapportée aux FPE. Ref: Titre IX §484. FODEP EP35.",
        "formule": "PARTICIPATION_INDIV_NON_FINANCIERE / FPE",
        "type_rapport": "bilan_reglementaire",
        "categorie": "participations",
        "seuil_min": None,
        "seuil_max": 25.0,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["PARTICIPATION_INDIV_NON_FINANCIERE", "FPE"],
        "ordre_affichage": 6,
    },
    {
        "code": "RA007",
        "libelle": "Limite individuelle de participation (entreprises financières hors périmètre)",
        "description": "Participation dans une entreprise financière hors périmètre de consolidation rapportée aux FPE. Ref: Titre IX §484. FODEP EP35.",
        "formule": "PARTICIPATION_INDIV_FINANCIERE / FPE",
        "type_rapport": "bilan_reglementaire",
        "categorie": "participations",
        "seuil_min": None,
        "seuil_max": 15.0,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["PARTICIPATION_INDIV_FINANCIERE", "FPE"],
        "ordre_affichage": 7,
    },
    {
        "code": "RA008",
        "libelle": "Limite globale des participations (entreprises non financières)",
        "description": "Total des participations dans les entreprises non financières rapporté aux FPE. Ref: Titre IX §484. FODEP EP35.",
        "formule": "TOTAL_PARTICIPATIONS_NON_FINANCIERES / FPE",
        "type_rapport": "bilan_reglementaire",
        "categorie": "participations",
        "seuil_min": None,
        "seuil_max": 60.0,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["TOTAL_PARTICIPATIONS_NON_FINANCIERES", "FPE"],
        "ordre_affichage": 8,
    },
    {
        "code": "RA009",
        "libelle": "Limite des immobilisations hors exploitation",
        "description": "Valeur nette des immobilisations hors exploitation rapportée aux FPE. Ref: Titre IX §485-488. FODEP EP36. L'excédent est déduit du CET1.",
        "formule": "IMMOBILISATIONS_HORS_EXPLOITATION / FPE",
        "type_rapport": "bilan_reglementaire",
        "categorie": "immobilisations",
        "seuil_min": None,
        "seuil_max": 15.0,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["IMMOBILISATIONS_HORS_EXPLOITATION", "FPE"],
        "ordre_affichage": 9,
    },
    {
        "code": "RA010",
        "libelle": "Limite totale des immobilisations et participations",
        "description": "Ensemble des immobilisations (corporelles + incorporelles) et participations rapporté aux FPE. Ref: Titre IX §489. FODEP EP37. L'excédent est déduit du CET1.",
        "formule": "(IMMOBILISATIONS_TOTALES + PARTICIPATIONS) / FPE",
        "type_rapport": "bilan_reglementaire",
        "categorie": "immobilisations",
        "seuil_min": None,
        "seuil_max": 100.0,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["IMMOBILISATIONS_TOTALES", "PARTICIPATIONS", "FPE"],
        "ordre_affichage": 10,
    },
    {
        "code": "RA011",
        "libelle": "Limite des prêts aux parties liées",
        "description": "Encours des prêts aux actionnaires (≥ 10 %), dirigeants, personnel et parties liées rapporté aux FPE. Ref: Titre IX §490. FODEP EP38. L'excédent est déduit du CET1.",
        "formule": "PRETS_PARTIES_LIEES / FPE",
        "type_rapport": "bilan_reglementaire",
        "categorie": "parties_liees",
        "seuil_min": None,
        "seuil_max": 20.0,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["PRETS_PARTIES_LIEES", "FPE"],
        "ordre_affichage": 11,
    },

    # ═══════════════════════════════════════════════════════════════════
    # CATÉGORIE E — LIQUIDITÉ (Titre XIII, §496-520)
    # ═══════════════════════════════════════════════════════════════════
    {
        "code": "LCR",
        "libelle": "Ratio de liquidité à court terme (LCR)",
        "description": "Stock d'actifs liquides de haute qualité (HQLA) rapporté aux sorties nettes de trésorerie sur 30 jours. Ref: Titre XIII §496-509. FODEP EP34.",
        "formule": "HQLA / SORTIES_NETTES_30J",
        "type_rapport": "bilan_reglementaire",
        "categorie": "liquidite",
        "seuil_min": 100.0,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["HQLA", "SORTIES_NETTES_30J"],
        "ordre_affichage": 12,
    },
    {
        "code": "NSFR",
        "libelle": "Ratio de liquidité structurelle (NSFR)",
        "description": "Financements stables disponibles (ASF) rapportés aux financements stables exigés (RSF) sur un horizon 1 an. Ref: Titre XIII §510-520. FODEP EP34.",
        "formule": "ASF / RSF",
        "type_rapport": "bilan_reglementaire",
        "categorie": "liquidite",
        "seuil_min": 100.0,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": True,
        "is_active": True,
        "postes_requis": ["ASF", "RSF"],
        "ordre_affichage": 13,
    },

    # ═══════════════════════════════════════════════════════════════════
    # RATIOS DE GESTION (non prudentiels mais surveillés par la CB-UMOA)
    # ═══════════════════════════════════════════════════════════════════
    {
        "code": "GEST_COEF_EXPLOITATION",
        "libelle": "Coefficient d'exploitation",
        "description": "Charges générales d'exploitation rapportées au PNB. Pas de norme BCEAO mais surveillé par la CB-UMOA (alerte > 65-70 %).",
        "formule": "CHARGES_GENERALES_EXPLOITATION / PNB",
        "type_rapport": "compte_resultat",
        "categorie": "efficacite",
        "seuil_min": None,
        "seuil_max": 65.0,
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["CHARGES_GENERALES_EXPLOITATION", "PNB"],
        "ordre_affichage": 20,
    },
    {
        "code": "GEST_TAUX_BRUT_DEGRADATION",
        "libelle": "Taux brut de dégradation du portefeuille",
        "description": "Créances en souffrance brutes rapportées au total des crédits bruts. Seuil d'alerte usuel > 5 %.",
        "formule": "CREANCES_SOUFFRANCE_BRUTES / TOTAL_CREDITS_BRUTS",
        "type_rapport": "bilan_reglementaire",
        "categorie": "qualite_portefeuille",
        "seuil_min": None,
        "seuil_max": 5.0,
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["CREANCES_SOUFFRANCE_BRUTES", "TOTAL_CREDITS_BRUTS"],
        "ordre_affichage": 21,
    },
    {
        "code": "GEST_TAUX_NET_DEGRADATION",
        "libelle": "Taux net de dégradation du portefeuille",
        "description": "Créances en souffrance nettes de provisions rapportées aux crédits nets.",
        "formule": "CREANCES_SOUFFRANCE_NETTES / TOTAL_CREDITS_NETS",
        "type_rapport": "bilan_reglementaire",
        "categorie": "qualite_portefeuille",
        "seuil_min": None,
        "seuil_max": 3.0,
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["CREANCES_SOUFFRANCE_NETTES", "TOTAL_CREDITS_NETS"],
        "ordre_affichage": 22,
    },
    {
        "code": "GEST_TAUX_PROVISIONNEMENT",
        "libelle": "Taux de provisionnement des CDL",
        "description": "Provisions constituées sur créances douteuses rapportées aux CDL brutes. Cible usuelle > 60 %.",
        "formule": "PROVISIONS_CDL / CREANCES_SOUFFRANCE_BRUTES",
        "type_rapport": "bilan_reglementaire",
        "categorie": "qualite_portefeuille",
        "seuil_min": 60.0,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["PROVISIONS_CDL", "CREANCES_SOUFFRANCE_BRUTES"],
        "ordre_affichage": 23,
    },
    {
        "code": "GEST_ROA",
        "libelle": "Rentabilité des actifs (ROA)",
        "description": "Résultat net rapporté au total actif moyen. Cible usuelle > 1 %.",
        "formule": "RESULTAT_NET / TOTAL_ACTIF_MOYEN",
        "type_rapport": "les_deux",
        "categorie": "rentabilite",
        "seuil_min": 1.0,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["RESULTAT_NET", "TOTAL_ACTIF_MOYEN"],
        "ordre_affichage": 24,
    },
    {
        "code": "GEST_ROE",
        "libelle": "Rentabilité des fonds propres (ROE)",
        "description": "Résultat net rapporté aux fonds propres moyens. Cible usuelle > 10 %.",
        "formule": "RESULTAT_NET / FONDS_PROPRES_MOYENS",
        "type_rapport": "les_deux",
        "categorie": "rentabilite",
        "seuil_min": 10.0,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["RESULTAT_NET", "FONDS_PROPRES_MOYENS"],
        "ordre_affichage": 25,
    },
    {
        "code": "GEST_MARGE_INTERET_NETTE",
        "libelle": "Marge nette d'intérêts",
        "description": "Écart entre intérêts reçus et intérêts payés rapporté au total actif moyen.",
        "formule": "(INTERETS_RECUS - INTERETS_PAYES) / TOTAL_ACTIF_MOYEN",
        "type_rapport": "les_deux",
        "categorie": "rentabilite",
        "seuil_min": 2.0,
        "seuil_max": None,
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["INTERETS_RECUS", "INTERETS_PAYES", "TOTAL_ACTIF_MOYEN"],
        "ordre_affichage": 26,
    },
    {
        "code": "GEST_CREDITS_DEPOTS",
        "libelle": "Ratio crédits / dépôts",
        "description": "Encours des crédits à la clientèle rapporté aux dépôts de la clientèle. Au-delà de 100 %, l'écart est financé par d'autres ressources (interbancaire notamment).",
        "formule": "CREDITS_CLIENTELE / DEPOTS_CLIENTELE",
        "type_rapport": "bilan_reglementaire",
        "categorie": "qualite_portefeuille",
        "seuil_min": None,
        "seuil_max": 100.0,
        "unite": "%",
        "is_reglementaire": False,
        "is_active": True,
        "postes_requis": ["CREDITS_CLIENTELE", "DEPOTS_CLIENTELE"],
        "ordre_affichage": 27,
    },
]
