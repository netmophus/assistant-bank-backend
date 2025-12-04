from datetime import datetime, timedelta
from typing import Optional
import hashlib
import logging
import bcrypt

from jose import jwt, JWTError
from passlib.context import CryptContext

from .config import settings
from app.schemas.user import TokenData

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _preprocess_password(password: str) -> str:
    """
    Preprocess password to handle bcrypt's 72-byte limit.
    Hash with SHA-256 to ensure consistent length (32 bytes).
    """
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    Preprocesses the password with SHA-256 to handle bcrypt's 72-byte limit.
    Uses bcrypt directly to avoid passlib's bug detection issue with long passwords.
    """
    preprocessed = _preprocess_password(password)
    # Use bcrypt directly instead of passlib to avoid the bug detection issue
    # The preprocessed password is always 64 hex characters (32 bytes), well under 72 bytes
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(preprocessed.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a bcrypt hash.
    Preprocesses the password with SHA-256 to handle bcrypt's 72-byte limit.
    Also supports backward compatibility with old password hashes.
    """
    if not plain_password or not hashed_password:
        logger.debug("verify_password: Missing password or hash")
        return False
    
    # Normalize password (strip whitespace, but keep it as-is for now to avoid breaking existing passwords)
    # Note: We don't strip whitespace to maintain compatibility with existing passwords
    
    # Ensure hashed_password is a string (in case it's stored as bytes or other type)
    if not isinstance(hashed_password, str):
        hashed_password = str(hashed_password)
    
    # Strip whitespace from hash (shouldn't have any, but just in case)
    hashed_password = hashed_password.strip()
    
    # Check hash format (bcrypt hashes start with $2a$, $2b$, or $2y$)
    if not hashed_password.startswith(('$2a$', '$2b$', '$2y$')):
        logger.warning(f"verify_password: Invalid hash format: {hashed_password[:20]}...")
        return False
    
    # Try OLD method FIRST (for backward compatibility with existing passwords)
    # This handles passwords that were hashed directly with bcrypt (without SHA-256 preprocessing)
    password_bytes = plain_password.encode('utf-8')
    
    if len(password_bytes) <= 72:
        # Password is short enough for direct bcrypt
        try:
            if pwd_context.verify(plain_password, hashed_password):
                logger.debug("verify_password: Verified with old method (direct bcrypt)")
                return True
        except (ValueError, Exception) as e:
            logger.debug(f"verify_password: Old method failed: {type(e).__name__}: {str(e)}")
            # Continue to try new method
            pass
    else:
        # Password is > 72 bytes - truncate to 72 bytes for old method compatibility
        # Bcrypt truncates at byte level during hashing, so we need to match that behavior
        logger.debug(f"verify_password: Password too long ({len(password_bytes)} bytes), truncating for old method")
        try:
            # Truncate to 72 bytes (matching bcrypt's behavior)
            truncated_bytes = password_bytes[:72]
            # Decode, handling potential incomplete UTF-8 sequences at the end
            truncated_password = truncated_bytes.decode('utf-8', errors='ignore')
            # Try with truncated password
            if pwd_context.verify(truncated_password, hashed_password):
                logger.debug("verify_password: Verified with old method (truncated password)")
                return True
        except (ValueError, Exception) as e:
            logger.debug(f"verify_password: Old method with truncated password failed: {type(e).__name__}: {str(e)}")
            # Continue to try new method
            pass
    
    # If old method didn't match, try new method: preprocess with SHA-256
    # This handles passwords that were hashed with SHA-256 preprocessing
    try:
        preprocessed = _preprocess_password(plain_password)
        # Use bcrypt directly for new method (consistent with hash_password)
        if bcrypt.checkpw(preprocessed.encode('utf-8'), hashed_password.encode('utf-8')):
            logger.debug("verify_password: Verified with new method (SHA-256 preprocessing)")
            return True
        else:
            logger.debug("verify_password: New method verification returned False (hash doesn't match)")
    except (ValueError, Exception) as e:
        logger.debug(f"verify_password: New method failed with exception: {type(e).__name__}: {str(e)}")
        pass
    
    logger.debug("verify_password: All verification methods failed")
    return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenData]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        if user_id is None or email is None:
            return None
        return TokenData(user_id=user_id, email=email)
    except JWTError:
        return None
