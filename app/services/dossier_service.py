"""
Service pour gérer les dossiers de crédit en base de données.
"""
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
import logging
from pydantic import ValidationError

# Initialiser la connexion MongoDB
client = None
db = None

if hasattr(settings, 'MONGO_URI'):
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB_NAME]


async def get_dossiers_disponibles() -> List[Dict[str, Any]]:
    """
    Récupère tous les dossiers de crédit disponibles.
    
    Returns:
        List des dossiers avec infos essentielles
    """
    try:
        if db is None:
            raise ValueError("Database not connected")
        
        # Récupérer les 10 dossiers les plus récents
        cursor = db.credit_particulier_requests.find({}).sort("created_at", -1).limit(10)
        dossiers = await cursor.to_list(length=10)
        
        # Formater pour l'affichage
        dossiers_formates = []
        for dossier in dossiers:
            request_data = dossier.get("request_data", {})
            calculated_metrics = dossier.get("calculated_metrics", {})
            
            dossier_formate = {
                "_id": str(dossier["_id"]),
                "client_name": request_data.get("clientName", "Client inconnu"),
                "montant": request_data.get("loanAmount", 0),
                "duree": request_data.get("loanDurationMonths", 0),
                "salaire": request_data.get("netMonthlySalary", 0),
                "decision": dossier.get("ai_decision", "EN_ATTENTE"),
                "date_creation": str(dossier.get("created_at", "")),
                "taux_endettement": calculated_metrics.get("newDebtToIncomeRatio", 0)
            }
            dossiers_formates.append(dossier_formate)
        
        logging.info(f"📂 {len(dossiers_formates)} dossiers récupérés")
        return dossiers_formates
        
    except Exception as e:
        logging.error(f"❌ Erreur lors de la récupération des dossiers: {str(e)}")
        raise


async def get_dossier_by_id(dossier_id: str) -> Optional[Dict[str, Any]]:
    """
    Récupère un dossier de crédit par son ID.
    
    Args:
        dossier_id: ID du dossier à récupérer
        
    Returns:
        Dict du dossier ou None si non trouvé
    """
    try:
        if db is None:
            raise ValueError("Database not connected")
        
        logging.info(f"🔍 Recherche du dossier: {dossier_id}")
        
        # Essayer avec ObjectId si l'ID ressemble à un ObjectId
        from bson import ObjectId
        try:
            object_id = ObjectId(dossier_id)
            filter_query = {"_id": object_id}
        except:
            # Si ce n'est pas un ObjectId valide, utiliser comme string
            filter_query = {"_id": dossier_id}
        
        # Chercher le dossier dans la collection credit_particulier_requests
        dossier_doc = await db.credit_particulier_requests.find_one(filter_query)
        
        if not dossier_doc:
            logging.warning(f"❌ Dossier non trouvé: {dossier_id}")
            return None
        
        # Convertir ObjectId en string
        if "_id" in dossier_doc:
            dossier_doc["_id"] = str(dossier_doc["_id"])
        
        logging.info(f"✅ Dossier trouvé: {dossier_doc.get('request_data', {}).get('clientName', 'N/A')}")
        
        # Transformer les données de credit_particulier_requests vers le format attendu
        request_data = dossier_doc.get("request_data", {})
        metrics = dossier_doc.get("calculated_metrics", {})
        
        dossier_transforme = {
            "_id": dossier_doc["_id"],
            "client": {
                "nom": request_data.get("clientName", "Client"),
                "email": "client@email.com",
                "profession": request_data.get("employmentStatus", "Non spécifié"),
                "employeur": request_data.get("employerName", "Non spécifié"),
                "anciennete": metrics.get("jobSeniorityMonths", 0) or 0,
                "contrat": request_data.get("contractType", "Non spécifié")
            },
            "revenus": {
                "salaire_net": request_data.get("netMonthlySalary", 0) or 0,
                "autres_revenus": request_data.get("otherMonthlyIncome", 0) or 0,
                "total_revenus": metrics.get("totalMonthlyIncome", 0) or 0
            },
            "charges": {
                "loyer": request_data.get("rentOrMortgage", 0) or 0,
                "autres_credits": sum(loan.get("monthlyPayment", 0) or 0 for loan in request_data.get("existingLoans", [])),
                "charges_familiales": request_data.get("otherMonthlyCharges", 0) or 0,
                "total_charges": metrics.get("totalMonthlyCharges", 0) or 0
            },
            "encours": [
                {
                    "banque": "Banque X",
                    "montant": (loan.get("monthlyPayment", 0) or 0) * 12,  # Estimation
                    "mensualite": loan.get("monthlyPayment", 0) or 0
                }
                for loan in request_data.get("existingLoans", [])
            ],
            "demande": {
                "montant": request_data.get("loanAmount", 0) or 0,
                "duree": request_data.get("loanDurationMonths", 0) or 0,
                "objet": request_data.get("loanType", "Non spécifié"),
                "taux": (metrics.get("annualInterestRate", 8.5) or 8.5) / 100
            },
            "garanties": {
                "type": "hypothèque" if (request_data.get("loanType", "") or "").upper() in ["IMMO", "IMMOBILIER"] else "aucune",
                "valeur": request_data.get("propertyValue", 0) or 0,
                "description": "Bien immobilier" if (request_data.get("propertyValue", 0) or 0) > 0 else "Aucune"
            },
            "historique": {
                "credits_precedents": len(request_data.get("existingLoans", [])),
                "incidents": 0,
                "score_banque_de_france": 750
            },
            "decision": {
                "statut": dossier_doc.get("ai_decision", "EN_ATTENTE") or "EN_ATTENTE",
                "score_risque": 50,
                "date_evaluation": str(dossier_doc.get("created_at", ""))
            },
            # Ajout des vraies données dynamiques
            "donnees_brutes": {
                "request_data": request_data,
                "calculated_metrics": metrics,
                "ai_analysis": dossier_doc.get("ai_analysis", ""),
                "ai_recommendations": dossier_doc.get("ai_recommendations", "")
            }
        }
        
        # Valider les champs essentiels
        validation_result = validate_dossier_complet(dossier_transforme)
        if not validation_result["valid"]:
            logging.warning(f"⚠️ Dossier incomplet: {validation_result['missing_fields']}")
            # On continue quand même mais on note les champs manquants
        
        return dossier_transforme
        
    except Exception as e:
        logging.error(f"❌ Erreur lors de la récupération du dossier: {str(e)}")
        raise


def validate_dossier_complet(dossier: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valide que les champs essentiels du dossier sont présents.
    
    Args:
        dossier: Dossier à valider
        
    Returns:
        Dict avec valid: bool et missing_fields: list
    """
    required_fields = [
        "client.nom",
        "demande.montant",
        "demande.duree",
        "revenus.total_revenus",
        "charges.total_charges"
    ]
    
    missing_fields = []
    
    for field in required_fields:
        keys = field.split(".")
        current = dossier
        
        try:
            for key in keys:
                current = current[key]
            if current is None or current == "":
                missing_fields.append(field)
        except (KeyError, TypeError):
            missing_fields.append(field)
    
    return {
        "valid": len(missing_fields) == 0,
        "missing_fields": missing_fields
    }


async def create_dossier_demo(dossier_id: str) -> Dict[str, Any]:
    """
    Plus besoin de dossier démo, on utilise les vrais dossiers.
    """
    raise ValueError("Utilisez un vrai dossier de credit_particulier_requests")
