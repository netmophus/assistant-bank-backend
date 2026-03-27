from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class GlobalDocumentBase(BaseModel):
    titre: str = Field(..., description="Titre du document")
    description: Optional[str] = Field(None, description="Description du document")
    category: str = Field(..., description="Catégorie: plan_comptable | commission_bancaire | lb_ft | general")
    authority: Optional[str] = Field(None, description="Autorité émettrice")
    reference: Optional[str] = Field(None, description="Référence officielle")
    version: Optional[str] = Field("1.0", description="Version du document")
    effective_date: Optional[datetime] = Field(None, description="Date d'entrée en vigueur")


class GlobalDocumentCreate(GlobalDocumentBase):
    pass


class GlobalDocumentUpdate(BaseModel):
    titre: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    authority: Optional[str] = None
    reference: Optional[str] = None
    version: Optional[str] = None
    effective_date: Optional[datetime] = None
    status: Optional[str] = None  # draft | published | archived


class GlobalDocumentPublic(BaseModel):
    id: str
    titre: str
    description: Optional[str]
    category: str
    authority: Optional[str]
    reference: Optional[str]
    version: Optional[str]
    effective_date: Optional[datetime]
    status: str  # draft | published | archived
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    upload_date: datetime
    uploaded_by: str
    published_date: Optional[datetime]
    total_chunks: int

    class Config:
        from_attributes = True


class GlobalDocumentListResponse(BaseModel):
    documents: List[GlobalDocumentPublic]
    total: int

