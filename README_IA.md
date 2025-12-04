# Configuration de l'API IA (OpenAI)

## Installation

Pour utiliser la génération de contenu avec l'IA, vous devez installer la bibliothèque OpenAI :

```bash
pip install openai
```

## Configuration

1. Créez un compte sur [OpenAI](https://platform.openai.com/)
2. Générez une clé API dans votre dashboard OpenAI
3. Ajoutez la clé API dans votre fichier `.env` :

```env
OPENAI_API_KEY=votre_cle_api_ici
OPENAI_MODEL=gpt-4o-mini
```

Le modèle par défaut est `gpt-4o-mini` qui est moins cher. Vous pouvez utiliser d'autres modèles comme :
- `gpt-4o-mini` (recommandé, moins cher)
- `gpt-4o`
- `gpt-4-turbo`
- `gpt-3.5-turbo`

## Utilisation

Une fois la clé API configurée, vous pouvez :

1. **Générer le contenu d'un chapitre** :
   - Ouvrez une formation existante
   - Cliquez sur "🤖 Générer contenu IA" sur un chapitre
   - Le contenu sera généré à partir des prompts des parties

2. **Générer des questions QCM** :
   - Ouvrez une formation existante
   - Cliquez sur "📝 Générer QCM IA" sur un module
   - Indiquez le nombre de questions souhaitées
   - Les questions seront générées automatiquement

## Note

Si la clé API n'est pas configurée, le système utilisera des contenus mock pour permettre le développement sans coût.

