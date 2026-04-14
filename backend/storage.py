"""
Armazenamento em memória para MVP.
Em produção: substituir por PostgreSQL + Redis.
"""

# Simples dicionários em memória para MVP
# Produção: usar SQLAlchemy + PostgreSQL para persistência
job_store = {}   # job_id -> ProcessingJob dict
user_store = {}  # email -> user dict
google_tokens = {}  # user_id -> google credentials
