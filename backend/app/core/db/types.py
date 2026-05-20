import hashlib
import base64
import json
import enum
from typing import Any, Optional
from cryptography.fernet import Fernet
from sqlalchemy import String, TypeDecorator, Text, Numeric, Integer
from app.core.config import settings

class EncryptedString(TypeDecorator):
    """
    SQLAlchemy TypeDecorator that encrypts a string before saving to the database
    and decrypts it when reading from the database.
    
    Uses cryptography.fernet (symmetric encryption) with a key derived from settings.SECRET_KEY.
    """
    impl = Text
    cache_ok = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Derive a 32-byte key from the SECRET_KEY for Fernet
        # Fernet requires a base64url-encoded 32-byte key.
        key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        self.fernet = Fernet(base64.urlsafe_b64encode(key))

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        return self.fernet.encrypt(value.encode()).decode()

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        try:
            return self.fernet.decrypt(value.encode()).decode()
        except Exception:
            # If decryption fails (e.g. data is not encrypted or key changed), 
            # return the original value to avoid breaking existing data.
            return value

class EncryptedJSON(EncryptedString):
    """
    Extension of EncryptedString that handles JSON serialization/deserialization
    transparently while storing the data encrypted in the database.
    """
    def process_bind_param(self, value: Any, dialect) -> Optional[str]:
        if value is None:
            return None
        json_str = json.dumps(value)
        return super().process_bind_param(json_str, dialect)

    def process_result_value(self, value: Optional[str], dialect) -> Any:
        decrypted = super().process_result_value(value, dialect)
        if decrypted is None:
            return None
        try:
            return json.loads(decrypted)
        except Exception:
            return decrypted

class IntEnum(TypeDecorator):
    """
    Permite o uso de Enums do Python que são persistidos como inteiros no banco de dados.
    """
    impl = Integer
    cache_ok = True

    def __init__(self, enumtype, *args, **kwargs):
        super(IntEnum, self).__init__(*args, **kwargs)
        self._enumtype = enumtype

    def process_bind_param(self, value, dialect):
        if isinstance(value, self._enumtype):
            return value.value
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            try:
                return self._enumtype(value)
            except ValueError:
                if isinstance(value, str):
                    if value.isdigit():
                        return self._enumtype(int(value))
                    if value in self._enumtype.__members__:
                        return self._enumtype[value]
                raise
        return value

    @property
    def python_type(self):
        return self._enumtype

class SafeStrEnum(TypeDecorator):
    """
    TypeDecorator para Enums de string que trata valores inválidos (como '') como None
    ao carregar do banco de dados, evitando LookupError.
    """
    impl = String
    cache_ok = True

    def __init__(self, enumtype, *args, **kwargs):
        super(SafeStrEnum, self).__init__(*args, **kwargs)
        self._enumtype = enumtype

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, self._enumtype):
            return value.value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is not None:
            str_val = str(value).strip()
            if str_val != '':
                try:
                    return self._enumtype(value)
                except (ValueError, KeyError):
                    if value in self._enumtype.__members__:
                        return self._enumtype[value]
                    return None
        return None

class Currency(Numeric):
    """Tipo customizado para valores monetários (BRL)."""
    def __init__(self, precision=15, scale=2, asdecimal=True, **kwargs):
        super().__init__(precision=precision, scale=scale, asdecimal=asdecimal, **kwargs)
