"""
Service pour calculer les métriques et ratios d'une demande de crédit PME/PMI.
"""
from typing import Optional
from app.schemas.credit_pme import CreditPMERequest, PMECalculatedMetrics, FinancialDataYear


def calculate_caf(ebitda: float, resultat_net: float, charges_financieres: float) -> float:
    """
    Calcule la CAF (Capacité d'Autofinancement) approximative.
    CAF ≈ EBITDA - Impôts (approximation basée sur résultat net)
    """
    # Approximation: CAF = EBITDA - (Résultat net - EBITDA + charges financières) * taux_impot
    # Simplification: CAF ≈ EBITDA si on néglige les ajustements
    # Pour plus de précision, on peut utiliser: CAF = Résultat net + Amortissements
    # Ici, on utilise une approximation: CAF ≈ EBITDA * 0.85 (pour tenir compte des impôts)
    # Ou mieux: CAF = EBITDA - charges financières + résultat net (si positif)
    if ebitda > 0:
        # Approximation: CAF proche de l'EBITDA après impôts
        return ebitda * 0.75  # Approximation conservatrice
    return ebitda


def calculate_pme_metrics(
    request: CreditPMERequest,
    annual_interest_rate: float = 0.05  # 5% par défaut
) -> PMECalculatedMetrics:
    """
    Calcule toutes les métriques d'une demande de crédit PME.
    
    Args:
        request: La demande de crédit PME
        annual_interest_rate: Taux d'intérêt annuel pour calculer la mensualité
    
    Returns:
        PMECalculatedMetrics avec tous les calculs
    """
    # Trier les données financières par année (plus récentes en premier)
    financial_data = sorted(request.donnees_financieres, key=lambda x: x.year, reverse=True)
    
    if len(financial_data) < 1:
        raise ValueError("Au moins une année de données financières est requise")
    
    # Données de l'année la plus récente
    latest = financial_data[0]
    
    # Calculer la mensualité du nouveau crédit (formule d'annuité)
    monthly_rate = annual_interest_rate / 12
    if monthly_rate > 0:
        nouvelle_mensualite = request.montant * (
            monthly_rate * (1 + monthly_rate) ** request.duree_mois
        ) / ((1 + monthly_rate) ** request.duree_mois - 1)
    else:
        nouvelle_mensualite = request.montant / request.duree_mois
    
    # ===================== Ratios de performance =====================
    
    # Croissance CA
    croissance_ca = None
    if len(financial_data) >= 2:
        ca_n = latest.chiffre_affaires
        ca_n1 = financial_data[1].chiffre_affaires
        if ca_n1 > 0:
            croissance_ca = ((ca_n - ca_n1) / ca_n1) * 100
    
    # Marge EBITDA
    ebitda_margin = None
    if latest.chiffre_affaires > 0:
        ebitda_margin = (latest.ebitda / latest.chiffre_affaires) * 100
    
    # Marge nette
    net_margin = None
    if latest.chiffre_affaires > 0:
        net_margin = (latest.resultat_net / latest.chiffre_affaires) * 100
    
    # ===================== Endettement =====================
    
    # Debt/Equity (Gearing)
    debt_to_equity = None
    if latest.fonds_propres > 0:
        debt_to_equity = (latest.dettes_financieres_totales / latest.fonds_propres) * 100
    
    # Debt/EBITDA
    debt_to_ebitda = None
    if latest.ebitda != 0:
        debt_to_ebitda = latest.dettes_financieres_totales / abs(latest.ebitda)
    
    # ===================== Capacité de remboursement =====================
    
    # Interest Coverage (EBITDA / charges financières)
    interest_coverage = None
    if latest.charges_financieres > 0:
        interest_coverage = latest.ebitda / latest.charges_financieres
    
    # CAF annuelle
    caf_annuelle = calculate_caf(latest.ebitda, latest.resultat_net, latest.charges_financieres)
    
    # Service annuel de la dette (charges financières + remboursement principal annuel)
    service_annuel_dette_existante = latest.charges_financieres  # Approximation
    service_annuel_nouveau_credit = nouvelle_mensualite * 12
    service_annuel_dette_totale = service_annuel_dette_existante + service_annuel_nouveau_credit
    
    # Debt Service Coverage (CAF / service annuel dette)
    debt_service_coverage = None
    if service_annuel_dette_totale > 0:
        debt_service_coverage = caf_annuelle / service_annuel_dette_totale
    
    # Poids de la nouvelle échéance dans la CAF
    new_installment_weight = None
    if caf_annuelle > 0:
        new_installment_weight = (service_annuel_nouveau_credit / caf_annuelle) * 100
    
    # ===================== Liquidité =====================
    
    # Current Ratio (actif courant / passif courant)
    # Approximation: actif courant ≈ trésorerie + stocks + créances
    # passif courant ≈ dettes fournisseurs + dettes court terme
    current_ratio = None
    if latest.stocks is not None and latest.creances_clients is not None and latest.dettes_fournisseurs is not None:
        actif_courant = latest.tresorerie + latest.stocks + latest.creances_clients
        passif_courant = latest.dettes_fournisseurs  # Approximation
        if passif_courant > 0:
            current_ratio = actif_courant / passif_courant
    
    # Quick Ratio (actif courant - stocks) / passif courant
    quick_ratio = None
    if latest.stocks is not None and latest.creances_clients is not None and latest.dettes_fournisseurs is not None:
        actif_courant_quick = latest.tresorerie + latest.creances_clients
        passif_courant = latest.dettes_fournisseurs
        if passif_courant > 0:
            quick_ratio = actif_courant_quick / passif_courant
    
    # ===================== Garanties =====================
    
    # LTV (Loan-to-Value)
    ltv = None
    if request.valeur_garanties and request.valeur_garanties > 0:
        ltv = (request.montant / request.valeur_garanties) * 100
    
    return PMECalculatedMetrics(
        croissance_ca=round(croissance_ca, 2) if croissance_ca is not None else None,
        ebitda_margin=round(ebitda_margin, 2) if ebitda_margin is not None else None,
        net_margin=round(net_margin, 2) if net_margin is not None else None,
        debt_to_equity=round(debt_to_equity, 2) if debt_to_equity is not None else None,
        debt_to_ebitda=round(debt_to_ebitda, 2) if debt_to_ebitda is not None else None,
        interest_coverage=round(interest_coverage, 2) if interest_coverage is not None else None,
        debt_service_coverage=round(debt_service_coverage, 2) if debt_service_coverage is not None else None,
        new_installment_weight=round(new_installment_weight, 2) if new_installment_weight is not None else None,
        current_ratio=round(current_ratio, 2) if current_ratio is not None else None,
        quick_ratio=round(quick_ratio, 2) if quick_ratio is not None else None,
        ltv=round(ltv, 2) if ltv is not None else None,
        caf_annuelle=round(caf_annuelle, 2),
        nouvelle_mensualite=round(nouvelle_mensualite, 2),
        service_annuel_dette=round(service_annuel_dette_totale, 2),
    )

