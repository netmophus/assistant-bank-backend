"""
Service pour calculer les métriques et ratios d'une demande de crédit particulier.
"""
from datetime import datetime, date
from typing import Optional, Dict, Any
from app.schemas.credit_particulier import (
    CreditParticulierRequest,
    CalculatedMetrics,
    ExistingLoan,
)


def calculate_annuity_payment(principal: float, annual_rate: float, months: int) -> float:
    """
    Calcule la mensualité d'un crédit avec formule d'annuité.
    
    Args:
        principal: Montant du crédit
        annual_rate: Taux annuel (ex: 0.05 pour 5%)
        months: Durée en mois
    
    Returns:
        Mensualité
    """
    if months == 0 or principal == 0:
        return 0.0
    
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        return principal / months
    
    payment = principal * (monthly_rate * (1 + monthly_rate) ** months) / ((1 + monthly_rate) ** months - 1)
    return round(payment, 2)


def calculate_credit_metrics(
    request: CreditParticulierRequest,
    annual_interest_rate: float = 0.05  # 5% par défaut
) -> CalculatedMetrics:
    """
    Calcule toutes les métriques d'une demande de crédit particulier.
    
    Args:
        request: La demande de crédit
        annual_interest_rate: Taux d'intérêt annuel pour calculer la mensualité
    
    Returns:
        CalculatedMetrics avec tous les calculs
    """
    # 1. Revenus
    total_monthly_income = request.netMonthlySalary + request.otherMonthlyIncome
    
    # 2. Charges existantes
    existing_loans_total = sum(loan.monthlyPayment for loan in request.existingLoans)
    total_monthly_charges = request.rentOrMortgage + request.otherMonthlyCharges + existing_loans_total
    
    # 3. DTI actuel
    debt_to_income_ratio = (total_monthly_charges / total_monthly_income * 100) if total_monthly_income > 0 else 0
    
    # 4. Stabilité professionnelle
    job_seniority_months = None
    if request.employmentStartDate:
        start_date = request.employmentStartDate
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        elif isinstance(start_date, date):
            start_date = datetime.combine(start_date, datetime.min.time())
        
        today = datetime.utcnow()
        delta = today - start_date
        job_seniority_months = max(0, delta.days // 30)
    
    en_periode_essai = False
    if request.probationEndDate:
        end_date = request.probationEndDate
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        elif isinstance(end_date, date):
            end_date = datetime.combine(end_date, datetime.min.time())
        
        en_periode_essai = end_date > datetime.utcnow()
    
    # 5. Mensualité du nouveau crédit
    new_loan_monthly_payment = calculate_annuity_payment(
        request.loanAmount,
        annual_interest_rate,
        request.loanDurationMonths
    )
    
    # 6. Charges après projet
    new_total_charges = total_monthly_charges + new_loan_monthly_payment
    new_debt_to_income_ratio = (new_total_charges / total_monthly_income * 100) if total_monthly_income > 0 else 0
    
    # 7. Reste à vivre
    reste_a_vivre = total_monthly_income - new_total_charges
    
    # 8. Loan-to-Income (LTI)
    annual_income = total_monthly_income * 12
    loan_to_income = (request.loanAmount / annual_income * 100) if annual_income > 0 else 0
    
    # 9. Loan-to-Value (LTV) - seulement si crédit immo
    loan_to_value = None
    if request.loanType.upper() in ["IMMO", "IMMOBILIER"] and request.propertyValue and request.propertyValue > 0:
        loan_to_value = (request.loanAmount / request.propertyValue * 100)
    
    # 10. Total des intérêts à payer
    total_interest_paid = (new_loan_monthly_payment * request.loanDurationMonths) - request.loanAmount
    
    return CalculatedMetrics(
        totalMonthlyIncome=round(total_monthly_income, 2),
        totalMonthlyCharges=round(total_monthly_charges, 2),
        debtToIncomeRatio=round(debt_to_income_ratio, 2),
        jobSeniorityMonths=job_seniority_months,
        enPeriodeEssai=en_periode_essai,
        newTotalCharges=round(new_total_charges, 2),
        newDebtToIncomeRatio=round(new_debt_to_income_ratio, 2),
        resteAVivre=round(reste_a_vivre, 2),
        loanToIncome=round(loan_to_income, 2),
        loanToValue=round(loan_to_value, 2) if loan_to_value else None,
        newLoanMonthlyPayment=round(new_loan_monthly_payment, 2),
        annualInterestRate=round(annual_interest_rate * 100, 2),  # En pourcentage
        totalInterestPaid=round(total_interest_paid, 2),
    )


def calculate_risk_ratios(dossier: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calcule les ratios de risque pour un dossier de crédit JSON.
    
    Args:
        dossier: Dossier de crédit au format JSON
        
    Returns:
        Dict avec tous les ratios calculés
    """
    try:
        # Extraire les données du dossier
        demande = dossier.get("demande", {})
        revenus = dossier.get("revenus", {})
        charges = dossier.get("charges", {})
        encours = dossier.get("encours", [])
        garanties = dossier.get("garanties", {})
        
        # Calcul mensualité
        montant = demande.get("montant", 0)
        duree = demande.get("duree", 0)
        taux_annuel = demande.get("taux", 8.5) / 100
        mensualite = calculate_annuity_payment(montant, taux_annuel, duree)
        
        # Calcul taux d'endettement
        total_revenus = revenus.get("total_revenus", 0)
        total_charges = charges.get("total_charges", 0)
        encours_mensualites = sum(e.get("mensualite", 0) for e in encours)
        
        endettement_actuel = ((total_charges + encours_mensualites) / total_revenus * 100) if total_revenus > 0 else 0
        endettement_avec_credit = ((total_charges + encours_mensualites + mensualite) / total_revenus * 100) if total_revenus > 0 else 0
        
        # Reste à vivre
        reste_a_vivre = total_revenus - total_charges - encours_mensualites - mensualite
        
        # Ratios LTI et LTV
        lti = (montant / (total_revenus * 12) * 100) if total_revenus > 0 else 0
        encours_total = sum(e.get("montant", 0) for e in encours)
        ltv = (montant / garanties.get("valeur", 0) * 100) if garanties.get("valeur", 0) > 0 else 0
        
        return {
            "mensualite": round(mensualite, 2),
            "endettement_actuel": round(endettement_actuel, 2),
            "endettement_avec_credit": round(endettement_avec_credit, 2),
            "reste_a_vivre": round(reste_a_vivre, 2),
            "lti": round(lti, 2),
            "ltv": round(ltv, 2),
            "encours_total": encours_total,
            "encours_mensualites": encours_mensualites,
            "total_revenus": total_revenus,
            "total_charges": total_charges
        }
        
    except Exception as e:
        raise ValueError(f"Erreur lors du calcul des ratios: {str(e)}")

