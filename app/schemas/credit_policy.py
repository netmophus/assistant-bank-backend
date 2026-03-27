"""
Schémas Pydantic pour le moteur de décision de crédit particulier.
Définit la structure complète de la politique de crédit, des demandes et des résultats.
"""
from typing import List, Optional, Dict, Literal, Any
from datetime import datetime
from pydantic import BaseModel, Field


# ======================== TYPES DE CRÉDIT ========================

class LoanTypeConfig(BaseModel):
    """Configuration d'un type de crédit spécifique (CONSO, PERSO, AUTO, IMMO)"""
    enabled: bool = True
    label: str = ""
    minAmount: float = 0.0
    maxAmount: float = 10_000_000.0
    minDurationMonths: int = 6
    maxDurationMonths: int = 60
    defaultDurationMonths: int = 24
    minRate: float = 5.0        # Taux nominal minimum en %
    maxRate: float = 20.0       # Taux nominal maximum en %
    defaultRate: float = 10.0   # Taux proposé par défaut en %
    maxUsuryRate: float = 24.0  # Plafond réglementaire en %
    requiresCollateral: bool = False
    requiresDownPayment: bool = False


# ======================== ÉLIGIBILITÉ ========================

class EligibilityConfig(BaseModel):
    """Conditions d'éligibilité pour traiter un dossier de crédit"""
    minimumNetIncome: float = 150_000.0          # Revenu net mensuel minimum
    minimumEmploymentMonths: int = 12            # Ancienneté minimum pour approbation
    conditionalEmploymentMonths: int = 6         # Ancienneté minimum pour conditionnel
    allowProbationaryPeriod: bool = False
    probationaryDecision: Literal["REJECT", "CONDITIONAL", "ALLOW"] = "CONDITIONAL"
    minimumAge: int = 21
    maximumAge: int = 65
    acceptedContractTypes: List[str] = Field(
        default_factory=lambda: ["CDI", "FONCTIONNAIRE", "RETRAITE", "CDI_PRIVE"]
    )
    rejectedContractTypes: List[str] = Field(
        default_factory=lambda: ["SANS_EMPLOI"]
    )


# ======================== RATIOS DE RISQUE ========================

class DTIConfig(BaseModel):
    """Configuration du taux d'endettement (Debt-to-Income Ratio)"""
    enabled: bool = True
    approvalThreshold: float = 33.0      # % - Zone favorable
    conditionalThreshold: float = 38.0   # % - Zone conditionnelle
    rejectionThreshold: float = 40.0     # % - Seuil de refus


class LivingRemainderConfig(BaseModel):
    """Configuration du reste à vivre mensuel"""
    enabled: bool = True
    minimumAmount: float = 75_000.0          # Montant absolu minimum en devise
    minimumPercentOfIncome: float = 30.0     # % minimum du revenu


class LTVConfig(BaseModel):
    """Configuration du ratio financement/valeur du bien (Loan-to-Value)"""
    enabled: bool = True
    approvalThreshold: float = 70.0      # % - Zone prudente
    conditionalThreshold: float = 80.0   # % - Zone à examiner
    rejectionThreshold: float = 90.0     # % - Seuil de refus


class LTIConfig(BaseModel):
    """Configuration du ratio montant/revenu annuel (Loan-to-Income)"""
    enabled: bool = True
    maximum: float = 4.5    # Multiple maximal du revenu annuel


class RatioConfig(BaseModel):
    """Configuration complète de tous les ratios de risque"""
    dti: DTIConfig = Field(default_factory=DTIConfig)
    livingRemainder: LivingRemainderConfig = Field(default_factory=LivingRemainderConfig)
    ltv: LTVConfig = Field(default_factory=LTVConfig)
    lti: LTIConfig = Field(default_factory=LTIConfig)


# ======================== SCORING ========================

