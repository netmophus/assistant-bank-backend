"""Service IA (OpenAI) pour la plateforme.

Ce module centralise les appels LLM (OpenAI) pour:
- Génération de contenu pédagogique pour les formations
  - `generate_chapitre_content`: génère le contenu complet d'un chapitre à partir
    de l'introduction + des prompts des parties.
  - `generate_partie_content`: génère le contenu d'une partie.
- Génération de QCM
  - `generate_qcm_questions`: génère les questions QCM au niveau module.
- Questions/Réponses utilisateur (assistant)
  - `generate_question_answer`: répond à une question en combinant:
    - contexte optionnel (ex: chapitre de formation)
    - historique de conversation
    - RAG (Recherche sémantique) sur:
      1) documents de l'organisation (scope=ORG)
      2) base globale (scope=GLOBAL) si licence active (ou superadmin)

Comportement en absence de clé OpenAI:
- `client` est None et des fonctions "mock" retournent un contenu placeholder.
"""

import os
import openai
from typing import List, Dict, Optional
import json
import re

from app.core.config import settings
from app.core.db import get_database

# -----------------------------------------------------------------------------
# Configuration OpenAI
# -----------------------------------------------------------------------------

# Configuration de l'API OpenAI
OPENAI_API_KEY = settings.OPENAI_API_KEY
OPENAI_MODEL = settings.OPENAI_MODEL  # Utiliser gpt-4o-mini par défaut (moins cher)

# Initialiser le client OpenAI si la clé est disponible
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
else:
    client = None


def _default_ai_search_config() -> dict:
    return {
        "source_priority": ["ORG", "GLOBAL", "AI"],
        "org_limit": 5,
        "global_limit": 3,
        "min_similarity_score": 0.7,
        "enable_global": True,
        "enable_ai_fallback": True,
        "filter_by_category": False,
        "filter_by_department": False,
    }


def _default_ai_response_config() -> dict:
    return {
        "system_prompt": "Tu es un assistant IA expert en formation bancaire.",
        "model": OPENAI_MODEL,
        "temperature": 0.7,
        "max_tokens": 2000,
        "response_style": "professional",
        "response_format": "markdown",
        "include_user_context": True,
        "include_department": True,
        "include_service": True,
        "custom_instructions": "Réponds de manière professionnelle et précise.",
    }


async def _load_org_ai_configs(organization_id: Optional[str]) -> tuple[dict, dict]:
    """Charge la config IA (search + response) depuis l'organisation.

    - Fallback sur valeurs par défaut si org absente / pas de config.
    - Tolère organization_id sous forme str (hex ObjectId) ou déjà "string id".
    """
    search_config = _default_ai_search_config()
    response_config = _default_ai_response_config()

    if not organization_id:
        return search_config, response_config

    try:
        db = get_database()
        org = await db["organizations"].find_one({"_id": organization_id})
        if not org:
            try:
                from bson import ObjectId

                org = await db["organizations"].find_one({"_id": ObjectId(organization_id)})
            except Exception:
                org = None

        if not org:
            return search_config, response_config

        if isinstance(org.get("ai_search_config"), dict):
            search_config = {**search_config, **org["ai_search_config"]}
        if isinstance(org.get("ai_response_config"), dict):
            response_config = {**response_config, **org["ai_response_config"]}

        return search_config, response_config
    except Exception:
        return search_config, response_config


# -----------------------------------------------------------------------------
# Formation: génération de contenu (chapitre / partie)
# -----------------------------------------------------------------------------


