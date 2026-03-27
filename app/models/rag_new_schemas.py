from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RagNewUploadMetadata(BaseModel):
    """Métadonnées optionnelles associées à un document uploadé."""

    source: Optional[str] = Field(None, description="Source du document (ex: 'BCEAO', 'UEMOA', 'interne')")
    title: Optional[str] = Field(None, description="Titre du document")
    tags: Optional[List[str]] = Field(default=None, description="Tags libres")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Champs additionnels")


class RagNewUploadResponse(BaseModel):
    """Réponse après ingestion (chunk + embedding + upsert)."""

    collection: str = Field(..., description="knowledge_global ou knowledge_local")
    document_count: int = Field(..., description="Nombre de documents (chunks) écrits")
    chunk_count: int = Field(..., description="Nombre de chunks générés")
    user_id: Optional[str] = Field(None, description="user_id si ingestion locale")
    created_at: datetime = Field(..., description="Date de traitement")


class RagNewQueryRequest(BaseModel):
    """Requête de question pour la nouvelle approche RAG."""

    question: str = Field(..., min_length=1, description="Question utilisateur")
    user_id: Optional[str] = Field(None, description="Compat: ancien identifiant utilisateur pour la base locale")
    category: Optional[str] = Field(None, description="Filtrer la recherche par catégorie (slug)")


class RagNewSource(BaseModel):
    """Source retournée (chunk) avec métadonnées."""

    id: str
    scope: str = Field(..., description="GLOBAL ou LOCAL")
    score: float
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RagNewSourceUsed(BaseModel):
    """Source utilisée (format compact) pour affichage côté UI."""

    documentName: str
    category: Optional[str] = None
    scope: str = Field(..., description="GLOBAL ou LOCAL")
    page: Optional[int] = None


class RagNewReference(BaseModel):
    """Référence réglementaire/procédurale extraite des extraits (si présente)."""

    textName: str = ""
    textNumber: str = ""
    article: str = ""
    section: str = ""
    scope: str = ""


class RagNewQueryResponse(BaseModel):
    """Réponse RAG avec éventuelles sources."""

    answer: str
    direct_answer: str = ""
    reference: RagNewReference = Field(default_factory=RagNewReference)
    grounded_summary: List[str] = Field(default_factory=list)
    helpful_explanation: str = ""
    expert_explanation: str = ""
    operational_impact: List[str] = Field(default_factory=list)
    limitations: str = ""
    used_retrieval: bool = Field(
        False,
        description="True si la réponse est principalement fondée sur des documents retrouvés (GLOBAL/LOCAL).",
    )
    usedRetrieval: bool = Field(
        False,
        description="Alias camelCase de used_retrieval (compat frontend).",
    )
    mode: str = Field(
        "LLM_ONLY",
        description="GLOBAL | LOCAL | LLM_ONLY (dépend des sources utilisées)",
    )
    sources_used: List[RagNewSourceUsed] = Field(default_factory=list)
    strategy: str = Field(
        ...,
        description="GLOBAL | LOCAL | LLM_ONLY (aucun document trouvé)",
    )
    sources: List[RagNewSource] = Field(default_factory=list)
    debug: Dict[str, Any] = Field(default_factory=dict)


class RagNewDocumentListItem(BaseModel):
    scope: str = Field(..., description="GLOBAL ou LOCAL")
    filename: str
    category: Optional[str] = None
    organization_id: Optional[str] = None
    chunk_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RagNewDocumentListResponse(BaseModel):
    total: int
    offset: int
    limit: int
    items: List[RagNewDocumentListItem] = Field(default_factory=list)
