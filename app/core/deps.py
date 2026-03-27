from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from bson import ObjectId

from app.core.security import decode_access_token
from app.models.user import get_user_by_id, _user_doc_to_public

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Récupère l'utilisateur courant à partir du token JWT.
    """
    token_data = decode_access_token(token)
    if not token_data or not token_data.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré.",
        )

    user = await get_user_by_id(token_data.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur introuvable.",
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Utilisateur désactivé.",
        )

    # Convertir le document MongoDB en format public avec "id" au lieu de "_id"
    return _user_doc_to_public(user)


async def get_org_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Vérifie que l'utilisateur est un administrateur d'organisation.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs d'organisation.",
        )
    
    return current_user


async def get_superadmin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Vérifie que l'utilisateur est un super administrateur.
    """
    user_role = current_user.get("role", "user")
    
    if user_role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux super administrateurs.",
        )
    
    return current_user