async def generate_chapitre_content(
    introduction: str,
    parties: List[Dict[str, str]],
    formation_titre: str = "",
    module_titre: str = "",
    chapitre_titre: str = ""
) -> str:
    """
    Génère le contenu complet d'un chapitre à partir de l'introduction et des prompts des parties.
    
    Args:
        introduction: Introduction du chapitre
        parties: Liste des parties avec leurs prompts (titre et contenu/prompt)
        formation_titre: Titre de la formation (contexte)
        module_titre: Titre du module (contexte)
    
    Returns:
        Contenu généré pour le chapitre
    """
    if not client:
        return _generate_mock_content(introduction, parties)
    
    try:
        # Construire le prompt pour l'IA
        system_prompt = """Tu es un expert en formation bancaire spécialisé dans la réglementation UEMOA.
Tu dois générer un contenu de formation complet, structuré et pédagogique pour un chapitre de formation bancaire.
Le contenu doit être technique, précis et conforme à la réglementation UEMOA.
Utilise un langage clair et professionnel, adapté à des stagiaires et agents bancaires.

IMPORTANT - Formules mathématiques:
- N'utilise JAMAIS de notation LaTeX (pas de \\[ \\], \\( \\), $$, ou commandes LaTeX)
- Écris toutes les formules en texte lisible et compréhensible
- Utilise des formats comme: "Ratio = Résultat Net / Capitaux Propres"
- Pour les fractions, utilise: "(numérateur) / (dénominateur)" ou "numérateur divisé par dénominateur"
- Pour les racines carrées, utilise: "√(valeur)" ou "racine carrée de valeur"
- Sois explicite et descriptif dans tes formules pour qu'elles soient facilement compréhensibles"""

        titre_bloc = ""
        if chapitre_titre:
            titre_bloc = f"TITRE DU CHAPITRE : {chapitre_titre}\n\n"

        user_prompt = f"""Génère le contenu complet d'un chapitre de formation bancaire.

CONTEXTE:
- Formation: {formation_titre}
- Module: {module_titre}

{titre_bloc}INTRODUCTION DU CHAPITRE:
{introduction}

STRUCTURE DU CHAPITRE (parties à développer):
"""

        # NOTE: on laisse l'ancien format en place (construction par concat) pour minimiser les changements.
        # Le titre est injecté avant l'introduction.

        # Ancien bloc (conservé) - remplacé par la version ci-dessus

        
        for idx, partie in enumerate(parties, 1):
            user_prompt += f"""
PARTIE {idx}: {partie.get('titre', '')}
Prompt/Contexte pour cette partie: {partie.get('contenu', '')}
"""
        
        user_prompt += """
INSTRUCTIONS:
- Génère un contenu complet et détaillé pour ce chapitre
- Structure le contenu selon les parties indiquées
- Chaque partie doit être développée de manière approfondie
- Utilise des exemples concrets et pratiques
- Assure-toi que le contenu est conforme à la réglementation UEMOA
- Le contenu doit être pédagogique et adapté à des stagiaires bancaires
- Format: Texte structuré avec des titres et sous-titres pour chaque partie
"""

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4000,
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        print(f"Erreur lors de la génération du contenu avec OpenAI: {e}")
        return _generate_mock_content(introduction, parties)


