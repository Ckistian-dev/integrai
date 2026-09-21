import re

def validar_cpf(cpf: str) -> bool:
    """
    Valida um número de CPF segundo o algoritmo canônico dos dígitos verificadores (módulo 11).
    Retorna True se válido, False caso contrário.
    """
    if not cpf:
        return False
    
    clean = re.sub(r'\D', '', str(cpf))
    if len(clean) != 11:
        return False
    
    # Rejeita CPFs com todos os dígitos iguais (ex: 000.000.000-00, 111.111.111-11, etc.)
    if clean == clean[0] * 11:
        return False
    
    # Validação do 1º dígito verificador
    soma = sum(int(clean[i]) * (10 - i) for i in range(9))
    resto = (soma * 10) % 11
    dv1 = 0 if resto in (10, 11) else resto
    if dv1 != int(clean[9]):
        return False
    
    # Validação do 2º dígito verificador
    soma = sum(int(clean[i]) * (11 - i) for i in range(10))
    resto = (soma * 10) % 11
    dv2 = 0 if resto in (10, 11) else resto
    if dv2 != int(clean[10]):
        return False
    
    return True


def validar_cnpj(cnpj: str) -> bool:
    """
    Valida um número de CNPJ (suporta formato tradicional numérico e alfanumérico IN RFB 2.229/2025).
    Retorna True se válido, False caso contrário.
    """
    if not cnpj:
        return False
    
    clean = re.sub(r'[^a-zA-Z0-9]', '', str(cnpj)).upper()
    if len(clean) != 14:
        return False
    
    # Rejeita sequências com todos os caracteres iguais
    if clean == clean[0] * 14:
        return False
    
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    
    try:
        # 1º dígito verificador
        soma1 = sum((ord(clean[i]) - 48) * pesos1[i] for i in range(12))
        resto1 = soma1 % 11
        dv1 = 0 if resto1 < 2 else 11 - resto1
        if dv1 != int(clean[12]):
            return False
        
        # 2º dígito verificador
        soma2 = sum((ord(clean[i]) - 48) * pesos2[i] for i in range(13))
        resto2 = soma2 % 11
        dv2 = 0 if resto2 < 2 else 11 - resto2
        if dv2 != int(clean[13]):
            return False
    except (ValueError, TypeError):
        return False
    
    return True


def validar_cpf_cnpj(documento: str) -> bool:
    """
    Valida documento identificando automaticamente se é CPF (11 dígitos) ou CNPJ (14 caracteres).
    """
    if not documento:
        return False
    
    clean = re.sub(r'[^a-zA-Z0-9]', '', str(documento))
    if len(clean) == 11 and clean.isdigit():
        return validar_cpf(clean)
    elif len(clean) == 14:
        return validar_cnpj(clean)
    
    return False
