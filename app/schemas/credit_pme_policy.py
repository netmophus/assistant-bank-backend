"""
Schémas Pydantic pour la politique de crédit PME/PMI.
Sections A-L de configuration + application utilisateur + résultat de décision.
"""
from typing import List, Optional, Dict, Literal, Any
from datetime import datetime
from pydantic import BaseModel, Field


# ════════════════════════════════════════════════════════════════
# A. PARAMÈTRES GÉNÉRAUX
# ════════════════════════════════════════════════════════════════

class PMEGeneralConfig(BaseModel):
    enabled: bool = True
    strategy: Literal["RULES_ONLY", "SCORING_ONLY", "HYBRID"] = "HYBRID"
    strict_mode: bool = False
    enable_explanations: bool = True
    enable_simulations: bool = True
    max_simulations: int = Field(default=3, ge=1, le=10)
    currency: str = "XOF"
    policy_version: str = "1.0"
    internal_note: str = ""


# ════════════════════════════════════════════════════════════════
# B. ÉLIGIBILITÉ ENTREPRISE
# ════════════════════════════════════════════════════════════════

class PMEEligibilityConfig(BaseModel):
    min_company_age_years: float = Field(default=2.0, ge=0)
    conditional_company_age_years: float = Field(default=1.0, ge=0)
    min_employees: int = Field(default=1, ge=0)
    accepted_legal_forms: List[str] = Field(default_factory=lambda: ["SARL", "SA", "SAS", "EURL", "SNC", "GIE"])
    rejected_legal_forms: List[str] = Field(default_factory=list)
    accepted_sectors: List[str] = Field(default_factory=list)
    restricted_sectors: List[str] = Field(default_factory=list)
    rejected_sectors: List[str] = Field(default_factory=list)
    min_manager_experience_years: float = Field(default=2.0, ge=0)
    require_structured_team_for_large: bool = False
    large_amount_threshold: float = Field(default=50_000_000, ge=0)


# ════════════════════════════════════════════════════════════════
# C. SEUILS FINANCIERS
# ════════════════════════════════════════════════════════════════

class PMEFinancialThresholdsConfig(BaseModel):
    min_ca: float = Field(default=0, ge=0)
    min_resultat_net: float = Field(default=0)
    min_ebitda: float = Field(default=0)
    min_fonds_propres: float = Field(default=0, ge=0)
    max_endettement_total: float = Field(default=0, ge=0)  # 0 = pas de limite
    min_tresorerie: float = Field(default=0)
    min_capacite_remboursement: float = Field(default=0)
    allow_incomplete_financials: bool = True
    min_financial_completeness_score: float = Field(default=60.0, ge=0, le=100)


# ════════════════════════════════════════════════════════════════
# D. RATIOS FINANCIERS
# ════════════════════════════════════════════════════════════════

class PMERatiosConfig(BaseModel):
    enable_debt_equity: bool = True
    max_debt_equity: float = Field(default=3.0, ge=0)
    conditional_debt_equity: float = Field(default=2.0, ge=0)
    enable_dscr: bool = True
    min_dscr: float = Field(default=1.2, ge=0)
    conditional_dscr: float = Field(default=1.0, ge=0)
    enable_treasury_coverage: bool = True
    min_treasury_months: float = Field(default=1.0, ge=0)
    enable_ca_trend: bool = True
    min_ca_trend_pct: float = Field(default=-10.0)
    enable_result_trend: bool = False
    min_result_trend_pct: float = Field(default=-20.0)


# ════════════════════════════════════════════════════════════════
# E. GARANTIES
# ════════════════════════════════════════════════════════════════

class PMEGuaranteeConfig(BaseModel):
    guarantee_required_above: float = Field(default=10_000_000, ge=0)
    min_guarantee_coverage_pct: float = Field(default=80.0, ge=0, le=200)
    conditional_guarantee_coverage_pct: float = Field(default=60.0, ge=0, le=200)
    accepted_guarantee_types: List[str] = Field(
        default_factory=lambda: ["HYPOTHEQUE", "NANTISSEMENT", "CAUTION_PERSO", "GAGE_MATERIEL"]
    )
    rejected_guarantee_types: List[str] = Field(default_factory=list)
    require_guarantee_docs: bool = True
    require_guarantee_free_of_charges: bool = False
    haircut_pct: float = Field(default=20.0, ge=0, le=100)


# ════════════════════════════════════════════════════════════════
# F. BANCARISATION
# ════════════════════════════════════════════════════════════════