async def generate_qcm_questions(
    module_titre: str,
    chapitres: List[Dict],
    nombre_questions: int = 5
) -> List[Dict]:
    """
    Génère des questions QCM pour un module à partir de ses chapitres.
    
    Args:
        module_titre: Titre du module
        chapitres: Liste des chapitres du module (avec leurs introductions et parties)
        nombre_questions: Nombre de questions à générer (défaut: 5)
    
    Returns:
        Liste de questions QCM avec format:
        [
            {
                "question": "...",
                "options": ["...", "...", "...", "..."],
                "correct_answer": 0,  # Index de la bonne réponse
                "explication": "..."  # Explication de la réponse
            }
        ]
    """
    if not client:
        return _generate_mock_qcm(module_titre, nombre_questions)
    
    try:
        # Construire le contexte du module
        contexte_chapitres = ""
        for idx, chapitre in enumerate(chapitres, 1):
            contexte_chapitres += f"\nChapitre {idx}: {chapitre.get('introduction', '')}\n"
            for p_idx, partie in enumerate(chapitre.get('parties', []), 1):
                contexte_chapitres += f"  - {partie.get('titre', '')}: {partie.get('contenu', '')[:200]}...\n"
        
        system_prompt = """Tu es un expert en formation bancaire spécialisé dans la réglementation UEMOA.
Tu dois créer des questions QCM (Question à Choix Multiples) pour évaluer la compréhension d'un module de formation bancaire.
Les questions doivent être pertinentes, claires et tester la compréhension des concepts importants.

IMPORTANT - Formules mathématiques:
- N'utilise JAMAIS de notation LaTeX (pas de \\[ \\], \\( \\), $$, ou commandes LaTeX)
- Écris toutes les formules en texte lisible et compréhensible
- Utilise des formats comme: "Ratio = Résultat Net / Capitaux Propres"
- Pour les fractions, utilise: "(numérateur) / (dénominateur)" ou "numérateur divisé par dénominateur"
- Pour les racines carrées, utilise: "√(valeur)" ou "racine carrée de valeur"
- Sois explicite et descriptif dans tes formules pour qu'elles soient facilement compréhensibles"""

        user_prompt = f"""Génère {nombre_questions} questions QCM pour le module suivant:

TITRE DU MODULE: {module_titre}

CONTENU DU MODULE:
{contexte_chapitres}

INSTRUCTIONS:
- Génère {nombre_questions} questions QCM pertinentes
- Chaque question doit avoir 4 options (A, B, C, D)
- Une seule réponse est correcte
- Les questions doivent tester la compréhension des concepts clés du module
- Les questions doivent être adaptées au niveau stagiaire/agent bancaire
- Inclus une explication pour chaque réponse correcte

Format de réponse attendu (JSON):
[
    {{
        "question": "Question textuelle",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_answer": 0,
        "explication": "Explication de la réponse correcte"
    }}
]

Réponds UNIQUEMENT avec le JSON, sans texte supplémentaire."""

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        
        content = response.choices[0].message.content.strip()
        
        # Essayer de parser le JSON
        try:
            # Nettoyer le contenu si nécessaire (enlever les markdown code blocks)
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()
            
            questions = json.loads(content)
            
            # Valider le format
            if isinstance(questions, list):
                for q in questions:
                    if not all(key in q for key in ["question", "options", "correct_answer"]):
                        raise ValueError("Format de question invalide")
                return questions
            else:
                raise ValueError("Le résultat n'est pas une liste")
        
        except json.JSONDecodeError as e:
            print(f"Erreur de parsing JSON: {e}")
            print(f"Contenu reçu: {content[:500]}")
            return _generate_mock_qcm(module_titre, nombre_questions)
    
    except Exception as e:
        print(f"Erreur lors de la génération des QCM avec OpenAI: {e}")
        return _generate_mock_qcm(module_titre, nombre_questions)


def _generate_mock_content(introduction: str, parties: List[Dict[str, str]]) -> str:
    """Génère un contenu mock si l'API IA n'est pas disponible."""
    content = f"# {introduction}\n\n"
    content += "Ce contenu sera généré automatiquement par l'IA une fois la clé API configurée.\n\n"
    
    for idx, partie in enumerate(parties, 1):
        content += f"## Partie {idx}: {partie.get('titre', 'Sans titre')}\n\n"
        content += f"**Prompt fourni:** {partie.get('contenu', 'Aucun prompt')}\n\n"
        content += f"*Le contenu de cette partie sera généré à partir du prompt ci-dessus.*\n\n"
    
    return content


def _generate_mock_qcm(module_titre: str, nombre_questions: int) -> List[Dict]:
    """Génère des questions QCM mock si l'API IA n'est pas disponible."""
    questions = []
    for i in range(nombre_questions):
        questions.append({
            "question": f"Question {i+1} sur le module '{module_titre}' (à générer avec l'IA)",
            "options": [
                "Option A (à générer)",
                "Option B (à générer)",
                "Option C (à générer)",
                "Option D (à générer)"
            ],
            "correct_answer": 0,
            "explication": "Explication à générer avec l'IA"
        })
    return questions


