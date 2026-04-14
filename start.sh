#!/bin/bash
# ─── DocFinance — Script de inicialização ────────────────────────────────
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$SCRIPT_DIR/backend"

echo "🚀 Iniciando DocFinance..."

# Verificar Python
python3 --version || { echo "❌ Python3 não encontrado"; exit 1; }

# Criar e ativar virtualenv
if [ ! -d "$BACKEND/venv" ]; then
  echo "📦 Criando ambiente virtual..."
  python3 -m venv "$BACKEND/venv"
fi
source "$BACKEND/venv/bin/activate"

# Instalar dependências
echo "📦 Instalando dependências..."
pip install -r "$BACKEND/requirements.txt" -q

# Criar .env se não existir
if [ ! -f "$BACKEND/.env" ]; then
  echo "⚙️  Criando .env padrão..."
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  # Gerar SECRET_KEY aleatória
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i "s/TROQUE_ESTA_CHAVE_POR_UMA_SEGURA_256bits/$SECRET/" "$BACKEND/.env"
  echo "⚠️  Edite $BACKEND/.env com suas credenciais Google (opcional)"
fi

# Criar diretórios necessários
mkdir -p "$BACKEND/uploads" "$SCRIPT_DIR/logs"

# Iniciar servidor
echo ""
echo "✅ DocFinance iniciado!"
echo "🌐 Acesse: http://localhost:8000"
echo "📖 API Docs: http://localhost:8000/docs"
echo ""
cd "$BACKEND"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
