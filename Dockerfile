FROM python:3.11-slim

# Instalar Tesseract + Poppler + idioma português
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-por poppler-utils libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependências Python
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY backend/ ./backend/
COPY frontend/ ./frontend/

WORKDIR /app/backend

# Diretórios
RUN mkdir -p uploads logs

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