async def generate_chapter_question_suggestions(
    chapitre_introduction: str,
    contenu_genere: Optional[str] = None,
    parties: List[Dict[str, str]] = None,
    nombre_suggestions: int = 3
) -> List[str]:
    """
    Génère des suggestions de questions pertinentes sur un chapitre.
    
    Args:
        chapitre_introduction: Introduction du chapitre
        contenu_genere: Contenu généré du chapitre (si disponible)
        parties: Liste des parties avec leurs prompts (si contenu non généré)
        nombre_suggestions: Nombre de suggestions à générer (défaut: 3)
    
    Returns:
        Liste de suggestions de questions
    """
    if not client:
        # Retourner des suggestions mock
        suggestions = [
            f"Pouvez-vous expliquer plus en détail le concept de '{chapitre_introduction[:50]}...' ?",
            f"Quelles sont les implications pratiques de '{chapitre_introduction[:50]}...' dans le contexte bancaire ?",
            f"Y a-t-il des exemples concrets que vous pouvez donner concernant '{chapitre_introduction[:50]}...' ?"
        ]
        return suggestions[:nombre_suggestions]
    
    try:
        # Construire le contexte
        contexte = f"Introduction du chapitre: {chapitre_introduction}\n\n"
        
        if contenu_genere:
            contexte += f"Contenu du chapitre:\n{contenu_genere[:2000]}"  # Limiter à 2000 caractères
        elif parties:
            contexte += "Structure du chapitre:\n"
            for idx, partie in enumerate(parties, 1):
                contexte += f"\nPartie {idx}: {partie.get('titre', '')}\n"
                contexte += f"Description: {partie.get('contenu', '')[:300]}\n"
        
        system_prompt = """Tu es un expert en formation bancaire spécialisé dans la réglementation UEMOA.
Ton rôle est de suggérer des questions pertinentes que des stagiaires ou agents bancaires pourraient poser sur un chapitre de formation.
Les questions doivent être claires, pertinentes et aider à approfondir la compréhension du contenu."""
        
        user_prompt = f"""Basé sur le contenu suivant d'un chapitre de formation bancaire, génère {nombre_suggestions} suggestions de questions pertinentes que des apprenants pourraient poser.

CONTENU DU CHAPITRE:
{contexte}

INSTRUCTIONS:
- Génère {nombre_suggestions} questions pertinentes et variées
- Les questions doivent être claires et aider à approfondir la compréhension
- Les questions doivent être adaptées au niveau stagiaire/agent bancaire
- Les questions doivent être pratiques et liées à la réglementation UEMOA

Format de réponse attendu (JSON):
{{
    "suggestions": [
        "Question 1",
        "Question 2",
        "Question 3"
    ]
}}

Réponds UNIQUEMENT avec le JSON, sans texte supplémentaire."""
        
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content.strip()
        
        # Parser le JSON
        try:
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()
            
            result = json.loads(content)
            suggestions = result.get("suggestions", [])
            
            if isinstance(suggestions, list) and len(suggestions) > 0:
                return suggestions[:nombre_suggestions]
            else:
                raise ValueError("Format de réponse invalide")
        
        except json.JSONDecodeError as e:
            print(f"Erreur de parsing JSON: {e}")
            print(f"Contenu reçu: {content[:500]}")
            return _generate_mock_question_suggestions(chapitre_introduction, nombre_suggestions)
    
    except Exception as e:
        print(f"Erreur lors de la génération des suggestions de questions avec OpenAI: {e}")
        return _generate_mock_question_suggestions(chapitre_introduction, nombre_suggestions)


def _generate_mock_question_suggestions(chapitre_introduction: str, nombre_suggestions: int) -> List[str]:
    """Génère des suggestions mock si l'API IA n'est pas disponible."""
    suggestions = [
        f"Pouvez-vous expliquer plus en détail le concept de '{chapitre_introduction[:50]}...' ?",
        f"Quelles sont les implications pratiques de '{chapitre_introduction[:50]}...' dans le contexte bancaire ?",
        f"Y a-t-il des exemples concrets que vous pouvez donner concernant '{chapitre_introduction[:50]}...' ?"
    ]
    return suggestions[:nombre_suggestions]


