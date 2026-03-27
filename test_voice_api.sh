#!/bin/bash

# Test de l'API voice avec analyse IA de risque de crédit
echo "🧪 Test de l'API /voice/process-command"

# URL de l'API
API_URL="http://localhost:8000/voice/process-command"

# Token d'authentification (à remplacer par un token valide)
AUTH_TOKEN="votre_token_jwt_ici"

# Requête de test
curl -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -d '{
    "text": "Bonjour, je voudrais savoir si mon crédit peut être accordé",
    "dossier_id": "dossier_test_001",
    "conversation_history": []
  }' | jq '.'

echo ""
echo "✅ Test terminé"
echo ""
echo "📊 Attendu: réponse avec analyse IA, ratios calculés et audio base64"
echo "🔍 Vérifiez les logs du backend pour voir le déroulement"
