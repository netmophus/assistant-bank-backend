# 📋 Plan d'Implémentation : Système de Conversations

## 🎯 Objectif

**Garder les questions simples existantes** ET **ajouter un système de conversations** avec historique contextuel.

---

## 📊 État Actuel (Questions Simples)

### Backend

**Collection MongoDB :** `questions`
```python
{
  _id: ObjectId,
  user_id: ObjectId,
  user_email: str,
  user_name: str,
  department_id: ObjectId,
  department_name: str,
  service_id: ObjectId,
  service_name: str,
  question: str,
  context: Optional[str],
  answer: str,
  status: "pending" | "answered" | "error",
  created_at: datetime,
  answered_at: datetime
}
```

**Endpoints existants :**
- `POST /questions` : Créer une question simple (sans historique)
- `GET /questions/my-questions` : Liste des questions de l'utilisateur
- `GET /questions/quota` : Statistiques de quota
- `GET /questions/org` : Liste des questions de l'organisation (admin)

**Fonction actuelle :** `create_question()` dans `app/models/question.py`
- Vérifie le quota
- Crée la question dans MongoDB
- Appelle `generate_question_answer()` (sans historique)
- Sauvegarde la réponse

**Quota :** 60 questions/mois par utilisateur

### Frontend

**Composant :** `QuestionsTab.jsx`
- Formulaire simple : question + contexte optionnel
- Affichage liste des questions/réponses (pas de conversation)
- Groupement par mois (courant vs archivé)

**Fonction :** `handleAskQuestion()` dans `UserDashboardPage.jsx`
- Appel `POST /questions`
- Rafraîchit la liste après réponse

---

## 🆕 Ce qu'on veut Ajouter (Conversations)

### Concept

**Deux modes de fonctionnement :**

1. **Mode Question Simple** (existant) :
   - Chaque question est indépendante
   - Pas d'historique partagé
   - Compte dans le quota
   - Reste disponible tel quel

2. **Mode Conversation** (nouveau) :
   - Plusieurs questions/réponses dans une même session
   - Historique partagé entre les questions
   - L'IA utilise le contexte de toute la conversation
   - Compte dans le quota (chaque question de la conversation)
   - Nouvelle conversation = nouvelle session (historique réinitialisé)

---

## 🗄️ Architecture Backend

### Nouvelle Collection : `conversations`

```python
{
  _id: ObjectId,
  user_id: ObjectId,
  organization_id: ObjectId,
  title: str,  # Première question ou "Conversation du [date]"
  messages: [
    {
      role: "user" | "assistant",
      content: str,
      timestamp: datetime,
      question_id: Optional[str]  # Lien vers la question si créée
    }
  ],
  created_at: datetime,
  updated_at: datetime,
  message_count: int  # Nombre de messages (pour quota)
}
```

**Indexes MongoDB :**
- `user_id` + `updated_at` (pour liste des conversations)
- `_id` (pour récupération rapide)

### Nouveaux Modèles (`app/models/conversation.py`)

**Fonctions à créer :**

1. `create_conversation(user_id, organization_id, first_question, first_answer) -> dict`
   - Crée une nouvelle conversation
   - Ajoute le premier message user + assistant
   - Retourne la conversation avec `conversation_id`

2. `add_message_to_conversation(conversation_id, role, content, question_id=None) -> dict`
   - Ajoute un message à une conversation existante
   - Met à jour `updated_at` et `message_count`

