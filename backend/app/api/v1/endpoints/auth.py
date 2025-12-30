from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.db.database import get_db
from app.core.db.schemas import Token # Importa o schema Token
from app.crud import crud_user, crud_business
from app.core.service import security

router = APIRouter()

@router.post("/login/token", response_model=Token)
def login_for_access_token(
    db: Session = Depends(get_db), 
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    Endpoint de login. Recebe email (no campo 'username') e senha.
    Retorna um token JWT.
    """
    user = crud_user.authenticate_user(
        db, email=form_data.username, senha=form_data.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or senha",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    business = crud_business.get_business(db, id_empresa=user.id_empresa) # Corrigido para get_empresa/id_empresa
    if not business:
        raise HTTPException(status_code=404, detail="Business not found for user")
    
    # Dados que serão armazenados dentro do token JWT
    token_data = {
        "id_usuario": user.id,
        "id_empresa": user.id_empresa,
        "empresa_fantasia": business.fantasia if business.fantasia else business.razao,
        "email": user.email,
        "perfil": user.perfil.value # Passa o valor (string) do Enum
    }
    
    access_token = security.create_access_token(data=token_data)
    
    return {"access_token": access_token, "token_type": "bearer"}