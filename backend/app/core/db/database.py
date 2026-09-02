from sqlalchemy import create_engine
# Importa o 'DeclarativeBase' (classe) e sessionmaker
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

# SQLAlchemy's create_engine expects a string, so we must convert the Pydantic DSN object.
engine = create_engine(
    str(settings.DATABASE_URL),
    pool_size=20,
    max_overflow=20,
    pool_timeout=30.0,
    pool_pre_ping=True,
    pool_recycle=300
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)

# Nós importamos 'DeclarativeBase' e herdamos dela.
class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
