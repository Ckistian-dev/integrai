import time
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.db.database import get_db
from app.core.db.schemas import Token # Importa o schema Token
from app.crud import crud_user, crud_business
from app.core.service import security
from app.core.logger import log_info, log_warning, log_error
from app.core.error_codes import AuthErrorCode, LogStatus

router = APIRouter()

# Rate limiting em memória contra ataques de força bruta no login
_LOGIN_ATTEMPTS = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 8
LOCKOUT_DURATION_SECONDS = 60

def _check_rate_limit(key: str):
    now = time.time()
    _LOGIN_ATTEMPTS[key] = [t for t in _LOGIN_ATTEMPTS[key] if now - t < LOCKOUT_DURATION_SECONDS]
    if len(_LOGIN_ATTEMPTS[key]) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas consecutivas de login. Aguarde 60 segundos antes de tentar novamente."
        )

def _record_failed_attempt(key: str):
    _LOGIN_ATTEMPTS[key].append(time.time())

def _clear_attempts(key: str):
    _LOGIN_ATTEMPTS.pop(key, None)

@router.post("/login/token", response_model=Token)
def login_for_access_token(
    request: Request,
    db: Session = Depends(get_db), 
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    Endpoint de login. Recebe email (no campo 'username') e senha.
    Retorna um token JWT protegido com limitação de taxa contra força bruta.
    """
    client_ip = request.client.host if request.client else "unknown"
    rate_limit_key = f"{client_ip}:{form_data.username.lower()}"
    _check_rate_limit(rate_limit_key)

    log_info("AUTH", "auth_endpoint", "login_for_access_token", LogStatus.PROCESSING,
             f"Recebida requisição de login para: {form_data.username}", {"username": form_data.username})
    user = crud_user.authenticate_user(
        db, email=form_data.username, senha=form_data.password
    )
    if not user:
        _record_failed_attempt(rate_limit_key)
        log_warning("AUTH", "auth_endpoint", "login_for_access_token", AuthErrorCode.INVALID_CREDENTIALS,
                    f"Falha no login: credenciais inválidas para {form_data.username}", {"username": form_data.username})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or senha",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Limpa contagem de falhas após login bem-sucedido
    _clear_attempts(rate_limit_key)

    log_info("AUTH", "auth_endpoint", "login_for_access_token", LogStatus.SUCCESS,
             f"Login realizado com sucesso. Gerando token JWT", {"user_id": user.id, "id_empresa": user.id_empresa})
        
    business = crud_business.get_business(db, id_empresa=user.id_empresa)
    if not business:
        log_error("AUTH", "auth_endpoint", "login_for_access_token", AuthErrorCode.USER_NOT_FOUND,
                  f"Empresa não encontrada para o usuário {user.id}", context={"user_id": user.id, "id_empresa": user.id_empresa})
        raise HTTPException(status_code=404, detail="Business not found for user")
    
    # Dados que serão armazenados dentro do token JWT
    token_data = {
        "id_usuario": user.id,
        "id_empresa": user.id_empresa,
        "empresa_fantasia": business.fantasia if business.fantasia else business.razao,
        "email": user.email,
        "perfil": user.perfil_rel.nome if user.perfil_rel else "Sem Perfil",
        "permissoes": user.perfil_rel.permissoes if user.perfil_rel else {},
        "cor_sidebar": business.cor_sidebar
    }
    
    access_token = security.create_access_token(data=token_data)
    
    return {"access_token": access_token, "token_type": "bearer"}
