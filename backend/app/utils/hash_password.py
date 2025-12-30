import getpass
import sys
from passlib.context import CryptContext

# IMPORTANTE: Esta é a MESMA configuração de 'pwd_context'
# que está em 'app/core/service/security.py'.
# É crucial que sejam idênticas.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """Gera o hash de uma senha."""
    return pwd_context.hash(password)

def main():
    print("--- Gerador de Hash de Senha (bcrypt) ---")
    print("Este script gera um hash de senha compatível com o backend.")
    
    try:
        # --- ALTERAÇÃO ---
        # Trocado de getpass.getpass para input() para mostrar a senha
        password = input("Digite a senha para gerar o hash: ")
        
        if not password:
            print("\n[ERRO] A senha não pode estar vazia.", file=sys.stderr)
            sys.exit(1)
            

        print("\nGerando hash...")
        hashed_password = get_password_hash(password)

        print("\n[SUCESSO!]")
        print("Hash gerado (pronto para copiar para o seu arquivo SQL):")
        print(f"\n{hashed_password}\n")

    except KeyboardInterrupt:
        print("\nOperação cancelada pelo usuário.")
        sys.exit(130)
    except Exception as e:
        print(f"\nOcorreu um erro inesperado: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

