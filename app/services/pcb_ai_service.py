"""
Service IA pour l'interprétation des rapports financiers PCB UEMOA
"""
import os
from typing import Dict
from app.core.config import settings

# Initialiser le client OpenAI si disponible
try:
    from openai import OpenAI
    
    if hasattr(settings, 'OPENAI_API_KEY') and settings.OPENAI_API_KEY:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
    else:
        client = None
except ImportError:
    client = None


async def generer_interpretation_ia(
    type_rapport: str,
    structure: Dict,
    ratios: Dict,
    date_cloture: str = None
) -> str:
    """
    Génère une interprétation IA des rapports financiers et ratios bancaires
    """
    if not client:
        return "⚠️ Analyse IA non disponible : clé API OpenAI non configurée. Veuillez configurer OPENAI_API_KEY dans le fichier .env"
    
    try:
        # Préparer le contexte
        postes_summary = []
        for poste in structure.get("postes", [])[:20]:  # Limiter à 20 postes pour le contexte
            postes_summary.append(f"- {poste.get('code', '')} {poste.get('libelle', '')}: {poste.get('solde', 0):,.0f} XOF")
        
        totaux = structure.get("totaux", {})
        
        # Préparer le prompt
        system_prompt = """Tu es un expert en analyse financière bancaire spécialisé dans le PCB UEMOA (Plan Comptable Bancaire de l'UEMOA).
Tu analyses les états financiers des banques et fournis des interprétations professionnelles, précises et actionnables.
Tu dois identifier les points forts, les points de vigilance, et proposer des recommandations concrètes.
Utilise un langage professionnel mais accessible, adapté au contexte bancaire UEMOA."""

        def _format_ratio_line(key: str, value) -> str:
            if value is None:
                return ""

            if isinstance(value, (int, float)):
                return f"- {key}: {value}"

            if isinstance(value, dict):
                if "valeur" in value:
                    unite = value.get("unite") or ""
                    statut = value.get("statut")
                    seuil_min = value.get("seuil_min")
                    seuil_max = value.get("seuil_max")
                    parts = [f"valeur={value.get('valeur')} {unite}".strip()]
                    if statut is not None:
                        parts.append(f"statut={statut}")
                    if seuil_min is not None:
                        parts.append(f"seuil_min={seuil_min}")
                    if seuil_max is not None:
                        parts.append(f"seuil_max={seuil_max}")
                    libelle = value.get("libelle")
                    lib = f" ({libelle})" if libelle else ""
                    return f"- {key}{lib}: " + ", ".join(parts)

                # ratios de gestion ou autres structures
                keys = ["n_1", "realisation_reference", "realisation_cloture", "evolution", "evolution_pct", "unite", "libelle"]
                compact = {k: value.get(k) for k in keys if k in value and value.get(k) is not None}
                if compact:
                    return f"- {key}: {compact}"

            return f"- {key}: {value}"

        ratios_lines = []
        for k, v in (ratios or {}).items():
            line = _format_ratio_line(k, v)
            if line:
                ratios_lines.append(line)

        user_prompt = f"""Analyse ce rapport financier bancaire selon le PCB UEMOA :

TYPE DE RAPPORT : {type_rapport.upper()}
DATE DE CLÔTURE : {date_cloture or 'Non spécifiée'}

POSTES PRINCIPAUX :
{chr(10).join(postes_summary)}

TOTAUX :
{chr(10).join([f"- {k}: {v:,.0f} XOF" if isinstance(v, (int, float)) else f"- {k}: {v}" for k, v in totaux.items()])}

RATIOS BANCAIRES CALCULÉS :
{chr(10).join(ratios_lines)}

Fournis une analyse structurée incluant :
1. SYNTHÈSE EXÉCUTIVE (2-3 phrases)
2. POINTS FORTS (3-5 points)
3. POINTS DE VIGILANCE (3-5 points)
4. ANALYSE DES RATIOS (interprétation de chaque ratio avec seuils réglementaires)
5. RECOMMANDATIONS (3-5 recommandations actionnables)

Format : Texte structuré, professionnel, adapté au contexte bancaire UEMOA."""

        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        interpretation = response.choices[0].message.content.strip()
        return interpretation
        
    except Exception as e:
        return f"⚠️ Erreur lors de la génération de l'analyse IA : {str(e)}. Veuillez vérifier la configuration de l'API OpenAI."