class ScoringWeights(BaseModel):
    """
    Pondérations des critères dans le calcul du score.
    La somme doit être égale à 100.
    """
    dti: float = 20.0
    livingRemainder: float = 15.0
    ltv: float = 10.0
    employmentStability: float = 15.0
    contractType: float = 10.0
    incomeLevel: float = 15.0
    debtBehavior: float = 10.0
    clientProfile: float = 3.0
    documentCompleteness: float = 2.0


class ScoringConfig(BaseModel):
    """Configuration du système de scoring de crédit"""
    enabled: bool = True
    scaleMin: float = 0.0
    scaleMax: float = 100.0
    approvalScore: float = 75.0      # Score minimum pour approbation
    conditionalScore: float = 60.0   # Score minimum pour conditionnel
    rejectionScore: float = 40.0     # Score en dessous duquel on refuse
    weights: ScoringWeights = Field(default_factory=ScoringWeights)


# ======================== AJUSTEMENTS DE PROFIL ========================

class ProfileAdjustments(BaseModel):
    """Bonus/malus appliqués au score selon le profil du client"""
    publicEmployeeBonus: float = 5.0
    permanentContractBonus: float = 3.0
    selfEmployedPenalty: float = -8.0
    probationPenalty: float = -10.0
    seniorityBonusPerYear: float = 1.0
    existingCustomerBonus: float = 3.0
    salaryDomiciliationBonus: float = 5.0


# ======================== DOCUMENTS ========================

class DocumentRequirement(BaseModel):
    """Pièce justificative requise pour le dossier"""
    code: str
    label: str
    required: bool = True
    blockingIfMissing: bool = False


# ======================== SIMULATIONS ========================

class SimulationConfig(BaseModel):
    """Configuration des simulations de scénarios alternatifs"""
    enabled: bool = True
    amountVariations: List[float] = Field(
        default_factory=lambda: [-20.0, -10.0, 10.0]
    )
    durationVariationsMonths: List[int] = Field(
        default_factory=lambda: [-12, 12, 24]
    )
    rateVariations: List[float] = Field(
        default_factory=lambda: [-1.0, 1.0]
    )
    downPaymentVariations: List[float] = Field(
        default_factory=lambda: [10.0, 20.0]
    )


# ======================== DÉROGATIONS ========================

class OverrideConfig(BaseModel):
    """Configuration des dérogations manuelles à la décision automatique"""
    allowManualOverride: bool = False
    manualOverrideRoles: List[str] = Field(default_factory=lambda: ["org_admin"])
    requireOverrideReason: bool = True


# ======================== CONFIGURATION PRINCIPALE ========================

def _default_loan_types() -> Dict[str, Any]:
    return {
        "CONSO": {
            "enabled": True, "label": "Crédit consommation",
            "minAmount": 50000, "maxAmount": 5000000,
            "minDurationMonths": 6, "maxDurationMonths": 60, "defaultDurationMonths": 24,
            "minRate": 8.0, "maxRate": 18.0, "defaultRate": 12.0, "maxUsuryRate": 22.0,
            "requiresCollateral": False, "requiresDownPayment": False
        },
        "PERSO": {
            "enabled": True, "label": "Crédit personnel",
            "minAmount": 50000, "maxAmount": 3000000,
            "minDurationMonths": 6, "maxDurationMonths": 48, "defaultDurationMonths": 24,
            "minRate": 10.0, "maxRate": 20.0, "defaultRate": 14.0, "maxUsuryRate": 24.0,
            "requiresCollateral": False, "requiresDownPayment": False
        },
        "AUTO": {
            "enabled": True, "label": "Crédit automobile",
            "minAmount": 500000, "maxAmount": 15000000,
            "minDurationMonths": 12, "maxDurationMonths": 60, "defaultDurationMonths": 48,
            "minRate": 7.0, "maxRate": 16.0, "defaultRate": 10.0, "maxUsuryRate": 20.0,
            "requiresCollateral": True, "requiresDownPayment": True
        },
        "IMMO": {
            "enabled": True, "label": "Crédit immobilier",
            "minAmount": 1000000, "maxAmount": 100000000,
            "minDurationMonths": 60, "maxDurationMonths": 240, "defaultDurationMonths": 120,
            "minRate": 5.0, "maxRate": 12.0, "defaultRate": 7.5, "maxUsuryRate": 15.0,
            "requiresCollateral": True, "requiresDownPayment": True
        }
    }


