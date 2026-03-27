# 📚 Utilisation de la Base de Connaissances par l'IA

## 🎯 Vue d'ensemble

La base de connaissances est **activement utilisée** par l'IA pour répondre aux questions des utilisateurs. Le système effectue une **recherche hybride** qui combine :
- Les documents **organisationnels** (ORG) : documents propres à chaque organisation
- Les documents **globaux** (GLOBAL) : documents officiels partagés (plan comptable UEMOA, réglementations, etc.)

---

## 🔍 Où est utilisée la base de connaissances ?

### 1. **Fonction principale : `generate_question_answer()`**

**Fichier :** `app/services/ai_service.py` (lignes 444-650)

Cette fonction est le **point d'entrée principal** où l'IA utilise la base de connaissances pour répondre aux questions.

#### Flux d'exécution :

```
Question utilisateur
    ↓
generate_question_answer()
    ↓
1. Génération de l'embedding de la question
    ↓
2. Recherche dans documents ORG (limit 5)
    ↓
3. Recherche dans documents GLOBAL (limit 3) - si licence active
    ↓
4. Construction du contexte avec extraits trouvés
    ↓
5. Envoi à OpenAI avec contexte
    ↓
Réponse générée
```

---

## 📋 Détails techniques

### 1. **Recherche dans les documents organisationnels (ORG)**

**Code :** `app/services/ai_service.py` lignes 496-517

```python
# Recherche dans documents organisationnels (limit 5)
if organization_id:
    org_chunks = await search_document_chunks(
        organization_id=organization_id,
        query_embedding=question_embedding,
        scope="ORG",
        limit=5
    )
```

**Caractéristiques :**
- ✅ Toujours effectuée si `organization_id` est fourni
- ✅ Limite : 5 chunks maximum
- ✅ Scope : `"ORG"` uniquement
- ✅ Filtre : documents de l'organisation spécifique

**Contexte généré :**
- Format : `"## 📁 Contexte de votre organisation:\n\n"`
- Inclut : nom du document, numéro de page, section
- Citation : `"Extrait 1 (Page X, Section: Y, Document: Z): ..."`

---

### 2. **Recherche dans la base globale (GLOBAL)**

**Code :** `app/services/ai_service.py` lignes 519-569

```python
# Recherche dans base de connaissances globale (limit 3)
# UNIQUEMENT si l'organisation a une licence active
if organization_id:
    from app.models.license import org_has_active_license
    has_license = await org_has_active_license(organization_id)
    
    if has_license:
        global_chunks = await search_document_chunks(
            organization_id=None,
            query_embedding=question_embedding,
            scope="GLOBAL",
            limit=3
        )
```

**Caractéristiques :**
- ⚠️ **Conditionnelle** : uniquement si licence active
- ✅ Limite : 3 chunks maximum
- ✅ Scope : `"GLOBAL"` uniquement
- ✅ Filtre : `status="published"` (seulement documents publiés)
- ✅ Superadmin : toujours accès (même sans `organization_id`)

**Contexte généré :**
- Format : `"## 🌐 Base de Connaissances Globale (Références Officielles):\n\n"`
- Inclut : autorité, référence, version, page, section, nom du document
- Citation : `"Référence 1 (Source: X, Réf: Y, vZ, Page W): ..."`

---

### 3. **Fonction de recherche : `search_document_chunks()`**

**Fichier :** `app/models/documents.py` (lignes 332-510)

Cette fonction effectue la **recherche sémantique** par similarité cosinus.

#### Paramètres :
- `organization_id` : ID de l'organisation (requis pour `scope="ORG"`)
- `query_embedding` : Vecteur d'embedding de la question
- `scope` : `"ORG"` | `"GLOBAL"` | `None`
- `limit` : Nombre maximum de résultats
- `category` : Filtrer par catégorie (optionnel)

#### Algorithme :
1. **Filtrage MongoDB** selon le scope :
   - `scope="ORG"` : `organization_id = ObjectId(org_id)` + `scope="ORG"`
   - `scope="GLOBAL"` : `organization_id = None` + `scope="GLOBAL"` + `status="published"`
2. **Récupération** de tous les chunks correspondants
3. **Calcul de similarité cosinus** pour chaque chunk
4. **Tri** par similarité décroissante
5. **Filtrage** des chunks d'erreur ou trop courts
6. **Retour** des N meilleurs chunks (selon `limit`)

---

## 🔗 Points d'appel de `generate_question_answer()`

### 1. **Endpoint : `POST /questions`**

**Fichier :** `app/routers/question.py` (via `app/models/question.py`)

**Code :** `app/models/question.py` lignes 198-205

