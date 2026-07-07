# Use uma imagem base oficial do Python
FROM python:3.11-slim

# Define o diretório de trabalho no container
WORKDIR /app

# Impede o Python de gerar arquivos .pyc
ENV PYTHONDONTWRITEBYTECODE 1
# Garante que a saída do Python seja exibida imediatamente
ENV PYTHONUNBUFFERED 1

# --- INSTALAÇÃO DE DEPENDÊNCIAS DO SISTEMA (PyNFe / XMLSec) ---
# Atualiza o apt e instala as dependências de compilação
# Removemos o 'sudo' pois no docker já somos root
# Adicionei 'pkg-config' que ajuda a encontrar as libs XML durante a compilação
RUN apt-get update && apt-get install -y --no-install-recommends \
    xmlsec1 \
    libxmlsec1-dev \
    libxml2-dev \
    libxslt1-dev \
    libssl-dev \
    build-essential \
    python3-dev \
    pkg-config \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# --- FIM DAS DEPENDÊNCIAS DO SISTEMA ---

# Copia o arquivo de dependências e instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código da aplicação para o diretório de trabalho
COPY . .