def _default_documents() -> Dict[str, Any]:
    common = [
        {"code": "CNI", "label": "Pièce d'identité (CNI ou passeport)", "required": True, "blockingIfMissing": True},
        {"code": "JUSTIF_REVENU", "label": "Justificatif de revenus (3 derniers bulletins)", "required": True, "blockingIfMissing": True},
        {"code": "RELEVES_BANCAIRES", "label": "Relevés bancaires (3 derniers mois)", "required": True, "blockingIfMissing": False},
    ]
    return {
        "CONSO": common,
        "PERSO": common,
        "AUTO": common + [{"code": "FACTURE_DEVIS", "label": "Facture ou devis du véhicule", "required": True, "blockingIfMissing": True}],
        "IMMO": common + [
            {"code": "CONTRAT_TRAVAIL", "label": "Contrat de travail", "required": True, "blockingIfMissing": False},
            {"code": "TITRE_PROPRIETE", "label": "Titre de propriété ou compromis de vente", "required": True, "blockingIfMissing": True},
            {"code": "ATTESTATION_DOM", "label": "Attestation de domiciliation de salaire", "required": False, "blockingIfMissing": False},
        ]
    }


class CreditPolicyConfigBase(BaseModel):
    """
    Configuration complète de la politique de crédit particulier.
    Tous les seuils, règles et paramètres du moteur de décision sont ici.
    Aucun seuil n'est codé en dur dans le moteur — tout vient de cette config.
    """
    # Paramètres généraux
    currency: str = "XOF"
    defaultLoanType: str = "CONSO"
    decisionStrategy: Literal["RULES_ONLY", "SCORING_ONLY", "HYBRID"] = "HYBRID"
    strictMode: bool = False
    enableExplanations: bool = True
    enableSimulations: bool = True
    maxSimulationScenarios: int = 3

    # Types de crédit disponibles
    loanTypes: Dict[str, LoanTypeConfig] = Field(default_factory=lambda: {
        k: LoanTypeConfig(**v) for k, v in _default_loan_types().items()
    })

    # Conditions d'éligibilité
    eligibility: EligibilityConfig = Field(default_factory=EligibilityConfig)

    # Ratios de risque
    ratios: RatioConfig = Field(default_factory=RatioConfig)

    # Scoring
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)

    # Ajustements de profil
    profileAdjustments: ProfileAdjustments = Field(default_factory=ProfileAdjustments)

    # Pièces justificatives par type de crédit
    documents: Dict[str, List[DocumentRequirement]] = Field(default_factory=lambda: {
        k: [DocumentRequirement(**d) for d in v] for k, v in _default_documents().items()
    })

    # Simulations
    simulations: SimulationConfig = Field(default_factory=SimulationConfig)

    # Dérogations manuelles
    overrides: OverrideConfig = Field(default_factory=OverrideConfig)


class CreditPolicyConfigPublic(CreditPolicyConfigBase):
    """Configuration publique retournée par l'API (inclut les métadonnées de version)"""
    id: str
    organization_id: str
    version: str = "1.0"
    status: str = "active"
    effectiveDate: datetime
    updatedAt: datetime
    updatedBy: str = ""


class CreditPolicyConfigCreate(CreditPolicyConfigBase):
    """Payload de création/mise à jour de la configuration"""
    pass


class CreditPolicyVersionPublic(BaseModel):
    """Version archivée de la configuration pour l'historique"""
    id: str
    organization_id: str
    version: str
    status: str
    effectiveDate: datetime
    updatedAt: datetime
    updatedBy: str
    config_snapshot: Dict[str, Any]


# ======================== INPUT DEMANDE DE CRÉDIT ========================

class ExistingLoanInput(BaseModel):
    """Prêt existant déclaré par le client"""
    type: str
    monthlyPayment: float = Field(ge=0)
    remainingDurationMonths: int = Field(ge=1)
    outstandingAmount: float = Field(ge=0)


