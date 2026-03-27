#!/usr/bin/env python3
"""
Test simple pour vérifier la connexion à OpenAI
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

# Charger les variables d'environnement
load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

print(f"🔑 Clé OpenAI: {'✅ Configurée' if OPENAI_API_KEY else '❌ Manquante'}")
print(f"🤖 Modèle: {OPENAI_MODEL}")

if OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Test simple
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "user", "content": "Bonjour, réponds simplement 'OK' pour tester."}
            ],
            max_tokens=10,
            timeout=10.0
        )
        
        result = response.choices[0].message.content
        print(f"✅ Test OpenAI réussi: {result}")
        print(f"💰 Tokens utilisés: {response.usage.total_tokens}")
        
    except Exception as e:
        print(f"❌ Erreur OpenAI: {str(e)}")
else:
    print("❌ Veuillez configurer OPENAI_API_KEY dans votre fichier .env")
