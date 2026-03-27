"""
Moteur de décision déterministe pour les crédits PME/PMI.
Aucune dépendance à une IA externe — décision basée uniquement sur la politique configurée.
"""
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.schemas.credit_pme_policy import (
    PMEPolicyConfig,
    PMEApplicationInput,
    PMEDecisionResult,
    PMECalculatedIndicators,
    PMERatioDetail,
    PMETriggeredRule,
    PMESimulationScenario,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _monthly_installment(principal: float, annual_rate_pct: float, months: int) -> float:
    if months <= 0 or principal <= 0:
        return 0.0
    if annual_rate_pct <= 0:
        return principal / months
    r = annual_rate_pct / 100 / 12
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def _ratio_status(value: float, approval: Optional[float], rejection: Optional[float], higher_is_better: bool) -> str:
    if approval is None:
        return "NA"
    if higher_is_better:
        if value >= approval:
            return "FAVORABLE"
        if rejection is not None and value < rejection:
            return "BLOQUANT"
        return "CONDITIONNEL"
    else:
        if value <= approval:
            return "FAVORABLE"
        if rejection is not None and value > rejection:
            return "BLOQUANT"
        return "CONDITIONNEL"


def _make_ratio(label: str, value: float, unit: str, approval: Optional[float],
                rejection: Optional[float], higher_is_better: bool, message: str) -> PMERatioDetail:
    return PMERatioDetail(
        label=label, value=round(value, 2), unit=unit,
        status=_ratio_status(value, approval, rejection, higher_is_better),
        message=message,
        threshold_approval=approval,
        threshold_rejection=rejection,
    )


# ── Calcul des indicateurs ─────────────────────────────────────────────────────

def _compute_indicators(
    app: PMEApplicationInput,
    policy: PMEPolicyConfig,
    annual_rate_pct: float,
) -> PMECalculatedIndicators:
    ind = PMECalculatedIndicators()
    cur_year = datetime.utcnow().year
    ind.company_age_years = max(0.0, float(cur_year - app.annee_creation))

    fin = sorted(app.donnees_financieres, key=lambda y: y.year, reverse=True)
    if not fin:
        return ind

    latest = fin[0]
    ind.ca_n = latest.ca
    ind.resultat_net_n = latest.resultat_net
    ind.ebitda_n = latest.ebitda
    ind.fonds_propres_n = latest.fonds_propres
    ind.endettement_n = latest.endettement_total
    ind.tresorerie_n = latest.tresorerie

    if len(fin) >= 2:
        ind.ca_n1 = fin[1].ca
        if fin[1].ca and fin[1].ca > 0 and latest.ca is not None:
            ind.ca_growth_pct = round((latest.ca - fin[1].ca) / fin[1].ca * 100, 1)

    if latest.ebitda is not None and latest.ca and latest.ca > 0:
        ind.ebitda_margin_pct = round(latest.ebitda / latest.ca * 100, 1)

    if latest.fonds_propres and latest.fonds_propres > 0 and latest.endettement_total is not None:
        ind.debt_equity_ratio = round(latest.endettement_total / latest.fonds_propres, 2)

    # Mensualité & DSCR
    rate = app.taux_annuel_pct if app.taux_annuel_pct else annual_rate_pct
    mensualite = _monthly_installment(app.montant_demande, rate, app.duree_mois)
    ind.nouvelle_mensualite = round(mensualite, 0)
    annuite_nouvelle = mensualite * 12
    annuites_existantes = app.annuites_existantes_annuelles or 0
    ind.annuite_annuelle = round(annuites_existantes + annuite_nouvelle, 0)

    if latest.ebitda is not None:
        caf = latest.ebitda * 0.75
        total_service = annuites_existantes + annuite_nouvelle
        if total_service > 0:
            ind.dscr = round(caf / total_service, 2)

    if ind.tresorerie_n is not None and ind.annuite_annuelle and ind.annuite_annuelle > 0:
        monthly_svc = ind.annuite_annuelle / 12
        if monthly_svc > 0:
            ind.treasury_coverage_months = round(ind.tresorerie_n / monthly_svc, 1)

    if app.garanties_prevues and app.valeur_retenue_garantie and app.valeur_retenue_garantie > 0 and app.montant_demande > 0:
        haircut = policy.guarantees.haircut_pct / 100
        val_nette = app.valeur_retenue_garantie * (1 - haircut)
        ind.guarantee_coverage_pct = round(val_nette / app.montant_demande * 100, 1)

    # Complétude financière
    fin_fields = [latest.ca, latest.resultat_net, latest.ebitda, latest.fonds_propres,
                  latest.endettement_total, latest.tresorerie]
    filled = sum(1 for f in fin_fields if f is not None)
    ind.financial_completeness_score = round(filled / len(fin_fields) * 100, 0)

    # Complétude documentaire
    docs = app.documents
    if docs:
        mandatory = [d for d in docs if d.obligatoire]
        if mandatory:
            provided = sum(1 for d in mandatory if d.fourni)
            ind.document_completeness_score = round(provided / len(mandatory) * 100, 0)
        else:
            provided = sum(1 for d in docs if d.fourni)
            ind.document_completeness_score = round(provided / len(docs) * 100, 0)
    else:
        ind.document_completeness_score = 100.0

    # Score gouvernance
    gov = 50.0
    if app.experience_secteur_ans >= policy.governance.min_manager_seniority_years:
        gov += policy.governance.manager_experience_bonus
    if app.equipe_structuree:
        gov += policy.governance.structured_team_bonus
    if not app.gouvernance_formelle:
        gov += policy.governance.weak_governance_penalty
    ind.governance_score = round(max(0.0, min(100.0, gov)), 1)

    return ind


# ── Règles ─────────────────────────────────────────────────────────────────────

def _apply_rules(
    app: PMEApplicationInput,
    ind: PMECalculatedIndicators,
    policy: PMEPolicyConfig,
) -> Tuple[List[PMETriggeredRule], List[str], List[str], List[str], List[str], List[str]]:
    rules: List[PMETriggeredRule] = []
    strengths: List[str] = []
    weaknesses: List[str] = []
    conditions: List[str] = []
    missing_docs: List[str] = []
    risks: List[str] = []

    elig = policy.eligibility

    # B. Éligibilité
    if ind.company_age_years < elig.conditional_company_age_years:
        rules.append(PMETriggeredRule(code="ELIG_AGE_BLOQUANT", section="Eligibilite", impact="BLOQUANT",
            message=f"Anciennete insuffisante ({ind.company_age_years:.1f} ans < {elig.conditional_company_age_years} requis)"))
    elif ind.company_age_years < elig.min_company_age_years:
        rules.append(PMETriggeredRule(code="ELIG_AGE_COND", section="Eligibilite", impact="PENALISANT",
            message=f"Anciennete en dessous du seuil optimal ({ind.company_age_years:.1f} ans)"))
    else:
        strengths.append(f"Anciennete entreprise satisfaisante ({ind.company_age_years:.0f} ans)")

    if elig.rejected_legal_forms and app.forme_juridique in elig.rejected_legal_forms:
        rules.append(PMETriggeredRule(code="ELIG_FORME_JURIDIQUE", section="Eligibilite", impact="BLOQUANT",
            message=f"Forme juridique '{app.forme_juridique}' non acceptee par la politique"))

    if elig.rejected_sectors and app.secteur in elig.rejected_sectors:
        rules.append(PMETriggeredRule(code="ELIG_SECTEUR_REJETE", section="Eligibilite", impact="BLOQUANT",
            message=f"Secteur '{app.secteur}' rejete par la politique"))
    elif elig.restricted_sectors and app.secteur in elig.restricted_sectors:
        rules.append(PMETriggeredRule(code="ELIG_SECTEUR_RESTREINT", section="Eligibilite", impact="PENALISANT",
            message=f"Secteur '{app.secteur}' soumis a conditions particulieres"))
        conditions.append("Secteur restreint : fournir justificatifs specifiques au secteur")

    if elig.require_structured_team_for_large and app.montant_demande >= elig.large_amount_threshold and not app.equipe_structuree:
        rules.append(PMETriggeredRule(code="ELIG_EQUIPE", section="Eligibilite", impact="BLOQUANT",
            message=f"Equipe structuree requise pour montants >= {elig.large_amount_threshold:,.0f}"))

    # C. Seuils financiers
    thr = policy.financial_thresholds
    if ind.ca_n is not None and thr.min_ca > 0 and ind.ca_n < thr.min_ca:
        rules.append(PMETriggeredRule(code="FIN_CA_INSUFFISANT", section="Financier", impact="BLOQUANT",
            message=f"CA N ({ind.ca_n:,.0f}) inferieur au minimum requis ({thr.min_ca:,.0f})"))
        weaknesses.append("CA insuffisant par rapport au seuil minimal")

    if ind.resultat_net_n is not None and thr.min_resultat_net != 0 and ind.resultat_net_n < thr.min_resultat_net:
        impact = "BLOQUANT" if ind.resultat_net_n < 0 else "PENALISANT"
        rules.append(PMETriggeredRule(code="FIN_RESULTAT_FAIBLE", section="Financier", impact=impact,
            message=f"Resultat net N ({ind.resultat_net_n:,.0f}) inferieur au seuil ({thr.min_resultat_net:,.0f})"))
        weaknesses.append("Resultat net insuffisant")

    if not thr.allow_incomplete_financials and ind.financial_completeness_score < thr.min_financial_completeness_score:
        rules.append(PMETriggeredRule(code="FIN_COMPLETUDE", section="Financier", impact="BLOQUANT",
            message=f"Completude financiere insuffisante ({ind.financial_completeness_score:.0f}% < {thr.min_financial_completeness_score:.0f}% requis)"))

    # D. Ratios
    rat = policy.ratios
    if rat.enable_debt_equity and ind.debt_equity_ratio is not None:
        if ind.debt_equity_ratio > rat.max_debt_equity:
            rules.append(PMETriggeredRule(code="RATIO_DE_BLOQUANT", section="Ratios", impact="BLOQUANT",
                message=f"Ratio D/E ({ind.debt_equity_ratio:.2f}x) depasse le maximum ({rat.max_debt_equity}x)"))
            weaknesses.append(f"Endettement excessif (ratio D/E = {ind.debt_equity_ratio:.2f}x)")
        elif ind.debt_equity_ratio > rat.conditional_debt_equity:
            rules.append(PMETriggeredRule(code="RATIO_DE_COND", section="Ratios", impact="PENALISANT",
                message=f"Ratio D/E eleve ({ind.debt_equity_ratio:.2f}x > {rat.conditional_debt_equity}x)"))
        else:
            strengths.append(f"Levier financier maitrise (D/E = {ind.debt_equity_ratio:.2f}x)")

    if rat.enable_dscr and ind.dscr is not None:
        if ind.dscr < rat.conditional_dscr:
            rules.append(PMETriggeredRule(code="RATIO_DSCR_BLOQUANT", section="Ratios", impact="BLOQUANT",
                message=f"DSCR insuffisant ({ind.dscr:.2f}x < {rat.conditional_dscr}x - remboursement non couvert)"))
            weaknesses.append(f"Capacite de remboursement critique (DSCR = {ind.dscr:.2f}x)")
        elif ind.dscr < rat.min_dscr:
            rules.append(PMETriggeredRule(code="RATIO_DSCR_COND", section="Ratios", impact="PENALISANT",
                message=f"DSCR limite ({ind.dscr:.2f}x < {rat.min_dscr}x)"))
            conditions.append("Presenter un plan de tresorerie detaille (DSCR limite)")
        else:
            strengths.append(f"Bonne capacite de remboursement (DSCR = {ind.dscr:.2f}x)")

    if rat.enable_ca_trend and ind.ca_growth_pct is not None:
        if ind.ca_growth_pct < rat.min_ca_trend_pct:
            rules.append(PMETriggeredRule(code="RATIO_CA_TREND", section="Ratios", impact="PENALISANT",
                message=f"Tendance CA defavorable ({ind.ca_growth_pct:.1f}% < {rat.min_ca_trend_pct}%)"))
            weaknesses.append(f"CA en repli ({ind.ca_growth_pct:+.1f}%)")
        elif ind.ca_growth_pct >= 5:
            strengths.append(f"Croissance CA positive ({ind.ca_growth_pct:+.1f}%)")

    # E. Garanties
    guar = policy.guarantees
    if app.montant_demande >= guar.guarantee_required_above and not app.garanties_prevues:
        rules.append(PMETriggeredRule(code="GUAR_REQUIRED", section="Garanties", impact="BLOQUANT",
            message=f"Garantie obligatoire pour montants >= {guar.guarantee_required_above:,.0f}"))
        conditions.append("Fournir des garanties reelles ou personnelles")

    if app.garanties_prevues and ind.guarantee_coverage_pct is not None:
        if ind.guarantee_coverage_pct < guar.conditional_guarantee_coverage_pct:
            rules.append(PMETriggeredRule(code="GUAR_COVERAGE_FAIBLE", section="Garanties", impact="PENALISANT",
                message=f"Couverture garantie insuffisante ({ind.guarantee_coverage_pct:.0f}% < {guar.conditional_guarantee_coverage_pct:.0f}%)"))
            conditions.append(f"Renforcer les garanties (couverture actuelle : {ind.guarantee_coverage_pct:.0f}%)")
        elif ind.guarantee_coverage_pct >= guar.min_guarantee_coverage_pct:
            strengths.append(f"Garanties bien couvertes ({ind.guarantee_coverage_pct:.0f}%)")

    if app.garanties_prevues and guar.require_guarantee_docs and not app.documents_garantie_disponibles:
        conditions.append("Documents de garantie a fournir avant deblocage")

    # F. Bancarisation
    bank = policy.banking
    if bank.require_bank_relationship and app.anciennete_relation_bancaire_mois < bank.min_bank_relationship_months:
        rules.append(PMETriggeredRule(code="BANK_ANCIENNETE", section="Bancarisation",
            impact="BLOQUANT" if bank.require_bank_relationship else "PENALISANT",
            message=f"Anciennete relation bancaire insuffisante ({app.anciennete_relation_bancaire_mois} mois < {bank.min_bank_relationship_months} requis)"))

    if bank.enable_incident_penalty and app.niveau_incidents_bancaires > bank.max_incident_level:
        rules.append(PMETriggeredRule(code="BANK_INCIDENTS", section="Bancarisation", impact="BLOQUANT",
            message=f"Niveau incidents bancaires eleve ({app.niveau_incidents_bancaires} > {bank.max_incident_level} autorise)"))
        risks.append("Incidents bancaires signales")

    if app.client_existant:
        strengths.append("Client existant de l'etablissement")
    if app.flux_domicilies:
        strengths.append("Flux domicilies dans l'etablissement")

    # G. Risque commercial
    comm = policy.commercial_risk
    if comm.enable_client_concentration and app.dependance_client_majeur and app.part_plus_gros_client_pct:
        pct = app.part_plus_gros_client_pct
        if pct > comm.max_client_concentration_pct:
            rules.append(PMETriggeredRule(code="COMM_CLIENT_BLOQUANT", section="Risque commercial", impact="BLOQUANT",
                message=f"Concentration client excessive ({pct:.0f}% > {comm.max_client_concentration_pct:.0f}%)"))
            risks.append(f"Forte dependance a un client ({pct:.0f}% du CA)")
        elif pct > comm.conditional_client_concentration_pct:
            rules.append(PMETriggeredRule(code="COMM_CLIENT_COND", section="Risque commercial", impact="PENALISANT",
                message=f"Concentration client elevee ({pct:.0f}%)"))
            risks.append(f"Dependance client importante ({pct:.0f}% du CA)")

    if comm.enable_supplier_dependency and app.dependance_fournisseur_majeur and app.part_plus_gros_fournisseur_pct:
        pct = app.part_plus_gros_fournisseur_pct
        if pct > comm.max_supplier_dependency_pct:
            rules.append(PMETriggeredRule(code="COMM_FOURNISSEUR_BLOQUANT", section="Risque commercial", impact="BLOQUANT",
                message=f"Dependance fournisseur excessive ({pct:.0f}%)"))
            risks.append(f"Forte dependance a un fournisseur ({pct:.0f}% des achats)")

    # I. Documents
    doc_pol = policy.document_policy
    if doc_pol.enable_document_policy:
        if ind.document_completeness_score < doc_pol.min_document_completeness_score:
            impact = "BLOQUANT" if doc_pol.block_if_key_docs_missing else "PENALISANT"
            rules.append(PMETriggeredRule(code="DOC_COMPLETUDE", section="Documents", impact=impact,
                message=f"Completude documentaire insuffisante ({ind.document_completeness_score:.0f}% < {doc_pol.min_document_completeness_score:.0f}% requis)"))

        for doc_code in doc_pol.key_mandatory_docs:
            provided = any(d.code == doc_code and d.fourni for d in app.documents)
            if not provided:
                missing_docs.append(doc_code)
                if doc_pol.block_if_key_docs_missing:
                    rules.append(PMETriggeredRule(code=f"DOC_{doc_code}_MANQUANT", section="Documents",
                        impact="BLOQUANT", message=f"Document obligatoire manquant : {doc_code}"))

    if ind.document_completeness_score >= 90:
        strengths.append(f"Dossier documentaire complet ({ind.document_completeness_score:.0f}%)")

    return rules, strengths, weaknesses, conditions, missing_docs, risks


# ── Scoring ────────────────────────────────────────────────────────────────────

def _compute_score(
    app: PMEApplicationInput,
    ind: PMECalculatedIndicators,
    policy: PMEPolicyConfig,
) -> float:
    sc = policy.scoring
    bm = policy.bonus_malus
    w = sc.weights

    # Solidite financiere
    fin_s = 50.0
    if ind.fonds_propres_n and ind.fonds_propres_n > 0:
        fin_s += 10
    if ind.resultat_net_n and ind.resultat_net_n > 0:
        fin_s += 15
    if ind.ca_growth_pct is not None:
        fin_s += min(15, max(-20, ind.ca_growth_pct * 0.5))
    if ind.ebitda_margin_pct and ind.ebitda_margin_pct > 10:
        fin_s += 10

    # Capacite remboursement
    rem_s = 50.0
    if ind.dscr is not None:
        if ind.dscr >= 1.5:
            rem_s = 90
        elif ind.dscr >= 1.2:
            rem_s = 70
        elif ind.dscr >= 1.0:
            rem_s = 50
        else:
            rem_s = 20

    # Qualite garanties
    guar_s = 30.0
    if app.garanties_prevues:
        if ind.guarantee_coverage_pct and ind.guarantee_coverage_pct >= policy.guarantees.min_guarantee_coverage_pct:
            guar_s = 85
        elif ind.guarantee_coverage_pct:
            guar_s = 55

    # Risque activite
    act_s = 70.0
    if app.dependance_client_majeur and app.part_plus_gros_client_pct and app.part_plus_gros_client_pct > 30:
        act_s -= (app.part_plus_gros_client_pct - 30) * 0.5
    if app.dependance_fournisseur_majeur and app.part_plus_gros_fournisseur_pct and app.part_plus_gros_fournisseur_pct > 40:
        act_s -= (app.part_plus_gros_fournisseur_pct - 40) * 0.3

    # Gouvernance
    gov_s = ind.governance_score

    # Comportement bancaire
    bank_s = 60.0
    if app.client_existant:
        bank_s += bm.bonus_client_existant
    if app.flux_domicilies:
        bank_s += bm.bonus_domiciliation
    if app.comportement_remboursement == "BON":
        bank_s += bm.bonus_bon_historique_remboursement
    bank_s += bm.penalty_incidents_bancaires * app.niveau_incidents_bancaires

    # Completudes
    doc_s = ind.document_completeness_score
    fin_comp_s = ind.financial_completeness_score

    total_weight = (
        w.solidite_financiere + w.capacite_remboursement + w.qualite_garanties +
        w.risque_activite + w.gouvernance + w.comportement_bancaire +
        w.completude_documentaire + w.completude_financiere
    )
    if total_weight <= 0:
        return 50.0

    raw = (
        max(0, min(100, fin_s)) * w.solidite_financiere +
        max(0, min(100, rem_s)) * w.capacite_remboursement +
        max(0, min(100, guar_s)) * w.qualite_garanties +
        max(0, min(100, act_s)) * w.risque_activite +
        max(0, min(100, gov_s)) * w.gouvernance +
        max(0, min(100, bank_s)) * w.comportement_bancaire +
        max(0, min(100, doc_s)) * w.completude_documentaire +
        max(0, min(100, fin_comp_s)) * w.completude_financiere
    ) / total_weight

    return round(max(sc.score_min, min(sc.score_max, raw)), 1)


# ── Simulations ────────────────────────────────────────────────────────────────

def _build_simulations(
    app: PMEApplicationInput,
    policy: PMEPolicyConfig,
    annual_rate_pct: float,
    base_decision: str,
) -> List[PMESimulationScenario]:
    if not policy.general.enable_simulations:
        return []

    rate = app.taux_annuel_pct or annual_rate_pct
    base_amount = app.montant_demande
    base_duration = app.duree_mois
    sims = []

    # S1 : Montant réduit -20%
    a1 = base_amount * 0.80
    m1 = _monthly_installment(a1, rate, base_duration)
    sims.append(PMESimulationScenario(
        id=str(uuid.uuid4())[:8], label="Montant reduit -20%",
        description="Reduction du montant de 20% pour ameliorer les ratios",
        montant=a1, duree_mois=base_duration, mensualite=round(m1, 0),
        decision="APPROUVE" if base_decision != "REFUSE" else "CONDITIONNEL",
        explication="Reduire le montant ameliore le DSCR et le taux de couverture garantie",
    ))

    # S2 : Durée allongée +12 mois
    d2 = base_duration + 12
    m2 = _monthly_installment(base_amount, rate, d2)
    sims.append(PMESimulationScenario(
        id=str(uuid.uuid4())[:8], label=f"Duree allongee +12 mois ({d2} mois)",
        description="Extension de la duree pour reduire la mensualite",
        montant=base_amount, duree_mois=d2, mensualite=round(m2, 0),
        decision="CONDITIONNEL" if base_decision == "REFUSE" else base_decision,
        explication="Allonger la duree reduit la charge de remboursement mensuelle",
    ))

    # S3 : Apport augmenté
    if app.apport_personnel and app.apport_personnel > 0:
        apport_new = app.apport_personnel * 1.5
        a3 = max(0, base_amount - (apport_new - app.apport_personnel))
        m3 = _monthly_installment(a3, rate, base_duration)
        sims.append(PMESimulationScenario(
            id=str(uuid.uuid4())[:8], label="Apport augmente +50%",
            description="Augmentation de l'apport personnel de 50%",
            montant=a3, duree_mois=base_duration, mensualite=round(m3, 0),
            decision="APPROUVE",
            explication="Un apport plus eleve reduit le risque et le montant net finance",
        ))

    return sims[:policy.general.max_simulations]


# ── Point d'entrée ─────────────────────────────────────────────────────────────

def run_pme_decision_engine(
    application: PMEApplicationInput,
    policy: PMEPolicyConfig,
    annual_rate_pct: float = 10.0,
) -> PMEDecisionResult:
    """Moteur de décision PME déterministe. Retourne un PMEDecisionResult complet."""

    ind = _compute_indicators(application, policy, annual_rate_pct)
    rules, strengths, weaknesses, conditions, missing_docs, risks = _apply_rules(application, ind, policy)

    # Ratio details
    rat = policy.ratios
    ratio_details: Dict[str, PMERatioDetail] = {}

    if ind.debt_equity_ratio is not None and rat.enable_debt_equity:
        ratio_details["debt_equity"] = _make_ratio(
            "Dette / Fonds propres", ind.debt_equity_ratio, "x",
            rat.conditional_debt_equity, rat.max_debt_equity, False,
            "Mesure l'effet de levier financier (endettement / capitaux propres)")

    if ind.dscr is not None and rat.enable_dscr:
        ratio_details["dscr"] = _make_ratio(
            "DSCR", ind.dscr, "x",
            rat.min_dscr, rat.conditional_dscr, True,
            "Capacite de remboursement : CAF / service annuel de la dette")

    if ind.treasury_coverage_months is not None and rat.enable_treasury_coverage:
        ratio_details["treasury_coverage"] = _make_ratio(
            "Couverture tresorerie", ind.treasury_coverage_months, " mois",
            rat.min_treasury_months, None, True,
            "Mois de service de la dette couverts par la tresorerie disponible")

    if ind.guarantee_coverage_pct is not None:
        ratio_details["guarantee_coverage"] = _make_ratio(
            "Couverture garantie", ind.guarantee_coverage_pct, "%",
            policy.guarantees.min_guarantee_coverage_pct,
            policy.guarantees.conditional_guarantee_coverage_pct, True,
            "Valeur nette des garanties / montant du credit")

    if ind.ca_growth_pct is not None and rat.enable_ca_trend:
        ratio_details["ca_growth"] = _make_ratio(
            "Croissance CA", ind.ca_growth_pct, "%",
            rat.min_ca_trend_pct, None, True,
            "Evolution du chiffre d'affaires entre N-1 et N")

    # Score
    credit_score = None
    if policy.scoring.enabled:
        credit_score = _compute_score(application, ind, policy)

    # Décision
    strategy = policy.general.strategy
    blocking = [r for r in rules if r.impact == "BLOQUANT"]
    penalizing = [r for r in rules if r.impact == "PENALISANT"]

    if strategy == "RULES_ONLY":
        if blocking:
            decision = "REFUSE"
            main_reason = blocking[0].message
        elif penalizing:
            decision = "CONDITIONNEL"
            main_reason = f"{len(penalizing)} point(s) a surveiller"
        else:
            decision = "APPROUVE"
            main_reason = "Tous les criteres de la politique sont satisfaits"

    elif strategy == "SCORING_ONLY" and credit_score is not None:
        sc = policy.scoring
        if credit_score >= sc.score_approval:
            decision, main_reason = "APPROUVE", f"Score satisfaisant ({credit_score:.0f}/100)"
        elif credit_score >= sc.score_conditional:
            decision, main_reason = "CONDITIONNEL", f"Score limite ({credit_score:.0f}/100)"
        else:
            decision, main_reason = "REFUSE", f"Score insuffisant ({credit_score:.0f}/100)"

    else:  # HYBRID
        if blocking:
            decision = "REFUSE"
            main_reason = blocking[0].message
        elif credit_score is not None:
            sc = policy.scoring
            if credit_score >= sc.score_approval and not penalizing:
                decision, main_reason = "APPROUVE", f"Profil favorable - score {credit_score:.0f}/100"
            elif credit_score >= sc.score_conditional or (credit_score >= sc.score_approval and penalizing):
                decision, main_reason = "CONDITIONNEL", f"Dossier acceptable sous conditions - score {credit_score:.0f}/100"
            else:
                decision, main_reason = "REFUSE", f"Score insuffisant ({credit_score:.0f}/100)"
        else:
            if penalizing:
                decision, main_reason = "CONDITIONNEL", f"{len(penalizing)} point(s) a surveiller"
            else:
                decision, main_reason = "APPROUVE", "Criteres de politique satisfaits"

    simulations = _build_simulations(application, policy, annual_rate_pct, decision)

    return PMEDecisionResult(
        decision=decision,
        main_reason=main_reason,
        credit_score=credit_score,
        strategy=strategy,
        config_version=policy.general.policy_version,
        currency=policy.general.currency,
        indicators=ind,
        ratio_details=ratio_details,
        strengths=strengths,
        weaknesses=weaknesses,
        conditions=conditions,
        missing_documents=missing_docs,
        identified_risks=risks,
        triggered_rules=rules,
        simulations=simulations,
    )