```python
answer = await generate_question_answer(
    question=question_text,
    context=context,
    user_department=department_name,
    user_service=service_name,
    organization_id=organization_id
)
```

**Usage :** Questions simples posées par les utilisateurs

---

### 2. **Endpoint : `POST /conversations/ask`**

**Fichier :** `app/routers/conversation.py`

**Code :** `app/routers/conversation.py` lignes 126-133

```python
answer = await generate_question_answer(
    question=request.question,
    context=request.context,
    user_department=department_name,
    user_service=service_name,
    organization_id=organization_id,
    conversation_history=conversation_history,  # Historique ajouté
)
```

**Usage :** Questions dans le cadre d'une conversation (avec historique)

---

## 📊 Structure du contexte envoyé à l'IA

### Ordre de construction :

1. **Historique de conversation** (si disponible)
   ```
   HISTORIQUE DE LA CONVERSATION:
   - Utilisateur: Question précédente
   - Assistant: Réponse précédente
   ```

2. **Question actuelle**
   ```
   Question de l'utilisateur:
   [question]
   ```

3. **Contexte utilisateur** (si fourni)
   ```
   Contexte fourni par l'utilisateur:
   [context]
   ```

4. **Contexte organisationnel** (si chunks ORG trouvés)
   ```
   ## 📁 Contexte de votre organisation:
   **Extrait 1** (Page X, Section: Y, Document: Z):
   [contenu du chunk]
   ```

5. **Contexte global** (si chunks GLOBAL trouvés ET licence active)
   ```
   ## 🌐 Base de Connaissances Globale (Références Officielles):
   **Référence 1** (Source: X, Réf: Y, vZ, Page W):
   [contenu du chunk]
   ```

6. **Informations utilisateur**
   ```
   Département de l'utilisateur: [dept]
   Service de l'utilisateur: [service]
   ```

7. **Instructions finales**
   ```
   Instructions:
   - Réponds de manière complète et détaillée
   - Utilise les extraits comme référence principale
   - Priorise les informations de votre organisation
   - Cite les sources (document, page, référence)
   ```

---

## 🔐 Contrôle d'accès

### Documents organisationnels (ORG)
- ✅ **Toujours accessibles** si `organization_id` est fourni
- ✅ Filtrage automatique par organisation
- ✅ Pas de vérification de licence

### Documents globaux (GLOBAL)
- ⚠️ **Conditionnel** : nécessite une licence active
- ✅ Vérification via `org_has_active_license(organization_id)`
- ✅ Superadmin (`organization_id=None`) : toujours accès
- ✅ Filtre : seulement documents avec `status="published"`

**Fichier de vérification :** `app/models/license.py`

---

## 📈 Statistiques et logs

### Logs de debug

La fonction `generate_question_answer()` génère des logs pour le débogage :

```python
print(f"[DEBUG] GLOBAL_INCLUDED=True pour org_id={organization_id} ({len(global_chunks)} chunks trouvés)")
print(f"[DEBUG] GLOBAL_INCLUDED=False pour org_id={organization_id} (pas de licence active)")
print(f"[DEBUG] GLOBAL_INCLUDED=True pour superadmin ({len(global_chunks)} chunks trouvés)")
```

### Gestion des erreurs

Si une erreur survient lors de la recherche dans la base de connaissances :
- ✅ L'erreur est loggée : `print(f"Erreur lors de la recherche dans la base de connaissances: {e}")`
- ✅ Le processus continue sans la base de connaissances
- ✅ L'IA répond quand même (sans contexte de documents)

---

## ✅ Résumé

| Aspect | Détails |
|--------|---------|
| **Fonction principale** | `generate_question_answer()` dans `app/services/ai_service.py` |
| **Recherche ORG** | Toujours effectuée, limit 5 chunks |
| **Recherche GLOBAL** | Conditionnelle (licence), limit 3 chunks |
| **Fonction de recherche** | `search_document_chunks()` dans `app/models/documents.py` |
| **Points d'appel** | `POST /questions` et `POST /conversations/ask` |
| **Méthode** | Recherche sémantique par similarité cosinus |
| **Contrôle d'accès** | Licence requise pour GLOBAL, ORG toujours accessible |

---

## 🎯 Conclusion

**OUI, la base de connaissances est activement utilisée par l'IA** pour répondre aux questions des utilisateurs. Le système combine intelligemment :
- Les documents propres à l'organisation (priorité)
- Les références officielles globales (si licence active)

Cela permet à l'IA de fournir des réponses précises, contextualisées et basées sur les documents réels de l'organisation et les réglementations officielles.

