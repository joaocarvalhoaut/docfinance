"""Endpoints de processamento de documentos."""
import os
import uuid
import asyncio
import logging
import aiofiles
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, BackgroundTasks, Form
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import settings
from models.database import User, ProcessingJob, get_db
from services.auth_service import get_current_user
from services.ocr_service import process_document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documentos"])

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_SIZE = settings.MAX_FILE_SIZE_MB * 1024 * 1024


async def _do_process(job_id: str, file_path: str, spreadsheet_config: dict):
    """Processamento em background."""
    from sqlalchemy import update
    from models.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            # Atualizar status para processando
            await db.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job_id)
                .values(status="processando", updated_at=datetime.utcnow())
            )
            await db.commit()

            # OCR + extração
            result = process_document(file_path)

            # Integração com planilha
            sheet_result = None
            if spreadsheet_config.get("type") == "google_sheets":
                from services.sheets_service import write_to_google_sheets
                try:
                    success = write_to_google_sheets(
                        google_token_json=spreadsheet_config["token"],
                        spreadsheet_id=spreadsheet_config["sheet_id"],
                        data=result,
                        doc_type=result["doc_type"],
                        sheet_name=spreadsheet_config.get("sheet_name", "Planilha1")
                    )
                    sheet_result = "ok" if success else "erro"
                except Exception as e:
                    logger.error(f"Erro Google Sheets: {e}")
                    sheet_result = f"erro: {str(e)[:100]}"

            result["sheet_result"] = sheet_result

            # Salvar resultado
            await db.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job_id)
                .values(
                    status="concluido",
                    doc_type=result["doc_type"],
                    extracted_data=result,
                    confidence=result.get("confidence", 0),
                    updated_at=datetime.utcnow()
                )
            )
            await db.commit()

        except Exception as e:
            logger.error(f"Erro no job {job_id}: {e}", exc_info=True)
            await db.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job_id)
                .values(status="erro", error_msg=str(e)[:500], updated_at=datetime.utcnow())
            )
            await db.commit()
        finally:
            # Remover arquivo temporário
            try:
                os.remove(file_path)
            except Exception:
                pass


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    sheet_type: str = Form(default="none"),          # none | excel | google_sheets
    google_sheet_id: Optional[str] = Form(default=None),
    google_sheet_name: Optional[str] = Form(default="Planilha1"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload e processamento assíncrono de documento financeiro."""
    # Validar extensão
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Tipo não suportado. Use: {', '.join(ALLOWED_EXTENSIONS)}")

    # Validar tamanho
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(413, f"Arquivo muito grande (máx {settings.MAX_FILE_SIZE_MB}MB)")

    # Salvar arquivo temporário
    job_id = str(uuid.uuid4())
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(exist_ok=True)
    file_path = str(upload_dir / f"{job_id}{suffix}")

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # Criar job no banco
    job = ProcessingJob(
        id=job_id,
        user_id=current_user.id,
        filename=file.filename or "documento",
        status="pendente"
    )
    db.add(job)
    await db.commit()

    # Configurar integração planilha
    spreadsheet_config = {"type": sheet_type}
    if sheet_type == "google_sheets":
        if not current_user.google_token:
            raise HTTPException(400, "Conecte sua conta Google antes de usar o Google Sheets")
        spreadsheet_config["token"] = current_user.google_token
        spreadsheet_config["sheet_id"] = google_sheet_id
        spreadsheet_config["sheet_name"] = google_sheet_name or "Planilha1"

    # Iniciar processamento em background
    background_tasks.add_task(_do_process, job_id, file_path, spreadsheet_config)

    return {"job_id": job_id, "status": "pendente", "message": "Processamento iniciado"}


@router.get("/status/{job_id}")
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retorna status e dados extraídos de um job."""
    result = await db.execute(
        select(ProcessingJob).where(
            ProcessingJob.id == job_id,
            ProcessingJob.user_id == current_user.id
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job não encontrado")

    return {
        "job_id": job.id,
        "status": job.status,
        "filename": job.filename,
        "doc_type": job.doc_type,
        "confidence": job.confidence,
        "extracted_data": job.extracted_data,
        "error": job.error_msg,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


@router.get("/history")
async def get_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
):
    """Histórico de processamentos do usuário."""
    result = await db.execute(
        select(ProcessingJob)
        .where(ProcessingJob.user_id == current_user.id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(limit)
    )
    jobs = result.scalars().all()
    return [
        {
            "job_id": j.id,
            "status": j.status,
            "filename": j.filename,
            "doc_type": j.doc_type,
            "confidence": j.confidence,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]



@router.post("/export-excel/{job_id}")
async def export_to_excel(
    job_id: str,
    file: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exporta dados de um job para Excel."""
    from services.sheets_service import write_to_excel
    import io

    result = await db.execute(
        select(ProcessingJob).where(
            ProcessingJob.id == job_id,
            ProcessingJob.user_id == current_user.id
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job nao encontrado")

    # Aceitar qualquer status — tentar exportar o que tiver
    extracted = job.extracted_data or {}

    # Ler planilha enviada (se houver)
    file_bytes = b""
    if file and file.filename:
        file_bytes = await file.read()

    # Gerar Excel com os dados
    updated = write_to_excel(file_bytes, extracted, job.doc_type or "desconhecido")

    filename = f"docfinance_{(job.filename or 'resultado').rsplit('.', 1)[0]}.xlsx"

    return StreamingResponse(
        io.BytesIO(updated),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.get("/google-sheets/list")
async def list_google_sheets(
    current_user: User = Depends(get_current_user),
):
    """Lista planilhas do Google Drive do usuário."""
    if not current_user.google_token:
        raise HTTPException(400, "Conta Google não conectada")

    from services.sheets_service import list_spreadsheets
    sheets = list_spreadsheets(current_user.google_token)
    return {"sheets": sheets}


@router.post("/export-sheets/{job_id}")
async def export_to_sheets(
    job_id: str,
    spreadsheet_id: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services.sheets_service import write_to_google_sheets, create_spreadsheet
    import datetime
    print(f"=== export_to_sheets chamado: {datetime.datetime.now()} job_id={job_id} sheet={spreadsheet_id} ===")
    result = await db.execute(
        select(ProcessingJob).where(
            ProcessingJob.id == job_id,
            ProcessingJob.user_id == current_user.id
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job nao encontrado")

    extracted = job.extracted_data or {}

    # Criar planilha nova se nao foi informada
    if not spreadsheet_id:
        spreadsheet_id = create_spreadsheet(f"DocFinance - {job.filename or job_id}")

    ok = write_to_google_sheets(spreadsheet_id, extracted, job.doc_type or "desconhecido")
    if not ok:
        raise HTTPException(500, "Erro ao escrever no Google Sheets")

    return {
        "ok": True,
        "spreadsheet_id": spreadsheet_id,
        "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    }


@router.get("/sheets/list")
async def list_sheets(current_user: User = Depends(get_current_user)):
    from services.sheets_service import list_spreadsheets
    return list_spreadsheets()
