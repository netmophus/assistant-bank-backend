from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    full_name: str


class UserCreate(UserBase):
    password: str = Field(min_length=6)
    organization_id: Optional[str] = Field(None, description="Laisse vide = compte demo MIZNAS")
    department_id: Optional[str] = Field(None, description="ID du département")
    service_id: Optional[str] = Field(None, description="ID du service")
    role: Optional[str] = Field(default="user", description="Rôle de l'utilisateur")
    role_departement: Optional[str] = Field(
        None,
        description="Rôle dans le département: 'agent', 'chef_service', 'directeur'",
    )


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=6)
    organization_id: Optional[str] = None
    department_id: Optional[str] = Field(None, description="ID du département")
    service_id: Optional[str] = Field(None, description="ID du service")
    role: Optional[str] = None
    role_departement: Optional[str] = None
    is_active: Optional[bool] = None


class UserPublic(UserBase):
    id: str
    organization_id: Optional[str] = None  # None pour les super admins
    organization_name: Optional[str] = None  # Nom de l'organisation
    organization_code: Optional[str] = None  # Code de l'organisation (ex: CATALOGUE)
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    service_id: Optional[str] = None
    service_name: Optional[str] = None
    role: Optional[str] = None  # Rôle système
    role_departement: Optional[str] = None  # Rôle dans le département
    is_active: Optional[bool] = True  # Statut actif/inactif de l'utilisateur
    # Champs DEMO (inscription publique via app.miznas.co)
    is_demo: Optional[bool] = None
    email_verified: Optional[bool] = None
    phone_country_code: Optional[str] = None
    phone_number: Optional[str] = None


class LoginData(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[str] = None
    email: Optional[EmailStr] = None


class StockUserCreate(UserBase):
    """Schéma pour créer un gestionnaire de stock ou un agent DRH"""
    password: str = Field(min_length=6)
    role: str = Field(..., description="Rôle: 'gestionnaire_stock' ou 'agent_stock_drh'")
    department_id: Optional[str] = Field(None, description="ID du département (optionnel pour gestionnaire stock)")


class RegisterDemoRequest(BaseModel):
    """Inscription DEMO via app mobile (phase 1 : pas d'OTP, pas de limites)."""
    email: EmailStr
    password: str = Field(min_length=6)
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    phone_country_code: str = Field(min_length=2, description="Ex: +227")
    phone_number: str = Field(min_length=6)


class DemoRegisterResponse(BaseModel):
    """Réponse de /auth/register-demo : token JWT + user complet."""
    access_token: str
    token_type: str = "bearer"
    user: UserPublic
