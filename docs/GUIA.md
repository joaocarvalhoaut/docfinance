# 🚀 DocFinance — Guia Completo de Instalação e Deploy

## Visão Geral da Arquitetura

```
docfinance/
├── backend/
│   ├── main.py          # API FastAPI
│   ├── models.py        # Modelos Pydantic
│   ├── auth.py          # JWT + bcrypt
│   ├── ocr_processor.py # OCR + extração de campos
│   ├── sheets_handler.py # Excel + Google Sheets
│   ├── storage.py       # Armazenamento (memória / banco)
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    └── index.html       # SPA completo (HTML + CSS + JS)
```

---

## 🖥️ INSTALAÇÃO LOCAL (MVP)

### Pré-requisitos

- Python 3.10+
- Tesseract OCR
- Poppler (para PDF → imagem)

### 1. Instalar Tesseract

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-por poppler-utils
```

**macOS:**
```bash
brew install tesseract tesseract-lang poppler
```

**Windows:**
- Baixe o instalador em: https://github.com/UB-Mannheim/tesseract/wiki
- Adicione ao PATH
- Baixe `por.traineddata` de https://github.com/tesseract-ocr/tessdata

### 2. Configurar o ambiente

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env com suas credenciais
```

**.env mínimo para rodar:**
```env
SECRET_KEY=minha-chave-secreta-32-chars-aqui
```

### 4. Iniciar o backend

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Abrir o frontend

Abra `frontend/index.html` no navegador.
Se preferir servir via HTTP:
```bash
cd frontend
python -m http.server 3000
# Acesse: http://localhost:3000
```

### 6. Testar

Acesse http://localhost:8000/docs para ver a documentação da API.

---

## 🔗 CONFIGURAR GOOGLE SHEETS (Opcional)

### 1. Criar projeto no Google Cloud

1. Acesse https://console.cloud.google.com
2. Crie um novo projeto: **DocFinance**
3. Ative as APIs:
   - Google Sheets API
   - Google Drive API

### 2. Criar credenciais OAuth 2.0

1. Menu: **APIs e serviços** → **Credenciais**
2. Clique em **Criar credenciais** → **ID do cliente OAuth**
3. Tipo: **Aplicativo da Web**
4. URIs de redirecionamento autorizados:
   ```
   http://localhost:8000/google/callback
   https://seudominio.com/google/callback
   ```
5. Copie o **Client ID** e **Client Secret**

### 3. Adicionar ao .env

```env
GOOGLE_CLIENT_ID=123456789-abc.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxx
GOOGLE_REDIRECT_URI=http://localhost:8000/google/callback
```

### 4. Fluxo de uso

1. No frontend: Configurações → Integrações → Conectar Google Sheets
2. Autorize o acesso
3. Ao fazer upload, selecione "Google Sheets"
4. Escolha a planilha e aba

---

## ☁️ DEPLOY EM PRODUÇÃO

### Opção A: Railway (recomendado para MVP)

```bash
# 1. Instale Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Deploy
cd backend
railway init
railway up

# 4. Configurar variáveis no painel Railway
# Settings → Variables → adicionar SECRET_KEY, GOOGLE_*, etc.
```

### Opção B: Render

1. Conecte seu repositório no https://render.com
2. Crie um **Web Service**:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Adicione variáveis de ambiente no painel

### Opção C: VPS (Ubuntu)

```bash
# 1. Instalar dependências do sistema
sudo apt update
sudo apt install python3.11 python3-pip nginx tesseract-ocr tesseract-ocr-por poppler-utils

# 2. Configurar aplicação
git clone https://github.com/seu-usuario/docfinance.git
cd docfinance/backend
pip install -r requirements.txt
cp .env.example .env
# Edite .env com valores de produção

# 3. Configurar Gunicorn
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# 4. Systemd service
sudo nano /etc/systemd/system/docfinance.service
```

**/etc/systemd/system/docfinance.service:**
```ini
[Unit]
Description=DocFinance API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/docfinance/backend
Environment=PATH=/home/ubuntu/docfinance/venv/bin
ExecStart=/home/ubuntu/docfinance/venv/bin/gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable docfinance
sudo systemctl start docfinance
```

**Nginx config:**
```nginx
server {
    listen 80;
    server_name seudominio.com;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        root /var/www/docfinance;
        try_files $uri $uri/ /index.html;
    }
}
```

---

## 🗄️ BANCO DE DADOS EM PRODUÇÃO

O MVP usa memória (dados perdidos ao reiniciar). Para produção:

### PostgreSQL (recomendado)

```bash
pip install sqlalchemy psycopg2-binary alembic
```

Adicione ao .env:
```env
DATABASE_URL=postgresql://user:password@localhost/docfinance
```

Substitua `job_store` e `user_store` por SQLAlchemy ORM.

---

## 🔒 CHECKLIST DE SEGURANÇA

- [ ] SECRET_KEY com no mínimo 32 caracteres aleatórios
- [ ] HTTPS habilitado (Certbot/Let's Encrypt)
- [ ] .env no .gitignore
- [ ] Nenhuma credencial no código
- [ ] Rate limiting configurado (adicione `slowapi` ao projeto)
- [ ] CORS restrito ao domínio do frontend
- [ ] Uploads com limite de tamanho (10MB por arquivo)

### Rate Limiting (adicionar ao main.py)

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/upload")
@limiter.limit("10/minute")
async def upload_documents(request: Request, ...):
    ...
```

---

## 🧪 TESTANDO COM DOCUMENTOS REAIS

### Gerar arquivos de teste

```python
# test_demo.py
import requests

# 1. Registrar usuário
res = requests.post('http://localhost:8000/auth/register', json={
    'name': 'Teste', 'email': 'teste@teste.com', 'password': 'senha123'
})
token = res.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

# 2. Upload de arquivo
with open('boleto.jpg', 'rb') as f:
    res = requests.post(
        'http://localhost:8000/upload',
        headers=headers,
        files={'files': ('boleto.jpg', f, 'image/jpeg')},
        data={'spreadsheet_type': 'excel', 'sheet_name': 'Teste'}
    )
job_id = res.json()['job_id']
print(f'Job ID: {job_id}')

# 3. Verificar resultado
import time
time.sleep(5)
res = requests.get(f'http://localhost:8000/jobs/{job_id}', headers=headers)
print(res.json())
```

---

## 🔮 EVOLUÇÃO FUTURA

### Fase 2: Qualidade
- [ ] Integrar Google Cloud Vision API (maior precisão)
- [ ] Pré-processamento de imagem (deskew, contrast, denoise)
- [ ] Score de confiança por campo (não só documento)

### Fase 3: Banco de Dados
- [ ] PostgreSQL com SQLAlchemy
- [ ] Redis para cache de sessões e jobs
- [ ] Celery para filas de processamento assíncrono

### Fase 4: Features
- [ ] Aprendizado com correções do usuário
- [ ] Webhook para notificação de conclusão
- [ ] API para integrar com ERPs
- [ ] Export para Google Sheets automático ao concluir
- [ ] Dashboard com gráficos temporais

### Fase 5: Escala
- [ ] Docker + Kubernetes
- [ ] Armazenamento de arquivos em S3
- [ ] CDN para frontend
- [ ] Multi-tenancy completo

---

## 📞 SUPORTE

- Documentação da API: http://localhost:8000/docs
- Health check: http://localhost:8000/health
- Logs: `journalctl -u docfinance -f` (produção)

---

*DocFinance v1.0 — Sistema de Extração Inteligente de Documentos Financeiros*
