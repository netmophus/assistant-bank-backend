import logging
from typing import List

from app.core.config import settings

logger = logging.getLogger(__name__)

# Configuration
OPENAI_API_KEY = settings.OPENAI_API_KEY
USE_OPENAI_EMBEDDINGS = bool(OPENAI_API_KEY)


async def generate_embedding(text: str) -> List[float]:
    """
    Génère un embedding pour un texte.
    Utilise OpenAI si disponible, sinon une méthode locale.
    """
    if USE_OPENAI_EMBEDDINGS:
        return await _generate_openai_embedding(text)
    else:
        # Fallback: retourner un vecteur vide pour l'instant
        # En production, utilisez Sentence Transformers local
        logger.warning("OpenAI API key non configurée. Embeddings désactivés.")
        return []


async def _generate_openai_embedding(text: str) -> List[float]:
    """Génère un embedding via OpenAI API."""
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        response = client.embeddings.create(
            model="text-embedding-3-small",  # ou text-embedding-ada-002
            input=text[:8000]  # Limite de tokens
        )
        return response.data[0].embedding
    except ImportError:
        logger.error("OpenAI n'est pas installé. Installez-le avec: pip install openai")
        return []
    except Exception as e:
        logger.error(f"Erreur lors de la génération d'embedding OpenAI: {e}", exc_info=True)
        return []


async def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Génère des embeddings pour plusieurs textes en batch.
    """
    if not texts:
        return []
    
    if USE_OPENAI_EMBEDDINGS:
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=OPENAI_API_KEY)
            
            # Limiter la taille des textes
            texts_limited = [text[:8000] if text else "" for text in texts]
            
            # Filtrer les textes vides
            non_empty_texts = [t for t in texts_limited if t.strip()]
            if not non_empty_texts:
                logger.warning("Aucun texte non vide à traiter")
                return [[] for _ in texts]
            
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=non_empty_texts
            )
            
            # Mapper les embeddings aux textes originaux
            embeddings_map = {text: item.embedding for text, item in zip(non_empty_texts, response.data)}
            result = []
            for text in texts_limited:
                if text.strip() and text in embeddings_map:
                    result.append(embeddings_map[text])
                else:
                    result.append([])
            
            return result
        except ImportError:
            logger.error("OpenAI n'est pas installé. Installez-le avec: pip install openai")
            return [[] for _ in texts]
        except Exception as e:
            logger.error(f"Erreur lors de la génération d'embeddings batch: {e}", exc_info=True)
            return [[] for _ in texts]
    else:
        logger.warning("OpenAI API key non configurée. Embeddings désactivés.")
        return [[] for _ in texts]

