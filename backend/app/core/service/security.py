from datetime import datetime, timedelta, timezone
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt

from app.core.config import settings

# Configuração do Hashing de Senha
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha plana corresponde ao hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(senha: str) -> str:
    """Gera o hash de uma senha."""
    return pwd_context.hash(senha)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Cria um novo token de acesso JWT.
    Os dados (data) devem conter 'user_id' e 'business_id'.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt
