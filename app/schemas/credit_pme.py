from typing import List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field


# ===================== Données financières annuelles =====================

class FinancialDataYear(BaseModel):
    """Données financières pour une année"""
    year: int = Field(..., description="Année (ex: 2023)")
    chiffre_affaires: float = Field(..., ge=0, description="Chiffre d'affaires (CA)")
    ebitda: float = Field(..., description="EBE (Excédent Brut d'Exploitation, équivalent EBITDA) (peut être négatif)")
    resultat_net: float = Field(..., description="Résultat net (peut être négatif)")
    fonds_propres: float = Field(..., ge=0, description="Fonds propres")
    dettes_financieres_totales: float = Field(..., ge=0, description="Dettes financières totales")
    charges_financieres: float = Field(..., ge=0, description="Charges financières (intérêts)")
    tresorerie: float = Field(..., description="Trésorerie (peut être négative)")
    stocks: Optional[float] = Field(None, ge=0, description="Stocks")
    creances_clients: Optional[float] = Field(None, ge=0, description="Créances clients")
    dettes_fournisseurs: Optional[float] = Field(None, description="Dettes fournisseurs (peut être négatif si avoir)")
    bfr: Optional[float] = Field(None, description="BFR (Besoin en Fonds de Roulement)")


# ===================== Demande de crédit PME =====================

class CreditPMERequest(BaseModel):
    """Demande de crédit PME/PMI - données saisies par l'utilisateur"""
    
    # Profil entreprise
    raison_sociale: str = Field(..., description="Raison sociale / nom de l'entreprise")
    secteur_activite: str = Field(..., description="Secteur: commerce, BTP, industrie, services, agro, etc.")
    taille: str = Field(..., description="TPE, PME, etc.")
    nombre_employes: Optional[int] = Field(None, ge=0, description="Nombre d'employés")
    annee_creation: int = Field(..., ge=1900, description="Année de création")
    forme_juridique: str = Field(..., description="SARL, SA, etc.")
    positionnement: Optional[str] = Field(None, description="Activité principale, gamme de clients")
    
    # Données financières (2-3 ans)
    donnees_financieres: List[FinancialDataYear] = Field(..., min_length=2, max_length=3, description="Données financières sur 2-3 ans")
    
    # Crédit demandé
    montant: float = Field(..., ge=0, description="Montant du crédit demandé")
    objet: str = Field(..., description="investissement, trésorerie, ligne de fonctionnement, etc.")
    duree_mois: int = Field(..., ge=1, description="Durée en mois")
    type_remboursement: str = Field(..., description="amortissable, in fine, etc.")
    garanties: Optional[str] = Field(None, description="hypothèque, nantissement, caution perso, etc.")
    valeur_garanties: Optional[float] = Field(None, ge=0, description="Valeur des garanties (pour LTV)")
    source_remboursement: str = Field(..., description="cash-flow exploitation, subvention, etc.")
    
    # Contexte risque
    concentration_clients: Optional[str] = Field(None, description="Ex: 60% du CA avec 2 clients")
    dependance_fournisseur: Optional[str] = Field(None, description="Dépendance à un fournisseur ou marché public")
    historique_incidents: Optional[str] = Field(None, description="Historique d'incidents de paiement")
    
    # Devise
    currency: str = Field(default="XOF", description="Devise")


# ===================== Métriques calculées =====================

class PMECalculatedMetrics(BaseModel):
    """Métriques calculées automatiquement pour une demande PME"""
    
    # Ratios de performance
    croissance_ca: Optional[float] = Field(None, description="Taux de croissance du CA (%)")
    ebitda_margin: Optional[float] = Field(None, description="Marge EBE (%)")
    net_margin: Optional[float] = Field(None, description="Marge nette (%)")
    
    # Endettement
    debt_to_equity: Optional[float] = Field(None, description="Debt/Equity (Gearing)")
    debt_to_ebitda: Optional[float] = Field(None, description="Dette/EBE")
    
    # Capacité de remboursement
    interest_coverage: Optional[float] = Field(None, description="Couverture des intérêts (EBE / charges financières)")
    debt_service_coverage: Optional[float] = Field(None, description="Capacité de remboursement (CAF / service annuel dette)")
    new_installment_weight: Optional[float] = Field(None, description="Poids nouvelle échéance dans CAF (%)")
    
    # Liquidité
    current_ratio: Optional[float] = Field(None, description="Current ratio (actif courant / passif courant)")
    quick_ratio: Optional[float] = Field(None, description="Quick ratio (actif courant - stocks) / passif courant")
    
    # Garanties
    ltv: Optional[float] = Field(None, description="Loan-to-Value (%) si garantie réelle")
    
    # Données calculées
    caf_annuelle: Optional[float] = Field(None, description="CAF (Capacité d'Autofinancement) annuelle")
    nouvelle_mensualite: Optional[float] = Field(None, description="Mensualité du nouveau crédit")
    service_annuel_dette: Optional[float] = Field(None, description="Service annuel de la dette totale")


# ===================== Analyse complète =====================

class CreditPMEAnalysis(BaseModel):
    """Analyse complète d'une demande de crédit PME"""
    id: str
    user_id: str
    organization_id: str
    request_data: CreditPMERequest
    calculated_metrics: PMECalculatedMetrics
    ai_analysis: str = Field(..., description="Analyse et décision de l'IA")
    ai_decision: Literal["APPROUVE", "REFUSE", "CONDITIONNEL"] = Field(...)
    ai_recommendations: Optional[str] = None
    created_at: datetime