class PMEBankingConfig(BaseModel):
    require_bank_relationship: bool = False
    min_bank_relationship_months: int = Field(default=6, ge=0)
    require_flux_domiciliation_for_approval: bool = False
    min_monthly_flux: float = Field(default=0, ge=0)
    enable_incident_penalty: bool = True
    max_incident_level: int = Field(default=2, ge=0, le=3)
    require_credit_history_for_large: bool = False
    large_exposure_threshold: float = Field(default=50_000_000, ge=0)


# ════════════════════════════════════════════════════════════════
# G. RISQUE COMMERCIAL
# ════════════════════════════════════════════════════════════════

class PMECommercialRiskConfig(BaseModel):
    enable_client_concentration: bool = True
    max_client_concentration_pct: float = Field(default=80.0, ge=0, le=100)
    conditional_client_concentration_pct: float = Field(default=60.0, ge=0, le=100)
    enable_supplier_dependency: bool = True
    max_supplier_dependency_pct: float = Field(default=80.0, ge=0, le=100)
    conditional_supplier_dependency_pct: float = Field(default=60.0, ge=0, le=100)
    enable_seasonality_risk: bool = False
    max_seasonality_level: int = Field(default=3, ge=0, le=3)


# ════════════════════════════════════════════════════════════════
# H. GOUVERNANCE
# ════════════════════════════════════════════════════════════════

class PMEGovernanceConfig(BaseModel):
    enable_governance_analysis: bool = True
    min_governance_score: float = Field(default=40.0, ge=0, le=100)
    structured_team_bonus: float = Field(default=5.0, ge=0, le=20)
    weak_governance_penalty: float = Field(default=-5.0, le=0, ge=-20)
    min_manager_seniority_years: float = Field(default=1.0, ge=0)
    manager_experience_bonus: float = Field(default=3.0, ge=0, le=15)


# ════════════════════════════════════════════════════════════════
# I. DOCUMENTS
# ════════════════════════════════════════════════════════════════

class PMEDocumentPolicyConfig(BaseModel):
    enable_document_policy: bool = True
    min_document_completeness_score: float = Field(default=60.0, ge=0, le=100)
    block_if_key_docs_missing: bool = True
    key_mandatory_docs: List[str] = Field(
        default_factory=lambda: ["RCCM", "NIF", "STATUTS", "BILAN_N", "BILAN_N1", "RELEVES_BANCAIRES"]
    )
    complete_dossier_bonus: float = Field(default=5.0, ge=0, le=15)
    missing_key_doc_penalty: float = Field(default=-10.0, le=0, ge=-30)


# ════════════════════════════════════════════════════════════════
# J. SCORING
# ════════════════════════════════════════════════════════════════

class PMEScoringWeights(BaseModel):
    solidite_financiere: float = Field(default=25.0, ge=0, le=100)
    capacite_remboursement: float = Field(default=25.0, ge=0, le=100)
    qualite_garanties: float = Field(default=15.0, ge=0, le=100)
    risque_activite: float = Field(default=15.0, ge=0, le=100)
    gouvernance: float = Field(default=10.0, ge=0, le=100)
    comportement_bancaire: float = Field(default=5.0, ge=0, le=100)
    completude_documentaire: float = Field(default=3.0, ge=0, le=100)
    completude_financiere: float = Field(default=2.0, ge=0, le=100)


class PMEScoringConfig(BaseModel):
    enabled: bool = True
    score_min: float = Field(default=0.0, ge=0)
    score_max: float = Field(default=100.0, ge=0)
    score_approval: float = Field(default=70.0, ge=0, le=100)
    score_conditional: float = Field(default=50.0, ge=0, le=100)
    score_rejection: float = Field(default=30.0, ge=0, le=100)
    weights: PMEScoringWeights = Field(default_factory=PMEScoringWeights)


# ════════════════════════════════════════════════════════════════
# K. BONUS / MALUS
# ════════════════════════════════════════════════════════════════

class PMEBonusMalusConfig(BaseModel):
    bonus_domiciliation: float = Field(default=3.0, ge=0, le=10)
    bonus_client_existant: float = Field(default=3.0, ge=0, le=10)
    bonus_bon_historique_remboursement: float = Field(default=5.0, ge=0, le=15)
    penalty_incidents_bancaires: float = Field(default=-8.0, le=0, ge=-25)
    penalty_concentration_client: float = Field(default=-5.0, le=0, ge=-20)
    penalty_dependance_fournisseur: float = Field(default=-3.0, le=0, ge=-15)
    penalty_donnees_financieres_incompletes: float = Field(default=-5.0, le=0, ge=-20)
    penalty_documentation_faible: float = Field(default=-5.0, le=0, ge=-20)
    bonus_gouvernance_forte: float = Field(default=5.0, ge=0, le=15)


# ════════════════════════════════════════════════════════════════
# L. DÉROGATION
# ════════════════════════════════════════════════════════════════

