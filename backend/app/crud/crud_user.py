from sqlalchemy.orm import Session
from typing import Optional, Any

from app.core.db import models
from app.core.db.schemas import  UsuarioCreate,  UsuarioUpdate
from app.core.service.security import get_password_hash, verify_password

# Nota: Todas as funções recebem 'db: Session' como primeiro argumento.

def get_user_by_email(db: Session, email: str) -> Optional[models. Usuario]:
    """Busca um usuário pelo email."""
    return db.query(models. Usuario).filter(models. Usuario.email == email).first()

def get_user(db: Session, user_id: int) -> Optional[models. Usuario]:
    """Busca um usuário pelo ID."""
    return db.query(models. Usuario).filter(models. Usuario.id == user_id).first()

def create_user(db: Session, *, obj_in:  UsuarioCreate, id_empresa: int) -> models. Usuario:
    """Cria um novo usuário no banco de dados."""
    senha = get_password_hash(obj_in.senha)
    
    # Cria o dict de dados, excluindo a senha plana
    db_obj_data = obj_in.model_dump(exclude={"senha"})
    
    db_user = models. Usuario(
        **db_obj_data,
        senha=senha,
        id_empresa=id_empresa
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(db: Session, email: str, senha: str) -> Optional[models. Usuario]:
    """
    Autentica um usuário. Retorna o usuário se for válido, senão None.
    """
    print(f"[DEBUG AUTH] Tentando autenticar usuário com email: '{email}'")
    
    # Adicionamos order_by id_empresa desc para tentar contornar temporariamente casos de empresas antigas
    user = db.query(models. Usuario).filter(models. Usuario.email == email).order_by(models.Usuario.id.desc()).first()
    
    if not user:
        print(f"[DEBUG AUTH] Falha: Usuário com email '{email}' não encontrado no banco de dados.")
        return None
        
    print(f"[DEBUG AUTH] Usuário encontrado: ID={user.id}, Empresa={user.id_empresa}")
    
    if not verify_password(senha, user.senha):
        print(f"[DEBUG AUTH] Falha: Senha incorreta para o usuário '{email}' (ID={user.id}, Empresa={user.id_empresa}).")
        return None
        
    print(f"[DEBUG AUTH] Sucesso: Usuário '{email}' autenticado corretamente para Empresa={user.id_empresa}.")
    return user

def update_user(db: Session, *, db_obj: models. Usuario, obj_in:  UsuarioUpdate) -> models. Usuario:
    """Atualiza um usuário."""
    update_data = obj_in.model_dump(exclude_unset=True)

    # Se uma nova senha foi fornecida, hasheia ela
    if "senha" in update_data and update_data["senha"]:
        senha = get_password_hash(update_data["senha"])
        db_obj.senha = senha
        del update_data["senha"] # Remove para não tentar setar duas vezes

    # Atualiza os outros campos
    for field, value in update_data.items():
        setattr(db_obj, field, value)

    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

# Adicione outras funções de 'user' aqui se precisar
# (ex: delete_user, get_users_by_business, etc.)

def get(db: Session, model: Any, id: int, id_empresa: int) -> Optional[models.Usuario]:
    """Generic get for user, compatible with generic endpoint signature."""
    return db.query(models.Usuario).filter(models.Usuario.id == id, models.Usuario.id_empresa == id_empresa).first()

def delete(db: Session, model: Any, id: int, id_empresa: int) -> Optional[models.Usuario]:
    """Generic delete for user, compatible with generic endpoint signature."""
    obj = db.query(models.Usuario).filter(models.Usuario.id == id, models.Usuario.id_empresa == id_empresa).first()
    if obj:
        db.delete(obj)
        db.commit()
    return obj