3. `get_conversation_by_id(conversation_id, user_id) -> Optional[dict]`
   - Récupère une conversation (vérifie que l'user en est propriétaire)

4. `list_user_conversations(user_id, limit=20) -> List[dict]`
   - Liste les conversations de l'utilisateur (triées par `updated_at` DESC)
   - Retourne titre, date, nombre de messages, dernier message

5. `get_conversation_history(conversation_id, user_id, max_messages=20) -> List[dict]`
   - Récupère l'historique d'une conversation
   - Limite à `max_messages` derniers messages (pour éviter tokens excessifs)

6. `delete_conversation(conversation_id, user_id) -> bool`
   - Supprime une conversation (et ses messages associés)

### Nouveaux Schémas (`app/schemas/conversation.py`)

```python
class ConversationCreate(BaseModel):
    question: str
    context: Optional[str] = None

class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: str
    question_id: Optional[str] = None

class ConversationPublic(BaseModel):
    id: str
    user_id: str
    organization_id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str
    last_message: Optional[str] = None

class ConversationDetail(ConversationPublic):
    messages: List[ConversationMessage]

class ConversationAskRequest(BaseModel):
    question: str
    context: Optional[str] = None
    conversation_id: Optional[str] = None  # Si None, crée une nouvelle conversation
```

### Nouveaux Endpoints (`app/routers/conversation.py`)

**Router :** `/conversations`

1. `POST /conversations/ask`
   - **Body :** `ConversationAskRequest` (question, context, conversation_id optionnel)
   - **Logique :**
     - Si `conversation_id` fourni : récupère l'historique
     - Sinon : crée une nouvelle conversation
     - Vérifie le quota (chaque question compte)
     - Appelle `generate_question_answer()` avec historique
     - Ajoute question + réponse à la conversation
     - Retourne réponse + `conversation_id`
   - **Response :** `{ conversation_id: str, answer: str, message: ConversationMessage }`

2. `GET /conversations`
   - Liste les conversations de l'utilisateur
   - **Response :** `List[ConversationPublic]`

3. `GET /conversations/{conversation_id}`
   - Détails d'une conversation (avec historique complet)
   - **Response :** `ConversationDetail`

4. `DELETE /conversations/{conversation_id}`
   - Supprime une conversation
   - **Response :** `{ success: bool, message: str }`

### Modification de `generate_question_answer()`

**Fichier :** `app/services/ai_service.py`

**Signature modifiée :**
```python
async def generate_question_answer(
    question: str,
    context: Optional[str] = None,
    user_department: Optional[str] = None,
    user_service: Optional[str] = None,
    organization_id: Optional[str] = None,
    conversation_history: Optional[List[Dict]] = None  # NOUVEAU
) -> str
```

**Logique modifiée :**
- Si `conversation_history` fourni :
  - Construire le prompt avec l'historique complet
  - Format : "Voici l'historique de notre conversation : [messages précédents]"
  - Ajouter la nouvelle question
  - L'IA génère une réponse contextuelle
- Sinon : comportement actuel (question isolée)

**Limite de contexte :**
- Envoyer seulement les 10-15 derniers messages à l'IA (pour éviter tokens excessifs)
- Garder tous les messages dans MongoDB pour l'affichage

### Modification du Quota

**Fichier :** `app/models/question.py`

**Modification de `check_user_quota()` :**
- Compter aussi les messages des conversations
- Un message dans une conversation = 1 question dans le quota
- `message_count` dans `conversations` compte dans le quota mensuel

**Option :** Créer aussi une question dans `questions` pour chaque message de conversation (pour compatibilité avec les stats existantes)

---

## 🎨 Architecture Frontend

### Nouveau Composant : `ConversationTab.jsx`

**Localisation :** `src/components/userDashboard/ConversationTab.jsx`

**Fonctionnalités :**
- Interface de chat (messages empilés verticalement)
- Zone de saisie en bas
- Affichage chronologique : questions à droite, réponses à gauche
- Scroll automatique vers le dernier message
- Bouton "Nouvelle conversation"
- Sidebar avec liste des conversations (optionnel)

**État React :**
```javascript
const [currentConversationId, setCurrentConversationId] = useState(null);
const [messages, setMessages] = useState([]);
const [conversations, setConversations] = useState([]);
const [isLoading, setIsLoading] = useState(false);
```

**Fonctions :**
- `handleSendMessage(question)` : Envoie une question dans la conversation actuelle
- `handleNewConversation()` : Réinitialise et crée une nouvelle conversation
- `loadConversation(conversationId)` : Charge une conversation existante
- `fetchConversations()` : Charge la liste des conversations

### Modification de `UserDashboardPage.jsx`

**Ajouter un onglet "Conversations" :**
- Nouvel onglet dans `tabsConfig` : `{ id: "conversations", label: "Conversations", icon: "💬" }`
- Import de `ConversationTab`
- Rendu conditionnel : `{activeTab === "conversations" && <ConversationTab />}`

**État partagé :**
- `quotaStats` : Partagé avec QuestionsTab (même quota)

### Modification de `QuestionsTab.jsx`

**Aucune modification nécessaire** : reste tel quel pour les questions simples

---

## 🔄 Flux Utilisateur

### Mode Question Simple (existant)

1. Utilisateur ouvre "Mes Questions"
2. Saisit une question → Envoie
3. Réponse affichée
4. Chaque question est indépendante

### Mode Conversation (nouveau)

1. Utilisateur ouvre "Conversations"
2. **Première question** :
   - Saisit une question → Envoie
   - Backend crée une nouvelle conversation
   - Retourne `conversation_id` + réponse
   - Frontend sauvegarde `conversation_id` et affiche Q/R
3. **Questions suivantes** :
   - Saisit une nouvelle question → Envoie
   - Backend récupère l'historique de la conversation
   - Envoie à l'IA avec contexte complet
   - Retourne réponse
   - Frontend ajoute Q/R à l'historique
4. **Nouvelle conversation** :
   - Utilisateur clique "Nouvelle conversation"
   - Frontend réinitialise `currentConversationId = null`
   - Prochaine question crée une nouvelle conversation

---

## 📝 Détails Techniques

### Gestion du Contexte pour l'IA

**Format du prompt avec historique :**
```
Tu es Fahimta AI...

HISTORIQUE DE LA CONVERSATION :
- Utilisateur : [question 1]
- Assistant : [réponse 1]
- Utilisateur : [question 2]
- Assistant : [réponse 2]
...

CONTEXTE ACTUEL (base de connaissances) :
[Extraits ORG + GLOBAL]

NOUVELLE QUESTION :
[question actuelle]

Réponds en tenant compte de tout l'historique et du contexte.
```

**Limite de tokens :**
- Historique limité à 10-15 derniers messages
- Si conversation très longue, prendre seulement les plus récents
- Garder tous les messages dans MongoDB pour l'affichage

### Quota et Comptage

**Option 1 : Comptage séparé**
- Questions simples : comptées dans `questions`
- Messages de conversation : comptés dans `conversations.message_count`
- Quota total = somme des deux

**Option 2 : Comptage unifié (recommandé)**
- Créer aussi une entrée dans `questions` pour chaque message de conversation
- `question_id` dans `conversations.messages` pointe vers `questions._id`
- Quota = comptage dans `questions` (comme actuellement)
- Avantage : Compatibilité avec les stats existantes

**Recommandation : Option 2** (comptage unifié)

### Performance

**Indexes MongoDB :**
```python
# Collection conversations
db.conversations.create_index([("user_id", 1), ("updated_at", -1)])
db.conversations.create_index([("_id", 1)])

# Collection questions (existant)
# Pas de modification nécessaire
```

**Limite de messages dans l'historique :**
- Pour l'IA : 10-15 derniers messages (éviter tokens excessifs)
- Pour l'affichage : Tous les messages (pas de limite)

---

## ✅ Checklist d'Implémentation

### Backend

- [ ] Créer `app/models/conversation.py` avec toutes les fonctions
- [ ] Créer `app/schemas/conversation.py` avec les schémas Pydantic
- [ ] Créer `app/routers/conversation.py` avec les 4 endpoints
- [ ] Modifier `app/services/ai_service.py` : ajouter `conversation_history` à `generate_question_answer()`
- [ ] Modifier `app/models/question.py` : adapter le comptage de quota pour inclure les conversations
- [ ] Ajouter les indexes MongoDB pour `conversations`
- [ ] Tester les endpoints avec Postman/curl

### Frontend

- [ ] Créer `src/components/userDashboard/ConversationTab.jsx`
- [ ] Modifier `UserDashboardPage.jsx` : ajouter onglet "Conversations"
- [ ] Créer les fonctions API dans `src/api.js` (ou fichier séparé)
- [ ] Implémenter l'interface de chat (messages empilés)
- [ ] Implémenter le bouton "Nouvelle conversation"
- [ ] Implémenter le chargement d'une conversation existante
- [ ] Implémenter la liste des conversations (sidebar ou dropdown)
- [ ] Tester le flux complet

### Tests

- [ ] Test : Créer une nouvelle conversation
- [ ] Test : Ajouter plusieurs messages dans une conversation
- [ ] Test : Vérifier que l'historique est bien utilisé par l'IA
- [ ] Test : Vérifier le quota (chaque message compte)
- [ ] Test : Créer une nouvelle conversation après une conversation existante
- [ ] Test : Charger une conversation existante
- [ ] Test : Supprimer une conversation
- [ ] Test : Questions simples toujours fonctionnelles (pas de régression)

---

## 🎯 Points d'Attention

1. **Pas de régression** : Les questions simples doivent continuer à fonctionner exactement comme avant

2. **Quota unifié** : Un message de conversation = 1 question dans le quota (comme une question simple)

3. **Performance** : Limiter l'historique envoyé à l'IA (10-15 messages max) pour éviter les coûts/tokens excessifs

4. **UX** : Interface claire pour distinguer "Questions simples" vs "Conversations"

5. **Migration** : Pas de migration nécessaire (nouvelle collection, pas de modification des données existantes)

6. **Sécurité** : Vérifier que l'utilisateur ne peut accéder qu'à ses propres conversations

---

## 📊 Résumé des Collections MongoDB

### Collection `questions` (existant - pas de modification)
- Questions simples (mode actuel)
- Peut aussi contenir les questions des conversations (si Option 2 choisie)

### Collection `conversations` (nouveau)
- Conversations avec historique
- Chaque conversation contient plusieurs messages
- Lien optionnel vers `questions` pour compatibilité quota

---

## 🚀 Ordre d'Implémentation Recommandé

1. **Backend - Modèles** : Créer `conversation.py` avec toutes les fonctions CRUD
2. **Backend - Schémas** : Créer les schémas Pydantic
3. **Backend - Service IA** : Modifier `generate_question_answer()` pour accepter l'historique
4. **Backend - Endpoints** : Créer les 4 endpoints de conversation
5. **Backend - Quota** : Adapter le comptage de quota
6. **Frontend - API** : Créer les appels API
7. **Frontend - Composant** : Créer `ConversationTab.jsx`
8. **Frontend - Intégration** : Ajouter l'onglet dans `UserDashboardPage`
9. **Tests** : Tester le flux complet
10. **Documentation** : Mettre à jour la doc si nécessaire

---

## ❓ Questions à Clarifier

1. **Comptage quota** : Option 1 (séparé) ou Option 2 (unifié) ?
   - **Recommandation : Option 2** (créer aussi une question dans `questions`)

2. **Limite de messages dans l'historique pour l'IA** : 10, 15, ou 20 ?
   - **Recommandation : 15 messages** (équilibre contexte/coût)

3. **Interface** : Sidebar avec liste des conversations ou dropdown simple ?
   - **Recommandation : Dropdown simple** pour commencer (moins complexe)

4. **Titre de conversation** : Première question ou "Conversation du [date]" ?
   - **Recommandation : Première question** (plus informatif)

5. **Suppression** : Permettre la suppression d'une conversation ?
   - **Recommandation : Oui** (avec confirmation)

---

## 📋 Prêt pour Implémentation

Une fois ces points clarifiés, on peut procéder à l'implémentation étape par étape.

