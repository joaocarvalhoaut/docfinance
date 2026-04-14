#!/bin/bash
# ─── DocFinance — Instalação completa ────────────────────────────────────
set -e
echo "🔧 Instalando dependências do sistema..."

# Detectar OS
if command -v apt-get &>/dev/null; then
  sudo apt-get update -q
  sudo apt-get install -y tesseract-ocr tesseract-ocr-por poppler-utils python3-venv python3-pip -q
elif command -v brew &>/dev/null; then
  brew install tesseract tesseract-lang poppler
elif command -v yum &>/dev/null; then
  sudo yum install -y tesseract poppler-utils python3
fi

echo "✅ Dependências do sistema instaladas!"
echo ""
echo "Agora execute: bash start.sh"
