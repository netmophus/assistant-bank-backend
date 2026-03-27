"""
Script pour migrer les anciennes analyses de crédit 
en ajoutant les champs manquants annualInterestRate et totalInterestPaid.
"""
import asyncio
from app.core.db import get_database
from app.services.credit_calculations import calculate_credit_metrics

async def migrate_credit_analyses():
    """Ajoute les champs manquants aux anciennes analyses de crédit"""
    db = get_database()
    
    # Récupérer toutes les analyses qui n'ont pas les nouveaux champs
    cursor = db["credit_particulier_requests"].find({
        "$or": [
            {"calculated_metrics.annualInterestRate": {"$exists": False}},
            {"calculated_metrics.totalInterestPaid": {"$exists": False}}
        ]
    })
    
    updated_count = 0
    
    async for doc in cursor:
        try:
            # Extraire les données de la demande
            request_data = doc.get("request_data", {})
            
            # Calculer les métriques manquantes avec un taux par défaut de 5%
            metrics = calculate_credit_metrics(
                request_data=request_data,
                annual_interest_rate=0.05  # 5% par défaut pour les anciennes analyses
            )
            
            # Mettre à jour le document
            await db["credit_particulier_requests"].update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "calculated_metrics.annualInterestRate": metrics.annualInterestRate,
                        "calculated_metrics.totalInterestPaid": metrics.totalInterestPaid
                    }
                }
            )
            
            updated_count += 1
            print(f"✅ Analyse {doc['_id']} mise à jour")
            
        except Exception as e:
            print(f"❌ Erreur lors de la mise à jour de l'analyse {doc['_id']}: {e}")
    
    print(f"\n🎉 Migration terminée ! {updated_count} analyses ont été mises à jour.")

if __name__ == "__main__":
    asyncio.run(migrate_credit_analyses())