class PMEOverrideConfig(BaseModel):
    allow_manual_override: bool = False
    override_roles: List[str] = Field(default_factory=lambda: ["org_admin"])
    require_justification: bool = True
    require_audit_log: bool = True


# ════════════════════════════════════════════════════════════════
# CONFIG PRINCIPALE PME
# ════════════════════════════════════════════════════════════════

class PMEPolicyConfig(BaseModel):
    """Configuration complète de la politique de crédit PME/PMI — sections A-L"""
    general: PMEGeneralConfig = Field(default_factory=PMEGeneralConfig)
    eligibility: PMEEligibilityConfig = Field(default_factory=PMEEligibilityConfig)
    financial_thresholds: PMEFinancialThresholdsConfig = Field(default_factory=PMEFinancialThresholdsConfig)
    ratios: PMERatiosConfig = Field(default_factory=PMERatiosConfig)
    guarantees: PMEGuaranteeConfig = Field(default_factory=PMEGuaranteeConfig)
    banking: PMEBankingConfig = Field(default_factory=PMEBankingConfig)
    commercial_risk: PMECommercialRiskConfig = Field(default_factory=PMECommercialRiskConfig)
    governance: PMEGovernanceConfig = Field(default_factory=PMEGovernanceConfig)
    document_policy: PMEDocumentPolicyConfig = Field(default_factory=PMEDocumentPolicyConfig)
    scoring: PMEScoringConfig = Field(default_factory=PMEScoringConfig)
    bonus_malus: PMEBonusMalusConfig = Field(default_factory=PMEBonusMalusConfig)
    override: PMEOverrideConfig = Field(default_factory=PMEOverrideConfig)


# ════════════════════════════════════════════════════════════════
# APPLICATION INPUT (USER)
# ════════════════════════════════════════════════════════════════

class PMEFinancialYear(BaseModel):
    year: int
    ca: Optional[float] = None
    resultat_net: Optional[float] = None
    ebitda: Optional[float] = None
    fonds_propres: Optional[float] = None
    endettement_total: Optional[float] = None
    tresorerie: Optional[float] = None
    bfr: Optional[float] = None
    fonds_roulement: Optional[float] = None
    charges_financieres: Optional[float] = None
    stocks: Optional[float] = None
    creances_clients: Optional[float] = None
    dettes_fournisseurs: Optional[float] = None


class PMEDocumentItem(BaseModel):
    code: str
    label: str
    fourni: bool = False
    obligatoire: bool = False
    bloquant: bool = False
    commentaire: str = ""


class PMEApplicationInput(BaseModel):
    # A. Identification entreprise
    raison_sociale: str
    nom_commercial: Optional[str] = None
    rccm: Optional[str] = None
    nif: Optional[str] = None
    annee_creation: int
    forme_juridique: str
    secteur: str
    sous_secteur: Optional[str] = None
    ville: Optional[str] = None
    region: Optional[str] = None
    adresse: Optional[str] = None
    telephone: Optional[str] = None
    email: Optional[str] = None
    site_web: Optional[str] = None
    taille: str = "PME"
    nombre_employes: int = Field(default=1, ge=0)
    positionnement: Optional[str] = None
    zone_activite: Optional[str] = None

    # B. Dirigeant / gouvernance
    nom_dirigeant: str
    age_dirigeant: Optional[int] = None
    fonction_dirigeant: Optional[str] = None
    experience_secteur_ans: float = Field(default=0, ge=0)
    anciennete_direction_ans: float = Field(default=0, ge=0)
    niveau_formation: Optional[str] = None
    structure_actionnariat: Optional[str] = None
    equipe_structuree: bool = False
    gouvernance_formelle: bool = False

    # C. Activité
    description_activite: Optional[str] = None
    produits_services: Optional[str] = None
    principaux_clients: Optional[str] = None
    principaux_fournisseurs: Optional[str] = None
    saisonnalite: Optional[str] = None
    dependance_client_majeur: bool = False
    part_plus_gros_client_pct: Optional[float] = Field(default=None, ge=0, le=100)
    dependance_fournisseur_majeur: bool = False
    part_plus_gros_fournisseur_pct: Optional[float] = Field(default=None, ge=0, le=100)
    niveau_concurrence: Optional[str] = None
    part_marche_pct: Optional[float] = Field(default=None, ge=0, le=100)
    perspectives_croissance: Optional[str] = None

    # D. Données financières
    donnees_financieres: List[PMEFinancialYear] = Field(..., min_length=1, max_length=5)
    annuites_existantes_annuelles: Optional[float] = Field(default=None, ge=0)
    capacite_remboursement_estimee: Optional[float] = Field(default=None, ge=0)

    # E. Crédit demandé
    montant_demande: float = Field(..., ge=0)
    devise: str = "XOF"
    objet_credit: str
    type_credit: Literal["INVESTISSEMENT", "TRESORERIE", "LIGNE_FONCTIONNEMENT", "AUTRE"] = "INVESTISSEMENT"
    duree_mois: int = Field(..., ge=1)
    periodicite: Literal["MENSUELLE", "TRIMESTRIELLE", "SEMESTRIELLE", "ANNUELLE", "IN_FINE"] = "MENSUELLE"
    taux_annuel_pct: Optional[float] = Field(default=None, ge=0, le=50)
    periode_grace_mois: int = Field(default=0, ge=0)
    apport_personnel: Optional[float] = Field(default=None, ge=0)
    source_remboursement: str = "cash-flow exploitation"
    plan_remboursement: Optional[str] = None
    urgence: Optional[Literal["FAIBLE", "NORMALE", "HAUTE"]] = "NORMALE"

    # F. Garanties
    garanties_prevues: bool = False
    type_garantie: Optional[str] = None
    description_garantie: Optional[str] = None
    valeur_estimee_garantie: Optional[float] = Field(default=None, ge=0)
    valeur_retenue_garantie: Optional[float] = Field(default=None, ge=0)
    proprietaire_garantie: Optional[str] = None
    garantie_libre_de_charges: Optional[bool] = None
    documents_garantie_disponibles: Optional[bool] = None

    # G. Bancarisation
    client_existant: bool = False
    anciennete_relation_bancaire_mois: int = Field(default=0, ge=0)
    flux_domicilies: Optional[bool] = None
    volume_flux_mensuels: Optional[float] = Field(default=None, ge=0)
    niveau_incidents_bancaires: int = Field(default=0, ge=0, le=3)
    historique_credits_precedents: Optional[str] = None
    comportement_remboursement: Optional[Literal["BON", "MOYEN", "MAUVAIS"]] = None
    nombre_banques: int = Field(default=1, ge=0)
    comptes_autres_banques: bool = False

    # H. Documents
    documents: List[PMEDocumentItem] = Field(default_factory=list)


