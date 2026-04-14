"""Models Pydantic para DocFinance."""

from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, validator
import re


class JobStatus(str, Enum):
    PROCESSING = "processando"
    COMPLETED = "concluído"
    ERROR = "erro"


class DocumentType(str, Enum):
    CHEQUE = "cheque"
    NOTA_FISCAL = "nota_fiscal"
    COMPROVANTE = "comprovante"
    BOLETO = "boleto"
    DESCONHECIDO = "desconhecido"


class ExtractedData(BaseModel):
    """Dados extraídos de um documento."""
    tipo_documento: DocumentType
    confianca: float  # 0.0 a 1.0
    campos: Dict[str, Any]
    campos_revisao: List[str] = []  # campos que precisam revisão
    raw_text: Optional[str] = None


class ProcessingJob(BaseModel):
    job_id: str
    user_id: str
    files: List[str]
    spreadsheet_type: str
    google_sheet_id: Optional[str] = None
    sheet_name: str = "Extrações"
    status: JobStatus = JobStatus.PROCESSING
    results: Optional[List[Dict]] = None
    output_path: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

    @validator("password")
    def password_strength(cls, v):
        if len(v) < 6:
            raise ValueError("Senha deve ter pelo menos 6 caracteres")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: str
