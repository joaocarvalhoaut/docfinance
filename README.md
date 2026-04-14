# 📄 DocFinance OCR

Sistema web completo para **extração automática de dados de documentos financeiros** via OCR (Tesseract), com exportação para **Excel** e **Google Sheets**.

---

## 🎯 O que faz

| Documento | Campos Extraídos |
|-----------|-----------------|
| **Cheque** | Beneficiário, valor, data, banco, número, cidade |
| **Nota Fiscal** | Número, CNPJ, empresa, data, valor, impostos |
| **Comprovante PIX/TED** | Tipo, valor, data/hora, pagador, recebedor, autenticação |
| **Boleto** | Linha digitável, beneficiário, pagador, valor, vencimento |

---

## 🚀 Instalação rápida

### Pré-requisitos
- Python 3.10+
- Tesseract OCR com idioma português

```bash
# Ubuntu/Debian
sudo apt install tesseract-ocr tesseract-ocr-por poppler-utils

# macOS
brew install tesseract tesseract-lang poppler

# Windows
# Baixe: https://github.com/UB-Mannheim/tesseract/wiki
# Adicione ao PATH
```

### Iniciar

```bash
git clone <seu-repositório> docfinance
cd docfinance

# Instala tudo e inicia
bash install.sh   # instala dependências do sistema
bash start.sh     # cria venv, instala pip e sobe o servidor
```

Acesse: **http://localhost:8000**
Documentação da API: **http://localhost:8000/docs**

---

## 🐳 Docker (recomendado para produção)

```bash
# Copiar e editar variáveis
cp backend/.env.example .env
nano .env

# Subir
docker-compose up -d

# Ver logs
docker-compose logs -f
```

---

## ⚙️ Configuração (.env)

```env
# Segurança (obrigatório mudar em produção)
SECRET_KEY=gere-com-python-secrets-token-hex-32

# Google OAuth (opcional — só para Google Sheets)
GOOGLE_CLIENT_ID=seu-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=seu-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# Limites
MAX_FILE_SIZE_MB=20
```

### Gerar SECRET_KEY segura
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 🔑 Configurar Google OAuth (para Google Sheets)

1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Crie um projeto → **APIs & Serviços** → **Credenciais**
3. Criar credencial OAuth 2.0 (Aplicativo Web)
4. URI de redirecionamento: `http://localhost:8000/auth/google/callback`
5. Ative as APIs: **Google Sheets API** e **Google Drive API**
6. Cole `client_id` e `client_secret` no `.env`

---

## 🏗️ Arquitetura

```
docfinance/
├── backend/
│   ├── main.py              # FastAPI app
│   ├── config.py            # Configurações (.env)
│   ├── models/
│   │   └── database.py      # SQLAlchemy: User, ProcessingJob
│   ├── routers/
│   │   ├── auth.py          # /auth/register, /auth/token, /auth/google
│   │   └── documents.py     # /documents/upload, /status, /history, /export-excel
│   ├── services/
│   │   ├── ocr_service.py   # Tesseract + extratores por tipo
│   │   ├── sheets_service.py # Google Sheets + Excel (openpyxl)
│   │   └── auth_service.py  # JWT + bcrypt
│   └── utils/
│       └── validators.py    # CPF, CNPJ, datas, valores
├── frontend/
│   └── index.html           # SPA completa (HTML/CSS/JS vanilla)
├── Dockerfile
├── docker-compose.yml
├── start.sh                 # Dev: venv + uvicorn --reload
└── install.sh               # Instala dependências do sistema
```

---

## 🔌 API REST

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/auth/register` | Criar conta |
| `POST` | `/auth/token` | Login (JWT) |
| `GET` | `/auth/google` | OAuth Google |
| `POST` | `/documents/upload` | Upload + processamento |
| `GET` | `/documents/status/{id}` | Status do job |
| `GET` | `/documents/history` | Histórico |
| `POST` | `/documents/export-excel/{id}` | Exportar Excel |
| `GET` | `/documents/google-sheets/list` | Listar Sheets |
| `GET` | `/health` | Health check |

---

## 🔒 Segurança implementada

- ✅ Senhas com **bcrypt**
- ✅ Sessões com **JWT (HS256)**
- ✅ **Rate limiting** (slowapi)
- ✅ **CORS** configurável
- ✅ Validação de tamanho e tipo de arquivo
- ✅ Arquivos temporários deletados após processamento
- ✅ Credenciais via `.env` (nunca no código)
- ✅ Dados separados por usuário

---

## ☁️ Deploy em produção

### Railway / Render / Fly.io
```bash
# Definir variáveis de ambiente no painel da plataforma
# Dockerfile está pronto para uso direto
```

### VPS com Nginx
```nginx
server {
    listen 80;
    server_name seudominio.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 25M;
    }
}
```

```bash
# HTTPS com Certbot
certbot --nginx -d seudominio.com
```

---

## 🧪 Testar a API manualmente

```bash
# 1. Criar conta
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Teste","email":"teste@email.com","password":"123456"}'

# 2. Login
curl -X POST http://localhost:8000/auth/token \
  -F "username=teste@email.com" -F "password=123456"

# 3. Upload de documento (use o token recebido)
curl -X POST http://localhost:8000/documents/upload \
  -H "Authorization: Bearer SEU_TOKEN" \
  -F "file=@nota_fiscal.pdf" \
  -F "sheet_type=none"

# 4. Verificar status
curl http://localhost:8000/documents/status/JOB_ID \
  -H "Authorization: Bearer SEU_TOKEN"
```

---

## ⚠️ Limitações do OCR

- OCR funciona bem com documentos digitais claros
- Fotos tortas ou de baixa qualidade reduzem precisão (marcado como `REVISAR`)
- Tesseract é gratuito; para maior precisão, integre Google Vision API (basta substituir `extract_text_from_file` em `ocr_service.py`)

---

## 🔮 Próximos passos (pós-MVP)

- [ ] Integração Google Vision API (OCR mais preciso)
- [ ] Aprendizado com correções do usuário
- [ ] Processamento em fila (Celery + Redis) para volumes maiores
- [ ] Dashboard de analytics por tipo de documento
- [ ] Webhook para notificação ao concluir