async def generate_partie_content(
    partie_titre: str,
    partie_prompt: str,
    chapitre_introduction: str = "",
    formation_titre: str = "",
    module_titre: str = ""
) -> str:
    """
    Génère le contenu complet d'une partie spécifique d'un chapitre.
    
    Args:
        partie_titre: Titre de la partie
        partie_prompt: Prompt/contexte pour cette partie
        chapitre_introduction: Introduction du chapitre (contexte)
        formation_titre: Titre de la formation (contexte)
        module_titre: Titre du module (contexte)
    
    Returns:
        Contenu généré pour la partie
    """
    if not client:
        return _generate_mock_partie_content(partie_titre, partie_prompt)
    
    try:
        system_prompt = """Tu es un expert en formation bancaire spécialisé dans la réglementation UEMOA.
Tu dois générer un contenu de formation complet, structuré et pédagogique pour une partie spécifique d'un chapitre de formation bancaire.
Le contenu doit être technique, précis et conforme à la réglementation UEMOA.
Utilise un langage clair et professionnel, adapté à des stagiaires et agents bancaires.

IMPORTANT - Formules mathématiques:
- N'utilise JAMAIS de notation LaTeX (pas de \\[ \\], \\( \\), $$, ou commandes LaTeX)
- Écris toutes les formules en texte lisible et compréhensible
- Utilise des formats comme: "Ratio = Résultat Net / Capitaux Propres"
- Pour les fractions, utilise: "(numérateur) / (dénominateur)" ou "numérateur divisé par dénominateur"
- Pour les racines carrées, utilise: "√(valeur)" ou "racine carrée de valeur"
- Sois explicite et descriptif dans tes formules pour qu'elles soient facilement compréhensibles"""
        
        user_prompt = f"""Génère le contenu complet et détaillé pour une partie spécifique d'un chapitre de formation bancaire.

CONTEXTE:
- Formation: {formation_titre}
- Module: {module_titre}
- Chapitre: {chapitre_introduction}

PARTIE À DÉVELOPPER:
Titre: {partie_titre}
Prompt/Contexte: {partie_prompt}

INSTRUCTIONS:
- Génère un contenu complet et détaillé pour cette partie spécifique
- Le contenu doit être approfondi et pédagogique
- Utilise des exemples concrets et pratiques liés à la banque
- Assure-toi que le contenu est conforme à la réglementation UEMOA
- Structure le contenu avec des titres et sous-titres si nécessaire
- Le contenu doit être adapté à des stagiaires et agents bancaires
- Format: Texte structuré et bien formaté"""
        
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        print(f"Erreur lors de la génération du contenu de la partie avec OpenAI: {e}")
        return _generate_mock_partie_content(partie_titre, partie_prompt)


def _generate_mock_partie_content(partie_titre: str, partie_prompt: str) -> str:
    """Génère un contenu mock pour une partie si l'API IA n'est pas disponible."""
    content = f"# {partie_titre}\n\n"
    content += "Ce contenu sera généré automatiquement par l'IA une fois la clé API configurée.\n\n"
    content += f"**Prompt fourni:** {partie_prompt}\n\n"
    content += "*Le contenu de cette partie sera généré à partir du prompt ci-dessus.*\n"
    return content


# -----------------------------------------------------------------------------
# Assistant Q/R: réponse utilisateur + RAG (ORG + GLOBAL)
# -----------------------------------------------------------------------------

