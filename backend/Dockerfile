# Use uma imagem base oficial do Python
FROM python:3.11-slim

# Define o diretório de trabalho no container
WORKDIR /app

# Impede o Python de gerar arquivos .pyc
ENV PYTHONDONTWRITEBYTECODE 1
# Garante que a saída do Python seja exibida imediatamente
ENV PYTHONUNBUFFERED 1

# Copia o arquivo de dependências e instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código da aplicação para o diretório de trabalho
COPY . .