import os
import openai
from typing import List, Dict, Optional
import json

# Configuration de l'API OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # Utiliser gpt-4o-mini par défaut (moins cher)

# Initialiser le client OpenAI si la clé est disponible
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
else:
    client = None


async def generate_chapitre_content(
    introduction: str,
    parties: List[Dict[str, str]],
    formation_titre: str = "",
    module_titre: str = ""
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

        user_prompt = f"""Génère le contenu complet d'un chapitre de formation bancaire.

CONTEXTE:
- Formation: {formation_titre}
- Module: {module_titre}

INTRODUCTION DU CHAPITRE:
{introduction}

STRUCTURE DU CHAPITRE (parties à développer):
"""
        
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


async def generate_question_answer(
    question: str,
    context: Optional[str] = None,
    user_department: Optional[str] = None,
    user_service: Optional[str] = None
) -> str:
    """
    Génère une réponse à une question posée par un utilisateur.
    
    Args:
        question: La question posée par l'utilisateur
        context: Contexte optionnel (ex: chapitre de formation)
        user_department: Département de l'utilisateur (contexte)
        user_service: Service de l'utilisateur (contexte)
    
    Returns:
        Réponse générée par l'IA
    """
    if not client:
        return _generate_mock_question_answer(question)
    
    try:
        system_prompt = """Tu es Fahimta AI, un assistant expert en formation bancaire spécialisé dans la réglementation UEMOA.
Tu dois répondre aux questions des utilisateurs de manière claire, précise et pédagogique.
Tes réponses doivent être techniques, conformes à la réglementation UEMOA, et adaptées au contexte bancaire.
Utilise un langage professionnel mais accessible, avec des exemples concrets lorsque c'est pertinent.
Structure tes réponses de manière claire avec des titres si nécessaire.

IMPORTANT - Formules mathématiques:
- N'utilise JAMAIS de notation LaTeX (pas de \\[ \\], \\( \\), $$, ou commandes LaTeX)
- Écris toutes les formules en texte lisible et compréhensible
- Utilise des formats comme: "Ratio = Résultat Net / Capitaux Propres"
- Pour les fractions, utilise: "(numérateur) / (dénominateur)" ou "numérateur divisé par dénominateur"
- Pour les racines carrées, utilise: "√(valeur)" ou "racine carrée de valeur"
- Sois explicite et descriptif dans tes formules pour qu'elles soient facilement compréhensibles"""
        
        user_prompt = f"""Question de l'utilisateur:
{question}
"""
        
        if context:
            user_prompt += f"""
Contexte:
{context}
"""
        
        if user_department:
            user_prompt += f"""
Département de l'utilisateur: {user_department}
"""
        
        if user_service:
            user_prompt += f"""
Service de l'utilisateur: {user_service}
"""
        
        user_prompt += """
Instructions:
- Réponds de manière complète et détaillée à la question
- Utilise des exemples concrets liés au secteur bancaire UEMOA si pertinent
- Structure ta réponse avec des titres (##) et des listes si nécessaire
- Assure-toi que la réponse est conforme à la réglementation UEMOA
- Sois précis et technique tout en restant accessible
"""
        
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
        print(f"Erreur lors de la génération de la réponse avec OpenAI: {e}")
        return _generate_mock_question_answer(question)


def _generate_mock_question_answer(question: str) -> str:
    """Génère une réponse mock si l'API IA n'est pas disponible."""
    answer = f"## Réponse à votre question\n\n"
    answer += f"Votre question: {question}\n\n"
    answer += "Cette réponse sera générée automatiquement par l'IA une fois la clé API OpenAI configurée.\n\n"
    answer += "*Pour configurer l'API, veuillez ajouter votre clé API OpenAI dans le fichier `.env`.*\n"
    return answer