# ════════════════════════════════════════════════════════════════
# RÉSULTAT DE DÉCISION PME
# ════════════════════════════════════════════════════════════════

class PMERatioDetail(BaseModel):
    label: str
    value: float
    unit: str = ""
    status: Literal["FAVORABLE", "CONDITIONNEL", "BLOQUANT", "NA"] = "NA"
    message: str = ""
    threshold_approval: Optional[float] = None
    threshold_rejection: Optional[float] = None


class PMETriggeredRule(BaseModel):
    code: str
    section: str
    impact: Literal["BLOQUANT", "PENALISANT", "FAVORABLE"]
    message: str


class PMESimulationScenario(BaseModel):
    id: str
    label: str
    description: str
    montant: float
    duree_mois: int
    mensualite: float
    decision: Literal["APPROUVE", "CONDITIONNEL", "REFUSE"]
    score: Optional[float] = None
    explication: str = ""


class PMECalculatedIndicators(BaseModel):
    company_age_years: float = 0
    ca_n: Optional[float] = None
    ca_n1: Optional[float] = None
    ca_growth_pct: Optional[float] = None
    resultat_net_n: Optional[float] = None
    ebitda_n: Optional[float] = None
    ebitda_margin_pct: Optional[float] = None
    fonds_propres_n: Optional[float] = None
    endettement_n: Optional[float] = None
    tresorerie_n: Optional[float] = None
    debt_equity_ratio: Optional[float] = None
    dscr: Optional[float] = None
    treasury_coverage_months: Optional[float] = None
    guarantee_coverage_pct: Optional[float] = None
    nouvelle_mensualite: Optional[float] = None
    annuite_annuelle: Optional[float] = None
    financial_completeness_score: float = 0
    document_completeness_score: float = 0
    governance_score: float = 0


class PMEDecisionResult(BaseModel):
    decision: Literal["APPROUVE", "CONDITIONNEL", "REFUSE"]
    main_reason: str
    credit_score: Optional[float] = None
    strategy: str
    config_version: str
    currency: str
    indicators: PMECalculatedIndicators
    ratio_details: Dict[str, PMERatioDetail] = Field(default_factory=dict)
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    conditions: List[str] = Field(default_factory=list)
    missing_documents: List[str] = Field(default_factory=list)
    identified_risks: List[str] = Field(default_factory=list)
    triggered_rules: List[PMETriggeredRule] = Field(default_factory=list)
    simulations: List[PMESimulationScenario] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)


class PMEApplicationRecord(BaseModel):
    id: str
    user_id: str
    organization_id: str
    application: PMEApplicationInput
    result: PMEDecisionResult
    created_at: datetime
