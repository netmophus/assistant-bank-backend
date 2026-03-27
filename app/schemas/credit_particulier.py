from typing import List, Optional, Literal, Any
from datetime import datetime
from pydantic import BaseModel, Field


# ===================== Configuration des champs du formulaire =====================

class FieldConfig(BaseModel):
    """Configuration d'un champ (activé/requis)"""
    enabled: bool = Field(default=True, description="Le champ est-il activé ?")
    required: bool = Field(default=False, description="Le champ est-il obligatoire ?")


class CreditParticulierFieldConfig(BaseModel):
    """Configuration de tous les champs du formulaire crédit particulier"""
    # Identité
    clientName: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=True))
    
    # Situation professionnelle
    employmentStatus: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=True))
    employerName: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=False))
    employerSector: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=False))
    employmentStartDate: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=True))
    contractType: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=True))
    position: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=False))
    probationEndDate: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=False))
    
    # Revenus
    netMonthlySalary: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=True))
    otherMonthlyIncome: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=False))
    incomeCurrency: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=True))
    
    # Charges
    rentOrMortgage: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=False))
    otherMonthlyCharges: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=False))
    existingLoans: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=False))
    
    # Crédit demandé
    loanAmount: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=True))
    loanDurationMonths: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=True))
    loanType: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=True))
    annualInterestRate: FieldConfig = Field(default_factory=lambda: FieldConfig(enabled=True, required=False))


class CreditParticulierConfigPublic(BaseModel):
    """Configuration publique pour une organisation"""
    id: str
    organization_id: str
    field_config: CreditParticulierFieldConfig
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ===================== Demande de crédit particulier =====================

class ExistingLoan(BaseModel):
    """Prêt existant"""
    type: str = Field(..., description="Type: CONSO, IMMO, AUTO, CREDIT_CARTE, etc.")
    monthlyPayment: float = Field(..., ge=0, description="Mensualité")
    remainingDurationMonths: int = Field(..., ge=1, description="Durée restante en mois")
    outstandingAmount: float = Field(..., ge=0, description="Encours restant dû")


class CreditParticulierRequest(BaseModel):
    """Demande de crédit particulier - données saisies par l'utilisateur"""
    # Identité
    clientName: str = Field(..., description="Nom et prénom du client")
    
    # Situation professionnelle
    employmentStatus: Literal["SALAIRE", "FONCTIONNAIRE", "INDEPENDANT", "AUTRE"] = Field(...)
    employerName: Optional[str] = None
    employerSector: Optional[str] = None
    employmentStartDate: Optional[datetime] = None
    contractType: Optional[str] = None
    position: Optional[str] = None
    probationEndDate: Optional[datetime] = None
    
    # Revenus
    netMonthlySalary: float = Field(..., ge=0)
    otherMonthlyIncome: float = Field(default=0, ge=0)
    incomeCurrency: str = Field(default="XOF")
    
    # Charges
    rentOrMortgage: float = Field(default=0, ge=0)
    otherMonthlyCharges: float = Field(default=0, ge=0)
    existingLoans: List[ExistingLoan] = Field(default_factory=list)
    
    # Crédit demandé
    loanAmount: float = Field(..., ge=0, description="Montant du crédit demandé")
    loanDurationMonths: int = Field(..., ge=1, description="Durée en mois")
    loanType: str = Field(..., description="Type: IMMO, CONSO, AUTO, etc.")
    propertyValue: Optional[float] = Field(None, ge=0, description="Valeur du bien (si crédit immo)")
    annualInterestRate: Optional[float] = Field(None, ge=0, le=50, description="Taux d'intérêt annuel en % (ex: 5.5 pour 5.5%)")


class CalculatedMetrics(BaseModel):
    """Métriques calculées automatiquement"""
    totalMonthlyIncome: float
    totalMonthlyCharges: float
    debtToIncomeRatio: float
    jobSeniorityMonths: Optional[int] = None
    enPeriodeEssai: bool = False
    newTotalCharges: float
    newDebtToIncomeRatio: float
    resteAVivre: float
    loanToIncome: float
    loanToValue: Optional[float] = None
    newLoanMonthlyPayment: float
    annualInterestRate: Optional[float] = None  # Optionnel pour compatibilité
    totalInterestPaid: Optional[float] = None  # Optionnel pour compatibilité


class CreditParticulierAnalysis(BaseModel):
    """Analyse complète d'une demande de crédit"""
    id: str
    user_id: str
    organization_id: str
    request_data: CreditParticulierRequest
    calculated_metrics: CalculatedMetrics
    ai_analysis: str = Field(..., description="Analyse et décision de l'IA")
    ai_decision: Literal["APPROUVE", "REFUSE", "CONDITIONNEL"] = Field(...)
    ai_recommendations: Optional[str] = None
    created_at: datetime


# ===================== Chat conversationnel =====================

class ChatMessage(BaseModel):
    """Message dans la conversation"""
    role: Literal["user", "assistant"]
    content: str


class CreditChatRequest(BaseModel):
    """Requête pour discuter d'un dossier de crédit"""
    request_data: Any
    calculated_metrics: Any
    ai_analysis: Optional[str] = None
    ai_decision: Optional[str] = None
    messages: List[ChatMessage] = Field(default_factory=list)
    user_message: str


class CreditChatResponse(BaseModel):
    """Réponse du chat avec l'historique mis à jour"""
    assistant_message: str
    messages: List[ChatMessage]

