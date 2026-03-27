import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def lister_dossiers():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["assistant_bank_db"]
    
    # Lister tous les dossiers
    cursor = db.credit_particulier_requests.find({})
    dossiers = await cursor.to_list(length=10)
    
    print("📂 Dossiers disponibles dans credit_particulier_requests:")
    for dossier in dossiers:
        client_name = dossier.get("request_data", {}).get("clientName", "N/A")
        montant = dossier.get("request_data", {}).get("loanAmount", 0)
        decision = dossier.get("ai_decision", "EN_ATTENTE")
        print(f"  ID: {dossier['_id']} - Client: {client_name} - Montant: {montant} - Décision: {decision}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(lister_dossiers())
