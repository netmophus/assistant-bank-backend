from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class DocumentBase(BaseModel):
    filename: str
    category: str = Field(..., description="Catégorie du document")
    subcategory: Optional[str] = None
    tags: List[str] = []
    description: Optional[str] = None


class DocumentCreate(DocumentBase):
    pass


class DocumentUpdate(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: Optional[List[str]] = None
    description: Optional[str] = None
    status: Optional[str] = None  # "active", "archived"


class DocumentPublic(BaseModel):
    id: str
    filename: str
    original_filename: str
    file_type: str  # "pdf", "word", "excel"
    file_size: int
    category: str
    subcategory: Optional[str] = None
    tags: List[str]
    description: Optional[str] = None
    upload_date: datetime
    uploaded_by: str
    status: str  # "pending", "processing", "processed", "error"
    total_chunks: int
    organization_id: str
    departments: Optional[List[dict]] = Field(default_factory=list, description="Départements assignés au document")

    class Config:
        from_attributes = True


class DocumentChunkPublic(BaseModel):
    id: str
    document_id: str
    chunk_index: int
    content: str
    page_number: Optional[int] = None
    section: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    documents: List[DocumentPublic]
    total: int


class DocumentStats(BaseModel):
    total_documents: int
    total_chunks: int
    total_size: int
    by_category: dict
    by_status: dict


class DocumentDepartmentAssignment(BaseModel):
    """Schéma pour l'affectation d'un document à des départements"""
    department_ids: List[str] = Field(..., description="Liste des IDs des départements")
