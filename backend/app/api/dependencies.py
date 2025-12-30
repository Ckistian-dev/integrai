from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from typing import Optional

from app.core.config import settings
from app.core.db import models
from app.core.db.database import get_db
from app.core.db.schemas import TokenData, UsuarioPerfilEnum
from app.crud import crud_user

# Esta é a URL que o frontend usará para fazer login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login/token")

def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> models.Usuario:
    """
    Dependência de segurança:
    1. Valida o token JWT.
    2. Extrai o id_usuario.
    3. Retorna o objeto Usuario do banco de dados.
    Esta função será injetada em todos os endpoints protegidos.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        id_usuario: Optional[int] = payload.get("id_usuario")
        id_empresa: Optional[int] = payload.get("id_empresa")
        perfil: Optional[UsuarioPerfilEnum] = payload.get("perfil")
        
        if id_usuario is None or id_empresa is None or perfil is None: 
            raise credentials_exception
        
        token_data = TokenData(id_usuario=id_usuario, id_empresa=id_empresa, perfil=perfil) 
        
    except JWTError:
        raise credentials_exception
    
    # 'user' é buscado no banco de dados aqui
    user = db.query(models.Usuario).filter(models.Usuario.id == token_data.id_usuario).first()
    
    if user is None:
        raise credentials_exception
    
    # IMPORTANTE: Verificamos também se o usuário ainda pertence ao mesmo business
    if user.id_empresa != token_data.id_empresa:
        raise credentials_exception
        
    user.perfil = perfil
        
    return user

def get_current_active_user(
    current_user: models.Usuario = Depends(get_current_user)
) -> models.Usuario:
    """
    Dependência que verifica se o usuário retornado por get_current_user está ativo.
    """
    if not current_user.situacao:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def get_admin_user(
    current_user: models.Usuario = Depends(get_current_active_user)
) -> models.Usuario:
    """
    Dependência que verifica se o usuário logado é um admin.
    Levanta um erro 403 (Forbidden) se não for.
    """
    if current_user.perfil != UsuarioPerfilEnum.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="The user does not have administrative privileges"
        )
    return current_user