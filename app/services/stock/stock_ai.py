from typing import List, Dict, Optional
from app.services.ai_service import client
from app.models.stock.consommable import list_consommables_by_org
from app.services.stock.stock_analytics import get_consumption_data, get_top_consumables


async def analyze_stock_prediction(org_id: str, consommable_id: Optional[str] = None) -> Dict:
    """
    Utilise l'IA pour prédire la consommation future.
    """
    if not client:
        return {"error": "Service IA non disponible"}
    
    try:
        # Récupérer les données historiques
        consumption_data = await get_consumption_data(org_id, days=90)
        
        if not consumption_data:
            return {"error": "Pas assez de données historiques"}
        
        # Préparer les données pour l'IA
        data_summary = []
        for item in consumption_data[-30:]:  # Derniers 30 jours
            data_summary.append(f"Date: {item['date']}, Quantité: {item['quantite']}, Demandes: {item['nombre_demandes']}")
        
        prompt = f"""
Analyse les données de consommation suivantes et prédit les besoins pour les 3 prochains mois.

Données historiques (30 derniers jours):
{chr(10).join(data_summary)}

Fournis une prédiction avec:
1. Estimation de consommation mensuelle pour les 3 prochains mois
2. Niveau de confiance (faible/moyen/élevé)
3. Recommandations de réapprovisionnement
4. Facteurs de risque identifiés

Format de réponse en JSON:
{{
    "prediction_3_mois": {{
        "mois_1": {{"quantite": X, "confiance": "moyen"}},
        "mois_2": {{"quantite": Y, "confiance": "moyen"}},
        "mois_3": {{"quantite": Z, "confiance": "faible"}}
    }},
    "recommandations": ["recommandation1", "recommandation2"],
    "facteurs_risque": ["facteur1", "facteur2"]
}}
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Tu es un expert en analyse de stock et prévision de demande."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
        )
        
        result_text = response.choices[0].message.content
        
        # Essayer de parser le JSON de la réponse
        import json
        import re
        
        # Extraire le JSON de la réponse
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = {"raw_response": result_text}
        
        return result
        
    except Exception as e:
        return {"error": f"Erreur lors de l'analyse: {str(e)}"}


async def detect_anomalies(org_id: str) -> List[Dict]:
    """
    Détecte les anomalies dans la consommation.
    """
    if not client:
        return []
    
    try:
        consumption_data = await get_consumption_data(org_id, days=60)
        
        if len(consumption_data) < 7:
            return []
        
        # Calculer les moyennes et écarts-types
        quantites = [item["quantite"] for item in consumption_data]
        moyenne = sum(quantites) / len(quantites)
        variance = sum((x - moyenne) ** 2 for x in quantites) / len(quantites)
        ecart_type = variance ** 0.5
        
        anomalies = []
        
        # Détecter les valeurs aberrantes (> 2 écarts-types)
        for item in consumption_data:
            if item["quantite"] > moyenne + 2 * ecart_type:
                anomalies.append({
                    "date": item["date"],
                    "type": "pic_consommation",
                    "valeur": item["quantite"],
                    "moyenne": round(moyenne, 2),
                    "message": f"Pic de consommation détecté: {item['quantite']} unités (moyenne: {round(moyenne, 2)})"
                })
            elif item["quantite"] < moyenne - 2 * ecart_type and item["quantite"] > 0:
                anomalies.append({
                    "date": item["date"],
                    "type": "baisse_consommation",
                    "valeur": item["quantite"],
                    "moyenne": round(moyenne, 2),
                    "message": f"Baisse significative de consommation: {item['quantite']} unités (moyenne: {round(moyenne, 2)})"
                })
        
        return anomalies
        
    except Exception as e:
        return [{"error": f"Erreur lors de la détection: {str(e)}"}]


async def get_ai_recommendations(org_id: str) -> List[str]:
    """
    Génère des recommandations intelligentes basées sur l'analyse du stock.
    """
    if not client:
        return []
    
    try:
        consommables = await list_consommables_by_org(org_id)
        top_consumables = await get_top_consumables(org_id, limit=5)
        low_stock = await get_consommables_low_stock(org_id)
        
        # Préparer le contexte
        context = f"""
Analyse la situation du stock suivante et fournis des recommandations concrètes:

Consommables en stock faible ({len(low_stock)}):
{chr(10).join([f"- {c['type']}: {c['quantite_stock']} {c['unite']} (limite: {c['limite_alerte']})" for c in low_stock[:5]])}

Top 5 consommables les plus demandés:
{chr(10).join([f"- {c['type']}: {c['total_quantite']} unités consommées" for c in top_consumables])}

Fournis 5 recommandations prioritaires et actionnables pour optimiser la gestion du stock.
Format: Liste numérotée de recommandations concises.
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Tu es un expert en gestion de stock et optimisation des approvisionnements."},
                {"role": "user", "content": context}
            ],
            temperature=0.5,
        )
        
        recommendations_text = response.choices[0].message.content
        
        # Extraire les recommandations (format liste numérotée)
        import re
        recommendations = re.findall(r'\d+\.\s*(.+?)(?=\d+\.|$)', recommendations_text, re.DOTALL)
        
        if not recommendations:
            # Fallback: diviser par lignes
            recommendations = [line.strip() for line in recommendations_text.split('\n') if line.strip() and not line.strip().startswith('#')]
        
        return recommendations[:5]  # Limiter à 5 recommandations
        
    except Exception as e:
        return [f"Erreur lors de la génération des recommandations: {str(e)}"]