async def generate_question_answer(
    question: str,
    context: Optional[str] = None,
    user_department: Optional[str] = None,
    user_service: Optional[str] = None,
    organization_id: Optional[str] = None,
    conversation_history: Optional[List[Dict]] = None,
) -> str:
    """
    Génère une réponse à une question posée par un utilisateur.
    
    Args:
        question: La question posée par l'utilisateur
        context: Contexte optionnel (ex: chapitre de formation)
        user_department: Département de l'utilisateur (contexte)
        user_service: Service de l'utilisateur (contexte)
        organization_id: ID de l'organisation (pour recherche base de connaissances)
        conversation_history: Historique de la conversation (liste de messages avec role/content)
    
    Returns:
        Réponse générée par l'IA
    """
    if not client:
        return _generate_mock_question_answer(question)
    
    try:
        # Charger les configs (ORG) et les appliquer réellement
        search_config, response_config = await _load_org_ai_configs(organization_id)

        # Normaliser quelques champs
        try:
            org_limit = int(search_config.get("org_limit", 5))
        except Exception:
            org_limit = 5
        try:
            global_limit = int(search_config.get("global_limit", 3))
        except Exception:
            global_limit = 3
        try:
            min_similarity_score = float(search_config.get("min_similarity_score", 0.7))
        except Exception:
            min_similarity_score = 0.7

        enable_global = bool(search_config.get("enable_global", True))
        source_priority = search_config.get("source_priority")
        if not isinstance(source_priority, list) or not source_priority:
            source_priority = ["ORG", "GLOBAL", "AI"]

        # Prompt système / paramètres LLM
        math_constraints = """

IMPORTANT - Formules mathématiques:
- N'utilise JAMAIS de notation LaTeX (pas de \\[ \\], \\( \\), $$, ou commandes LaTeX)
- Écris toutes les formules en texte lisible et compréhensible
- Utilise des formats comme: "Ratio = Résultat Net / Capitaux Propres"
- Pour les fractions, utilise: "(numérateur) / (dénominateur)" ou "numérateur divisé par dénominateur"
- Pour les racines carrées, utilise: "√(valeur)" ou "racine carrée de valeur"
- Sois explicite et descriptif dans tes formules pour qu'elles soient facilement compréhensibles"""

        base_system_prompt = (response_config.get("system_prompt") or "").strip()
        if not base_system_prompt:
            base_system_prompt = "Tu es Fahimta AI, un assistant expert en formation bancaire spécialisé dans la réglementation UEMOA."

        formatting_constraints = """

RÈGLES DE STRUCTURATION — OBLIGATOIRES:

INTERDIT (tu ne dois JAMAIS écrire):
❌ "## Partie 1 : ..."
❌ "## Partie 2 : ..."
❌ "### Partie 1 :", "### Partie 2 :", "Partie 1/2/3"
❌ Tout titre commençant par "Partie" suivi d'un numéro

CORRECT (exemples de titres autorisés):
✅ "## Exigences de capital minimum"
✅ "## Classification des créances"
✅ "## Conseils pratiques"
✅ "### Ratio de solvabilité"

RÈGLES:
- Construis une réponse unifiée et cohérente — pas des blocs séparés de sources
- Titres (##, ###) uniquement basés sur le contenu réel, JAMAIS sur une numérotation de parties
- Sources entre parenthèses en fin de phrase: *(NomDocument.pdf)*
- Listes à puces pour énumérations, listes numérotées pour étapes séquentielles uniquement
- Exemples intégrés dans le texte avec "**Exemple :**", pas en section à part"""

        system_prompt = (base_system_prompt + math_constraints + formatting_constraints).strip()

        model = (response_config.get("model") or OPENAI_MODEL)
        try:
            temperature = float(response_config.get("temperature", 0.7))
        except Exception:
            temperature = 0.7
        try:
            max_tokens = int(response_config.get("max_tokens", 4000))
        except Exception:
            max_tokens = 4000

        custom_instructions = (response_config.get("custom_instructions") or "").strip()
        response_style = (response_config.get("response_style") or "professional").strip()
        response_format = (response_config.get("response_format") or "markdown").strip()

        include_user_context = bool(response_config.get("include_user_context", True))
        include_department = bool(response_config.get("include_department", True))
        include_service = bool(response_config.get("include_service", True))
        
        # Recherche RAG via le nouveau pipeline Atlas Vector Search
        org_context = ""
        global_context = ""

        def _build_context_from_chunks(chunks: List[dict], kind: str) -> str:
            if not chunks:
                return ""
            if kind == "ORG":
                ctx = "\n\n## 📁 Contexte de votre organisation:\n\n"
                for i, chunk in enumerate(chunks, 1):
                    meta = chunk.get("metadata") or {}
                    filename = meta.get("filename") or chunk.get("filename") or ""
                    source = f" (Document: {filename})" if filename else ""
                    ctx += f"**Extrait {i}**{source}:\n{chunk.get('content', '')}\n\n"
                return ctx

            ctx = "\n\n## 🌐 Base de Connaissances Globale (Références Officielles):\n\n"
            for i, chunk in enumerate(chunks, 1):
                meta = chunk.get("metadata") or {}
                filename = meta.get("filename") or chunk.get("filename") or ""
                source = f" (Document: {filename})" if filename else ""
                ctx += f"**Référence {i}**{source}:\n{chunk.get('content', '')}\n\n"
            return ctx

        try:
            from app.services.rag_new_service import retrieve

            # Déterminer si GLOBAL est autorisée (config + licence)
            allow_global_by_license = False
            if enable_global:
                if organization_id:
                    from app.models.license import org_has_active_license
                    allow_global_by_license = await org_has_active_license(organization_id)
                else:
                    allow_global_by_license = True

            rag_scope, rag_results = await retrieve(
                question=question,
                organization_id=organization_id if organization_id else None,
                category=None,
            )

            local_chunks = [r for r in rag_results if r.get("scope") in ("LOCAL", "ORG")]
            global_chunks = [r for r in rag_results if r.get("scope") == "GLOBAL"]

            if local_chunks and org_limit > 0:
                org_context = _build_context_from_chunks(local_chunks[:org_limit], "ORG")

            if global_chunks and allow_global_by_license and global_limit > 0:
                global_context = _build_context_from_chunks(global_chunks[:global_limit], "GLOBAL")

        except Exception as e:
            print(f"Erreur lors de la recherche RAG: {e}")
        
        # Construire le prompt avec historique si disponible
        user_prompt = ""
        
        # Ajouter l'historique de conversation si disponible
        if conversation_history and len(conversation_history) > 0:
            user_prompt += "HISTORIQUE DE LA CONVERSATION:\n\n"
            for msg in conversation_history:
                role_label = "Utilisateur" if msg.get("role") == "user" else "Assistant"
                content = msg.get("content", "")
                user_prompt += f"- {role_label}: {content}\n"
            user_prompt += "\n"
        
        user_prompt += f"""Question de l'utilisateur:
{question}
"""
        
        if context and include_user_context:
            user_prompt += f"""
Contexte fourni par l'utilisateur:
{context}
"""
        
        # Ajouter les contextes (ORG puis GLOBAL)
        if org_context:
            user_prompt += org_context
        
        if global_context:
            user_prompt += global_context
        
        if user_department and include_department:
            user_prompt += f"""
Département de l'utilisateur: {user_department}
"""
        
        if user_service and include_service:
            user_prompt += f"""
Service de l'utilisateur: {user_service}
"""
        
        user_prompt += """
Instructions de réponse:
- Réponds directement à la question de façon complète, détaillée et pédagogique
- Fusionne intelligemment toutes les informations disponibles (documents ORG + références globales) en une réponse unique et cohérente — ne les traite PAS comme des blocs séparés
- Cite les sources entre parenthèses en fin de phrase ou de paragraphe quand tu utilises un document, ex: *(NomDocument.pdf)*
- Structure avec des titres markdown significatifs (## Titre basé sur le contenu), jamais "Partie 1 / Partie 2 / Partie 3"
- Si tu fournis des recommandations ou conseils pratiques, inclus-les dans une section finale "## Conseils pratiques" ou "## À retenir"
- Intègre les exemples concrets directement dans le texte (introduit par "**Exemple :**"), pas comme une section à part
- Adopte le ton d'un expert qui explique et guide, pas d'un compilateur de sources
- Assure-toi que la réponse est conforme à la réglementation UEMOA et adaptée au secteur bancaire
"""

        if response_style or response_format:
            user_prompt += f"\nContraintes de style:\n- Style: {response_style}\n- Format: {response_format}\n"

        if custom_instructions:
            user_prompt += f"\nInstructions personnalisées:\n{custom_instructions}\n"
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        print(f"Erreur lors de la génération de la réponse avec OpenAI: {e}")
        return _generate_mock_question_answer(question)


def _generate_mock_question_answer(question: str) -> str:
    """Génère une réponse mock si l'API IA n'est pas disponible."""
    answer = f"## Réponse à votre question\n\n"
    answer += f"Votre question: {question}\n\n"
    answer += "Cette réponse sera générée automatiquement par l'IA une fois la clé API OpenAI configurée.\n\n"
    answer += "*Pour configurer l'API, veuillez ajouter votre clé API OpenAI dans le fichier `.env`.*\n"
    return answer

