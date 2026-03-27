"""
Moteur de décision de crédit particulier.

Ce service implémente les calculs financiers, l'évaluation des règles d'éligibilité,
le scoring multicritère et la génération de simulations alternatives.

PRINCIPE FONDAMENTAL : Tous les seuils et paramètres sont lus depuis la configuration
active. Aucune valeur n'est codée en dur dans ce fichier.
"""
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple

from app.schemas.credit_policy import (
    CreditApplicationInput,
    CreditPolicyConfigPublic,
    CreditDecisionResult,
    RatioDetail,
    TriggeredRule,
    SimulationScenario,
    LoanTypeConfig,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
# CALCULS FINANCIERS DE BASE
# ════════════════════════════════════════════════════════════════════

def calculate_monthly_installment(principal: float, annual_rate_pct: float, months: int) -> float:
    """
    Calcule la mensualité par la formule d'annuité constante.

    Args:
        principal: Montant du crédit
        annual_rate_pct: Taux annuel en % (ex: 12.5 pour 12.5%)
        months: Durée en mois

    Returns:
        Mensualité arrondie à 2 décimales
    """
    if months <= 0 or principal <= 0:
        return 0.0
    monthly_rate = (annual_rate_pct / 100) / 12
    if monthly_rate == 0:
        return round(principal / months, 2)
    payment = principal * (monthly_rate * (1 + monthly_rate) ** months) / ((1 + monthly_rate) ** months - 1)
    return round(payment, 2)


def calculate_seniority_months(employment_start_date: Optional[str]) -> int:
    """Calcule l'ancienneté en mois depuis la date d'embauche."""
    if not employment_start_date:
        return 0
    try:
        start = datetime.fromisoformat(employment_start_date.replace('Z', '+00:00'))
        delta = datetime.utcnow() - start.replace(tzinfo=None)
        return max(0, delta.days // 30)
    except Exception:
        return 0


def _get_effective_rate(application: CreditApplicationInput, loan_type_cfg: Optional[LoanTypeConfig]) -> float:
    """Détermine le taux d'intérêt à appliquer (saisi > défaut type > 10%)."""
    if application.annualInterestRate is not None and application.annualInterestRate > 0:
        return application.annualInterestRate
    if loan_type_cfg:
        return loan_type_cfg.defaultRate
    return 10.0


# ════════════════════════════════════════════════════════════════════
# ÉVALUATION DES RÈGLES D'ÉLIGIBILITÉ
# ════════════════════════════════════════════════════════════════════

def _evaluate_eligibility_rules(
    application: CreditApplicationInput,
    config: CreditPolicyConfigPublic,
    seniority: int,
    total_income: float
) -> List[TriggeredRule]:
    """
    Évalue les conditions d'éligibilité et retourne les règles déclenchées.
    Une règle BLOQUANTE provoque un refus en mode RULES_ONLY et HYBRID.
    """
    rules = []
    eligibility = config.eligibility

    # ── Revenu minimum ──────────────────────────────────────────────
    if total_income < eligibility.minimumNetIncome:
        rules.append(TriggeredRule(
            code="INCOME_TOO_LOW",
            message=f"Revenu mensuel net ({total_income:,.0f} {config.currency}) inférieur "
                    f"au minimum requis ({eligibility.minimumNetIncome:,.0f} {config.currency})",
            impact="BLOQUANT"
        ))
    elif total_income >= eligibility.minimumNetIncome * 2:
        rules.append(TriggeredRule(
            code="HIGH_INCOME",
            message=f"Revenu élevé ({total_income:,.0f} {config.currency}/mois) — profil favorable",
            impact="FAVORABLE"
        ))

    # ── Type de contrat ─────────────────────────────────────────────
    contract_upper = application.contractType.upper().replace(' ', '_').replace('-', '_')
    for rejected in eligibility.rejectedContractTypes:
        if rejected.upper().replace(' ', '_') in contract_upper or contract_upper in rejected.upper().replace(' ', '_'):
            rules.append(TriggeredRule(
                code="CONTRACT_REJECTED",
                message=f"Type de contrat '{application.contractType}' exclu par la politique de crédit",
                impact="BLOQUANT"
            ))
            break

    # ── Période d'essai ─────────────────────────────────────────────
    if application.isOnProbation:
        if not eligibility.allowProbationaryPeriod or eligibility.probationaryDecision == "REJECT":
            rules.append(TriggeredRule(
                code="PROBATION_REJECT",
                message="Client en période d'essai — refus automatique selon la politique",
                impact="BLOQUANT"
            ))
        elif eligibility.probationaryDecision == "CONDITIONAL":
            rules.append(TriggeredRule(
                code="PROBATION_CONDITIONAL",
                message="Client en période d'essai — dossier traité de façon conditionnelle",
                impact="PENALISANT"
            ))

    # ── Ancienneté ──────────────────────────────────────────────────
    if seniority < eligibility.conditionalEmploymentMonths:
        rules.append(TriggeredRule(
            code="SENIORITY_INSUFFICIENT",
            message=f"Ancienneté insuffisante ({seniority} mois, minimum {eligibility.conditionalEmploymentMonths} mois)",
            impact="BLOQUANT"
        ))
    elif seniority < eligibility.minimumEmploymentMonths:
        rules.append(TriggeredRule(
            code="SENIORITY_CONDITIONAL",
            message=f"Ancienneté en zone conditionnelle ({seniority} mois, optimal {eligibility.minimumEmploymentMonths} mois)",
            impact="PENALISANT"
        ))
    else:
        rules.append(TriggeredRule(
            code="SENIORITY_FAVORABLE",
            message=f"Ancienneté satisfaisante ({seniority} mois)",
            impact="FAVORABLE"
        ))

    # ── Âge ─────────────────────────────────────────────────────────
    if application.age:
        if application.age < eligibility.minimumAge:
            rules.append(TriggeredRule(
                code="AGE_TOO_YOUNG",
                message=f"Âge ({application.age} ans) inférieur au minimum requis ({eligibility.minimumAge} ans)",
                impact="BLOQUANT"
            ))
        elif application.age > eligibility.maximumAge:
            rules.append(TriggeredRule(
                code="AGE_TOO_OLD",
                message=f"Âge ({application.age} ans) supérieur au maximum autorisé ({eligibility.maximumAge} ans)",
                impact="BLOQUANT"
            ))

    return rules


def _evaluate_loan_type_rules(
    application: CreditApplicationInput,
    config: CreditPolicyConfigPublic,
    loan_type_cfg: Optional[LoanTypeConfig]
) -> List[TriggeredRule]:
    """Vérifie les limites du type de crédit (montant, durée)."""
    rules = []
    if not loan_type_cfg:
        return rules

    if application.loanAmount < loan_type_cfg.minAmount:
        rules.append(TriggeredRule(
            code="AMOUNT_BELOW_MIN",
            message=f"Montant ({application.loanAmount:,.0f} {config.currency}) inférieur au minimum "
                    f"pour ce type ({loan_type_cfg.minAmount:,.0f} {config.currency})",
            impact="BLOQUANT"
        ))
    elif application.loanAmount > loan_type_cfg.maxAmount:
        rules.append(TriggeredRule(
            code="AMOUNT_ABOVE_MAX",
            message=f"Montant ({application.loanAmount:,.0f} {config.currency}) supérieur au maximum "
                    f"({loan_type_cfg.maxAmount:,.0f} {config.currency})",
            impact="BLOQUANT"
        ))

    if application.loanDurationMonths < loan_type_cfg.minDurationMonths:
        rules.append(TriggeredRule(
            code="DURATION_BELOW_MIN",
            message=f"Durée ({application.loanDurationMonths} mois) inférieure au minimum ({loan_type_cfg.minDurationMonths} mois)",
            impact="BLOQUANT"
        ))
    elif application.loanDurationMonths > loan_type_cfg.maxDurationMonths:
        rules.append(TriggeredRule(
            code="DURATION_ABOVE_MAX",
            message=f"Durée ({application.loanDurationMonths} mois) supérieure au maximum ({loan_type_cfg.maxDurationMonths} mois)",
            impact="BLOQUANT"
        ))

    return rules


# ════════════════════════════════════════════════════════════════════
# ÉVALUATION DES RATIOS
# ════════════════════════════════════════════════════════════════════

def _evaluate_ratio_rules(
    config: CreditPolicyConfigPublic,
    new_dti: float,
    living_remainder: float,
    ltv: Optional[float],
    lti: float,
    total_income: float
) -> Tuple[Dict[str, RatioDetail], List[TriggeredRule]]:
    """
    Évalue les ratios de risque selon les seuils configurés.
    Retourne le détail de chaque ratio et les règles déclenchées.
    """
    ratio_details: Dict[str, RatioDetail] = {}
    rules: List[TriggeredRule] = []
    ratios = config.ratios

    # ── DTI ─────────────────────────────────────────────────────────
    if ratios.dti.enabled:
        dti_cfg = ratios.dti
        if new_dti <= dti_cfg.approvalThreshold:
            status = "FAVORABLE"
            msg = f"Taux d'endettement favorable ({new_dti:.1f}% ≤ {dti_cfg.approvalThreshold}%)"
            rules.append(TriggeredRule(code="DTI_FAVORABLE", message=msg, impact="FAVORABLE"))
        elif new_dti <= dti_cfg.conditionalThreshold:
            status = "CONDITIONNEL"
            msg = f"Taux d'endettement en zone à surveiller ({new_dti:.1f}%, seuil favorable {dti_cfg.approvalThreshold}%)"
            rules.append(TriggeredRule(code="DTI_CONDITIONAL", message=msg, impact="PENALISANT"))
        elif new_dti <= dti_cfg.rejectionThreshold:
            status = "CONDITIONNEL"
            msg = f"Taux d'endettement élevé ({new_dti:.1f}%, seuil refus {dti_cfg.rejectionThreshold}%)"
            rules.append(TriggeredRule(code="DTI_HIGH", message=msg, impact="PENALISANT"))
        else:
            status = "BLOQUANT"
            msg = f"Taux d'endettement trop élevé ({new_dti:.1f}% > {dti_cfg.rejectionThreshold}%)"
            rules.append(TriggeredRule(code="DTI_EXCEEDED", message=msg, impact="BLOQUANT"))

        ratio_details["dti"] = RatioDetail(
            value=round(new_dti, 2),
            thresholdApproval=dti_cfg.approvalThreshold,
            thresholdConditional=dti_cfg.conditionalThreshold,
            thresholdRejection=dti_cfg.rejectionThreshold,
            status=status, label="Taux d'endettement (DTI)",
            message=msg, unit="%"
        )

    # ── Reste à vivre ────────────────────────────────────────────────
    if ratios.livingRemainder.enabled:
        lr_cfg = ratios.livingRemainder
        min_by_amount = lr_cfg.minimumAmount
        min_by_pct = (lr_cfg.minimumPercentOfIncome / 100) * total_income
        effective_min = max(min_by_amount, min_by_pct)

        if living_remainder >= effective_min:
            status = "FAVORABLE"
            msg = f"Reste à vivre suffisant ({living_remainder:,.0f} {config.currency}/mois)"
            rules.append(TriggeredRule(code="LIVING_REMAINDER_OK", message=msg, impact="FAVORABLE"))
        elif living_remainder > 0:
            status = "CONDITIONNEL"
            msg = f"Reste à vivre insuffisant ({living_remainder:,.0f} vs min {effective_min:,.0f} {config.currency})"
            rules.append(TriggeredRule(code="LOW_LIVING_REMAINDER", message=msg, impact="PENALISANT"))
        else:
            status = "BLOQUANT"
            msg = f"Reste à vivre négatif ({living_remainder:,.0f} {config.currency}) — dossier non viable"
            rules.append(TriggeredRule(code="NEGATIVE_LIVING_REMAINDER", message=msg, impact="BLOQUANT"))

        ratio_details["livingRemainder"] = RatioDetail(
            value=round(living_remainder, 2),
            thresholdApproval=effective_min,
            status=status, label="Reste à vivre mensuel",
            message=msg, unit=config.currency
        )

    # ── LTV ──────────────────────────────────────────────────────────
    if ratios.ltv.enabled and ltv is not None:
        ltv_cfg = ratios.ltv
        if ltv <= ltv_cfg.approvalThreshold:
            status = "FAVORABLE"
            msg = f"LTV favorable — apport confortable ({ltv:.1f}% financé)"
        elif ltv <= ltv_cfg.conditionalThreshold:
            status = "CONDITIONNEL"
            msg = f"LTV en zone conditionnelle ({ltv:.1f}%, seuil {ltv_cfg.approvalThreshold}%)"
            rules.append(TriggeredRule(code="LTV_CONDITIONAL", message=msg, impact="PENALISANT"))
        else:
            status = "BLOQUANT"
            msg = f"LTV trop élevé ({ltv:.1f}% > {ltv_cfg.rejectionThreshold}%) — financement excessif"
            rules.append(TriggeredRule(code="LTV_EXCEEDED", message=msg, impact="BLOQUANT"))

        ratio_details["ltv"] = RatioDetail(
            value=round(ltv, 2),
            thresholdApproval=ltv_cfg.approvalThreshold,
            thresholdConditional=ltv_cfg.conditionalThreshold,
            thresholdRejection=ltv_cfg.rejectionThreshold,
            status=status, label="Ratio financement/valeur bien (LTV)",
            message=msg, unit="%"
        )

    # ── LTI ──────────────────────────────────────────────────────────
    if ratios.lti.enabled:
        lti_cfg = ratios.lti
        if lti <= lti_cfg.maximum:
            status = "FAVORABLE"
            msg = f"LTI acceptable ({lti:.2f}x le revenu annuel, max {lti_cfg.maximum}x)"
            rules.append(TriggeredRule(code="LTI_FAVORABLE", message=msg, impact="FAVORABLE"))
        else:
            status = "BLOQUANT" if config.strictMode else "CONDITIONNEL"
            msg = f"LTI trop élevé ({lti:.2f}x > {lti_cfg.maximum}x le revenu annuel)"
            rules.append(TriggeredRule(
                code="LTI_EXCEEDED", message=msg,
                impact="BLOQUANT" if config.strictMode else "PENALISANT"
            ))

        ratio_details["lti"] = RatioDetail(
            value=round(lti, 4),
            thresholdApproval=lti_cfg.maximum,
            status=status, label="Ratio montant/revenu annuel (LTI)",
            message=msg, unit="x"
        )

    return ratio_details, rules


# ════════════════════════════════════════════════════════════════════
# CALCUL DU SCORE DE CRÉDIT
# ════════════════════════════════════════════════════════════════════

def _calculate_credit_score(
    application: CreditApplicationInput,
    config: CreditPolicyConfigPublic,
    new_dti: float,
    living_remainder: float,
    ltv: Optional[float],
    lti: float,
    seniority: int,
    total_income: float
) -> float:
    """
    Calcule un score de crédit entre 0 et 100.
    Chaque critère est noté 0-100 puis pondéré selon la configuration.
    Les ajustements de profil viennent s'additionner au score de base.
    """
    scoring = config.scoring
    weights = scoring.weights
    adjustments = config.profileAdjustments
    eligibility = config.eligibility

    # Score DTI
    if config.ratios.dti.enabled:
        dti_cfg = config.ratios.dti
        if new_dti <= dti_cfg.approvalThreshold:
            score_dti = 100.0
        elif new_dti <= dti_cfg.conditionalThreshold:
            score_dti = 60.0
        elif new_dti <= dti_cfg.rejectionThreshold:
            score_dti = 30.0
        else:
            score_dti = 0.0
    else:
        score_dti = 75.0

    # Score reste à vivre
    if config.ratios.livingRemainder.enabled:
        lr_cfg = config.ratios.livingRemainder
        min_lr = max(lr_cfg.minimumAmount, (lr_cfg.minimumPercentOfIncome / 100) * total_income)
        if living_remainder >= min_lr * 1.5:
            score_lr = 100.0
        elif living_remainder >= min_lr:
            score_lr = 75.0
        elif living_remainder > 0:
            score_lr = 30.0
        else:
            score_lr = 0.0
    else:
        score_lr = 75.0

    # Score LTV
    if config.ratios.ltv.enabled and ltv is not None:
        ltv_cfg = config.ratios.ltv
        if ltv <= ltv_cfg.approvalThreshold:
            score_ltv = 100.0
        elif ltv <= ltv_cfg.conditionalThreshold:
            score_ltv = 60.0
        else:
            score_ltv = 20.0
    else:
        score_ltv = 80.0

    # Score stabilité emploi
    min_months = eligibility.minimumEmploymentMonths
    if seniority >= min_months * 2:
        score_stability = 100.0
    elif seniority >= min_months:
        score_stability = 80.0
    elif seniority >= eligibility.conditionalEmploymentMonths:
        score_stability = 50.0
    else:
        score_stability = 10.0

    # Score type de contrat
    contract_upper = application.contractType.upper().replace(' ', '_')
    if "FONCTIONNAIRE" in contract_upper or "TITULAIRE" in contract_upper:
        score_contract = 100.0
    elif "CDI" in contract_upper or "PERMANENT" in contract_upper:
        score_contract = 85.0
    elif "RETRAITE" in contract_upper:
        score_contract = 90.0
    elif "CDD" in contract_upper:
        score_contract = 50.0
    elif "INDEPENDANT" in contract_upper or "AUTO" in contract_upper:
        score_contract = 40.0
    else:
        score_contract = 30.0

    # Score niveau de revenu (relatif au minimum)
    income_ratio = total_income / eligibility.minimumNetIncome if eligibility.minimumNetIncome > 0 else 1.0
    if income_ratio >= 3.0:
        score_income = 100.0
    elif income_ratio >= 2.0:
        score_income = 85.0
    elif income_ratio >= 1.5:
        score_income = 70.0
    elif income_ratio >= 1.0:
        score_income = 50.0
    else:
        score_income = 0.0

    # Score comportement d'endettement
    if not application.existingLoans:
        score_debt = 100.0
    elif len(application.existingLoans) == 1:
        score_debt = 70.0
    elif len(application.existingLoans) == 2:
        score_debt = 50.0
    else:
        score_debt = 20.0

    # Score profil client
    score_profile = 50.0
    if application.isExistingCustomer:
        score_profile += 25.0
    if application.hasSalaryDomiciliation:
        score_profile += 25.0

    # Score complétude documentaire
    docs_config = config.documents.get(application.loanType.upper(), config.documents.get(application.loanType, []))
    required_docs = [d for d in docs_config if d.required]
    if required_docs:
        provided = set(application.providedDocuments)
        required_codes = {d.code for d in required_docs}
        completeness = len(provided & required_codes) / len(required_codes)
        score_docs = completeness * 100
    else:
        score_docs = 80.0

    # Score pondéré
    base_score = (
        score_dti * weights.dti / 100 +
        score_lr * weights.livingRemainder / 100 +
        score_ltv * weights.ltv / 100 +
        score_stability * weights.employmentStability / 100 +
        score_contract * weights.contractType / 100 +
        score_income * weights.incomeLevel / 100 +
        score_debt * weights.debtBehavior / 100 +
        score_profile * weights.clientProfile / 100 +
        score_docs * weights.documentCompleteness / 100
    )

    # Ajustements de profil
    adj = adjustments
    contract_u = application.contractType.upper()
    if "FONCTIONNAIRE" in contract_u or "PUBLIC" in contract_u:
        base_score += adj.publicEmployeeBonus
    if "CDI" in contract_u:
        base_score += adj.permanentContractBonus
    if "INDEPENDANT" in contract_u or "AUTO_ENTREPRENEUR" in contract_u:
        base_score += adj.selfEmployedPenalty
    if application.isOnProbation:
        base_score += adj.probationPenalty
    if seniority > 0:
        years = seniority / 12
        base_score += min(adj.seniorityBonusPerYear * years, 10.0)  # plafonné à 10 pts
    if application.isExistingCustomer:
        base_score += adj.existingCustomerBonus
    if application.hasSalaryDomiciliation:
        base_score += adj.salaryDomiciliationBonus

    return round(max(scoring.scaleMin, min(scoring.scaleMax, base_score)), 1)


# ════════════════════════════════════════════════════════════════════
# GÉNÉRATION DES SIMULATIONS
# ════════════════════════════════════════════════════════════════════

def _generate_simulations(
    application: CreditApplicationInput,
    config: CreditPolicyConfigPublic,
    applied_rate: float,
    total_income: float,
    total_current_charges: float
) -> List[SimulationScenario]:
    """
    Génère des scénarios alternatifs pour aider à transformer un refus.
    Chaque simulation recalcule les métriques clés et produit une nouvelle décision.
    """
    scenarios = []
    loan_type_cfg = config.loanTypes.get(application.loanType.upper())

    def quick_decision(new_dti_val: float, new_lr_val: float) -> str:
        """Évaluation rapide de la décision pour un scénario."""
        if config.ratios.dti.enabled:
            if new_dti_val > config.ratios.dti.rejectionThreshold:
                return "REFUSE"
            if new_dti_val > config.ratios.dti.approvalThreshold:
                return "CONDITIONNEL"
        if config.ratios.livingRemainder.enabled:
            min_lr = max(
                config.ratios.livingRemainder.minimumAmount,
                (config.ratios.livingRemainder.minimumPercentOfIncome / 100) * total_income
            )
            if new_lr_val < 0:
                return "REFUSE"
            if new_lr_val < min_lr:
                return "CONDITIONNEL"
        return "APPROUVE"

    def sim_id() -> str:
        return str(uuid.uuid4())[:8]

    currency = config.currency

    # Scénario 1 : Réduire le montant de 20%
    if len(scenarios) < config.maxSimulationScenarios:
        reduced_amount = application.loanAmount * 0.80
        if loan_type_cfg is None or reduced_amount >= loan_type_cfg.minAmount:
            m = calculate_monthly_installment(reduced_amount, applied_rate, application.loanDurationMonths)
            dti = ((total_current_charges + m) / total_income * 100) if total_income > 0 else 0
            lr = total_income - total_current_charges - m
            scenarios.append(SimulationScenario(
                id=sim_id(),
                label="Montant réduit de 20%",
                description=f"Réduire la demande à {reduced_amount:,.0f} {currency}",
                loanAmount=reduced_amount,
                loanDurationMonths=application.loanDurationMonths,
                annualInterestRate=applied_rate,
                monthlyInstallment=round(m, 2),
                newDTI=round(dti, 2),
                newLivingRemainder=round(lr, 2),
                decision=quick_decision(dti, lr),
                explanation=f"En réduisant le montant de 20%, la mensualité passe à {m:,.0f} {currency}/mois"
            ))

    # Scénario 2 : Allonger la durée de 24 mois
    if len(scenarios) < config.maxSimulationScenarios:
        longer_duration = application.loanDurationMonths + 24
        if loan_type_cfg is None or longer_duration <= loan_type_cfg.maxDurationMonths:
            m = calculate_monthly_installment(application.loanAmount, applied_rate, longer_duration)
            dti = ((total_current_charges + m) / total_income * 100) if total_income > 0 else 0
            lr = total_income - total_current_charges - m
            scenarios.append(SimulationScenario(
                id=sim_id(),
                label="Durée allongée de 24 mois",
                description=f"Allonger la durée à {longer_duration} mois",
                loanAmount=application.loanAmount,
                loanDurationMonths=longer_duration,
                annualInterestRate=applied_rate,
                monthlyInstallment=round(m, 2),
                newDTI=round(dti, 2),
                newLivingRemainder=round(lr, 2),
                decision=quick_decision(dti, lr),
                explanation=f"En allongeant de 24 mois, la mensualité baisse à {m:,.0f} {currency}/mois"
            ))

    # Scénario 3 : Montant réduit (-15%) + durée allongée (+12 mois)
    if len(scenarios) < config.maxSimulationScenarios:
        reduced_amount = application.loanAmount * 0.85
        longer_duration = application.loanDurationMonths + 12
        if (loan_type_cfg is None or (
            reduced_amount >= loan_type_cfg.minAmount and
            longer_duration <= loan_type_cfg.maxDurationMonths
        )):
            m = calculate_monthly_installment(reduced_amount, applied_rate, longer_duration)
            dti = ((total_current_charges + m) / total_income * 100) if total_income > 0 else 0
            lr = total_income - total_current_charges - m
            scenarios.append(SimulationScenario(
                id=sim_id(),
                label="Compromis : montant -15% et durée +12 mois",
                description=f"{reduced_amount:,.0f} {currency} sur {longer_duration} mois",
                loanAmount=reduced_amount,
                loanDurationMonths=longer_duration,
                annualInterestRate=applied_rate,
                monthlyInstallment=round(m, 2),
                newDTI=round(dti, 2),
                newLivingRemainder=round(lr, 2),
                decision=quick_decision(dti, lr),
                explanation=f"Compromis équilibré — mensualité {m:,.0f} {currency}/mois"
            ))

    return scenarios


# ════════════════════════════════════════════════════════════════════
# MOTEUR PRINCIPAL DE DÉCISION
# ════════════════════════════════════════════════════════════════════

def make_credit_decision(
    application: CreditApplicationInput,
    config: CreditPolicyConfigPublic
) -> CreditDecisionResult:
    """
    Point d'entrée principal du moteur de décision de crédit.

    Processus en 10 étapes :
    1. Récupération de la config du type de crédit
    2. Détermination du taux d'intérêt appliqué
    3. Calculs financiers (mensualité, DTI, LTV, LTI, reste à vivre)
    4. Évaluation des règles d'éligibilité
    5. Vérification des limites du type de crédit
    6. Évaluation des ratios de risque
    7. Calcul du score de crédit (si activé)
    8. Décision finale selon la stratégie configurée
    9. Construction des points forts / faibles / conditions
    10. Génération des simulations alternatives

    Args:
        application : données de la demande de crédit saisies par l'utilisateur
        config      : configuration active de la politique de crédit de l'organisation

    Returns:
        CreditDecisionResult avec tous les résultats, ratios, décision et simulations
    """
    # ── 1. Config du type de crédit ──────────────────────────────────
    loan_type_key = application.loanType.upper()
    loan_type_cfg = config.loanTypes.get(loan_type_key) or config.loanTypes.get(application.loanType)

    # ── 2. Taux d'intérêt ────────────────────────────────────────────
    applied_rate = _get_effective_rate(application, loan_type_cfg)

    # ── 3. Calculs financiers ────────────────────────────────────────
    total_income = application.netMonthlySalary + application.otherMonthlyIncome
    existing_monthly = sum(loan.monthlyPayment for loan in application.existingLoans)
    total_current_charges = application.rentOrMortgage + application.otherMonthlyCharges + existing_monthly

    monthly_installment = calculate_monthly_installment(
        application.loanAmount, applied_rate, application.loanDurationMonths
    )
    total_amount = monthly_installment * application.loanDurationMonths
    total_interest = max(0, total_amount - application.loanAmount)

    new_total_charges = total_current_charges + monthly_installment
    current_dti = (total_current_charges / total_income * 100) if total_income > 0 else 0.0
    new_dti = (new_total_charges / total_income * 100) if total_income > 0 else 0.0
    living_remainder = total_income - new_total_charges

    # LTV (uniquement pour crédits immobiliers)
    ltv = None
    if application.propertyValue and application.propertyValue > 0 and loan_type_key in ["IMMO", "IMMOBILIER"]:
        ltv = (application.loanAmount / application.propertyValue) * 100

    # LTI (montant / revenu annuel)
    annual_income = total_income * 12
    lti = (application.loanAmount / annual_income) if annual_income > 0 else 0.0

    # Ancienneté
    seniority = calculate_seniority_months(application.employmentStartDate)

    # ── 4. Règles d'éligibilité ──────────────────────────────────────
    eligibility_rules = _evaluate_eligibility_rules(application, config, seniority, total_income)

    # ── 5. Limites type de crédit ────────────────────────────────────
    loan_type_rules = _evaluate_loan_type_rules(application, config, loan_type_cfg)

    # ── 6. Ratios de risque ──────────────────────────────────────────
    ratio_details, ratio_rules = _evaluate_ratio_rules(
        config, new_dti, living_remainder, ltv, lti, total_income
    )

    # Consolidation des règles
    all_rules = eligibility_rules + loan_type_rules + ratio_rules

    # ── 7. Score de crédit ───────────────────────────────────────────
    credit_score = None
    if config.scoring.enabled:
        credit_score = _calculate_credit_score(
            application, config, new_dti, living_remainder, ltv, lti, seniority, total_income
        )

    # ── 8. Décision finale ───────────────────────────────────────────
    has_blocking = any(r.impact == "BLOQUANT" for r in all_rules)
    has_penalizing = any(r.impact == "PENALISANT" for r in all_rules)

    if config.decisionStrategy == "RULES_ONLY":
        if has_blocking:
            final_decision = "REFUSE"
            main_reason = next((r.message for r in all_rules if r.impact == "BLOQUANT"), "Règle bloquante déclenchée")
        elif has_penalizing:
            final_decision = "CONDITIONNEL"
            main_reason = "Points à améliorer pour une approbation complète"
        else:
            final_decision = "APPROUVE"
            main_reason = "Tous les critères d'éligibilité et ratios sont satisfaits"

    elif config.decisionStrategy == "SCORING_ONLY" and credit_score is not None:
        sc = config.scoring
        if credit_score >= sc.approvalScore:
            final_decision = "APPROUVE"
            main_reason = f"Score de crédit satisfaisant ({credit_score:.0f}/100)"
        elif credit_score >= sc.conditionalScore:
            final_decision = "CONDITIONNEL"
            main_reason = f"Score de crédit en zone intermédiaire ({credit_score:.0f}/100)"
        else:
            final_decision = "REFUSE"
            main_reason = f"Score de crédit insuffisant ({credit_score:.0f}/100)"

    else:  # HYBRID : règles bloquantes prioritaires, score pour nuancer
        if has_blocking:
            final_decision = "REFUSE"
            main_reason = next((r.message for r in all_rules if r.impact == "BLOQUANT"), "Règle bloquante déclenchée")
        elif credit_score is not None:
            sc = config.scoring
            if credit_score >= sc.approvalScore and not has_penalizing:
                final_decision = "APPROUVE"
                main_reason = f"Profil favorable — Score {credit_score:.0f}/100, ratios dans les normes"
            elif credit_score >= sc.conditionalScore:
                final_decision = "CONDITIONNEL"
                main_reason = f"Profil à examiner — Score {credit_score:.0f}/100"
            else:
                final_decision = "REFUSE"
                main_reason = f"Score insuffisant ({credit_score:.0f}/100) et critères non satisfaits"
        else:
            if has_penalizing:
                final_decision = "CONDITIONNEL"
                main_reason = "Points à améliorer détectés"
            else:
                final_decision = "APPROUVE"
                main_reason = "Critères d'éligibilité satisfaits"

    # ── 9. Points forts / faibles / conditions ───────────────────────
    strengths = [r.message for r in all_rules if r.impact == "FAVORABLE"]
    weaknesses = [r.message for r in all_rules if r.impact == "BLOQUANT"]
    weaknesses += [r.message for r in all_rules if r.impact == "PENALISANT"]

    conditions = []
    if final_decision == "CONDITIONNEL":
        if config.ratios.dti.enabled and new_dti > config.ratios.dti.approvalThreshold:
            conditions.append(
                f"Réduire le taux d'endettement en dessous de {config.ratios.dti.approvalThreshold}% "
                f"(actuellement {new_dti:.1f}%)"
            )
        if config.ratios.livingRemainder.enabled and living_remainder < config.ratios.livingRemainder.minimumAmount:
            conditions.append(
                f"Augmenter le reste à vivre mensuel au-dessus de "
                f"{config.ratios.livingRemainder.minimumAmount:,.0f} {config.currency}"
            )
        if seniority < config.eligibility.minimumEmploymentMonths:
            conditions.append(
                f"Atteindre {config.eligibility.minimumEmploymentMonths} mois d'ancienneté "
                f"(actuellement {seniority} mois)"
            )
        if application.isOnProbation:
            conditions.append("Attendre la fin de la période d'essai")

    # ── 10. Simulations ──────────────────────────────────────────────
    simulations = []
    if config.simulations.enabled and final_decision != "APPROUVE" and total_income > 0:
        try:
            simulations = _generate_simulations(
                application, config, applied_rate, total_income, total_current_charges
            )
            simulations = simulations[:config.maxSimulationScenarios]
        except Exception as e:
            logger.error(f"Erreur génération simulations: {e}")

    return CreditDecisionResult(
        appliedRate=applied_rate,
        monthlyInstallment=round(monthly_installment, 2),
        totalAmount=round(total_amount, 2),
        totalInterest=round(total_interest, 2),
        currentDTI=round(current_dti, 2),
        newDTI=round(new_dti, 2),
        livingRemainder=round(living_remainder, 2),
        ltv=round(ltv, 2) if ltv is not None else None,
        lti=round(lti, 4),
        creditScore=credit_score,
        jobSeniorityMonths=seniority,
        totalMonthlyIncome=round(total_income, 2),
        totalCurrentCharges=round(total_current_charges, 2),
        ratioDetails=ratio_details,
        decision=final_decision,
        mainReason=main_reason,
        strategy=config.decisionStrategy,
        configVersion=config.version,
        triggeredRules=all_rules,
        strengths=strengths,
        weaknesses=weaknesses,
        conditions=conditions,
        simulations=simulations,
        analyzedAt=datetime.utcnow().isoformat(),
        applicationId=str(uuid.uuid4())
    )
