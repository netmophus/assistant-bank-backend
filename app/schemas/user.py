from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class UserBase(BaseModel):
    email: EmailStr
    full_name: str


class UserCreate(UserBase):
    password: str = Field(min_length=6)
    organization_id: str
    department_id: Optional[str] = Field(None, description="ID du département")
    service_id: Optional[str] = Field(None, description="ID du service")
    role: Optional[str] = Field(default="user", description="Rôle de l'utilisateur: 'user', 'admin' (admin d'organisation) ou 'superadmin' (super admin)")


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=6)
    organization_id: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserPublic(UserBase):
    id: str
    organization_id: Optional[str] = None  # None pour les super admins
    organization_name: Optional[str] = None  # Nom de l'organisation
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    service_id: Optional[str] = None
    service_name: Optional[str] = None
    role: Optional[str] = None  # Ajouter le rôle pour le frontend


class LoginData(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[str] = None
    email: Optional[EmailStr] = None