class CreditApplicationInput(BaseModel):
    """
    Données complètes d'une demande de crédit particulier.
    Saisies par l'utilisateur métier dans l'interface /user/credit.
    """
    # Crédit demandé
    loanType: str
    loanAmount: float = Field(gt=0)
    loanDurationMonths: int = Field(ge=1)
    annualInterestRate: Optional[float] = None  # En % (ex: 12.5 pour 12.5%)
    propertyValue: Optional[float] = None       # Valeur du bien pour le LTV
    downPayment: Optional[float] = None         # Apport personnel

    # Informations client
    clientName: str
    age: Optional[int] = None
    isExistingCustomer: bool = False
    hasSalaryDomiciliation: bool = False

    # Emploi
    contractType: str = ""
    employmentStartDate: Optional[str] = None   # Format ISO
    isOnProbation: bool = False
    probationEndDate: Optional[str] = None
    employerSector: Optional[str] = None

    # Revenus mensuels
    netMonthlySalary: float = Field(ge=0)
    otherMonthlyIncome: float = Field(default=0.0, ge=0)

    # Charges mensuelles
    rentOrMortgage: float = Field(default=0.0, ge=0)
    otherMonthlyCharges: float = Field(default=0.0, ge=0)
    existingLoans: List[ExistingLoanInput] = Field(default_factory=list)

    # Documents fournis (liste de codes)
    providedDocuments: List[str] = Field(default_factory=list)


# ======================== RÉSULTAT DE DÉCISION ========================

class RatioDetail(BaseModel):
    """Détail d'un ratio calculé avec ses seuils et son statut d'évaluation"""
    value: float
    thresholdApproval: Optional[float] = None
    thresholdConditional: Optional[float] = None
    thresholdRejection: Optional[float] = None
    status: Literal["FAVORABLE", "CONDITIONNEL", "BLOQUANT", "NA"] = "NA"
    label: str
    message: str
    unit: str = ""


class TriggeredRule(BaseModel):
    """Règle métier déclenchée lors de l'évaluation du dossier"""
    code: str
    message: str
    impact: Literal["BLOQUANT", "PENALISANT", "FAVORABLE"]


class SimulationScenario(BaseModel):
    """Scénario alternatif simulé pour améliorer la décision"""
    id: str
    label: str
    description: str
    loanAmount: float
    loanDurationMonths: int
    annualInterestRate: float
    monthlyInstallment: float
    newDTI: float
    newLivingRemainder: float
    decision: Literal["APPROUVE", "CONDITIONNEL", "REFUSE"]
    explanation: str


class CreditDecisionResult(BaseModel):
    """
    Résultat complet de l'analyse de crédit par le moteur de décision.
    Contient tous les métriques calculés, ratios évalués, décision finale et simulations.
    """
    # Métriques financières
    appliedRate: float
    monthlyInstallment: float
    totalAmount: float
    totalInterest: float
    currentDTI: float
    newDTI: float
    livingRemainder: float
    ltv: Optional[float] = None
    lti: float
    creditScore: Optional[float] = None
    jobSeniorityMonths: int = 0
    totalMonthlyIncome: float
    totalCurrentCharges: float

    # Détails des ratios avec statuts
    ratioDetails: Dict[str, RatioDetail]

    # Décision et explications
    decision: Literal["APPROUVE", "CONDITIONNEL", "REFUSE"]
    mainReason: str
    strategy: str
    configVersion: str
    triggeredRules: List[TriggeredRule]
    strengths: List[str]
    weaknesses: List[str]
    conditions: List[str]

    # Simulations alternatives
    simulations: List[SimulationScenario]

    # Métadonnées
    analyzedAt: str
    applicationId: str


class CreditApplicationRecord(BaseModel):
    """Enregistrement persisté d'une demande analysée"""
    id: str
    user_id: str
    organization_id: str
    application: CreditApplicationInput
    result: CreditDecisionResult
    created_at: datetime
