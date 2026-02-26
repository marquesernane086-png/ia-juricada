"""Chunked upload routes — Upload de arquivos grandes em partes."""

import os
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload-large", tags=["upload-large"])

db: Optional[AsyncIOMotorDatabase] = None
UPLOAD_DIR = Path("/tmp") / "jurista_uploads"
# Use overlay disk (72GB) instead of /app (4.6GB)
QDRANT_DIR = Path("/tmp") / "qdrant_persistent"


def set_db(database):
    global db
    db = database


@router.post("/init")
async def init_upload(filename: str = Form(...), total_chunks: int = Form(...), total_size: int = Form(0)):
    """Inicializa um upload chunked."""
    upload_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    upload_dir = UPLOAD_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "upload_id": upload_id,
        "filename": filename,
        "total_chunks": total_chunks,
        "total_size": total_size,
        "received_chunks": 0,
        "status": "uploading",
    }

    import json
    with open(upload_dir / "meta.json", "w") as f:
        json.dump(meta, f)

    logger.info(f"Upload iniciado: {filename} ({total_chunks} partes, {total_size/(1024*1024):.0f}MB)")
    return {"upload_id": upload_id, "status": "ready"}


@router.post("/chunk")
async def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...)
):
    """Recebe uma parte do arquivo."""
    upload_dir = UPLOAD_DIR / upload_id
    if not upload_dir.exists():
        raise HTTPException(status_code=404, detail="Upload not found")

    # Save chunk
    chunk_path = upload_dir / f"chunk_{chunk_index:05d}"
    content = await chunk.read()
    with open(chunk_path, "wb") as f:
        f.write(content)

    # Update meta
    import json
    meta_path = upload_dir / "meta.json"
    with open(meta_path) as f:
        meta = json.load(f)

    meta["received_chunks"] += 1
    with open(meta_path, "w") as f:
        json.dump(meta, f)

    logger.info(f"Chunk {chunk_index+1}/{meta['total_chunks']} recebido ({len(content)/(1024*1024):.1f}MB)")

    return {
        "chunk_index": chunk_index,
        "received": meta["received_chunks"],
        "total": meta["total_chunks"],
    }


@router.post("/finalize")
async def finalize_upload(upload_id: str = Form(...), background_tasks: BackgroundTasks = None):
    """Monta o arquivo final e processa."""
    upload_dir = UPLOAD_DIR / upload_id
    if not upload_dir.exists():
        raise HTTPException(status_code=404, detail="Upload not found")

    import json
    with open(upload_dir / "meta.json") as f:
        meta = json.load(f)

    if meta["received_chunks"] < meta["total_chunks"]:
        raise HTTPException(status_code=400, detail=f"Missing chunks: {meta['received_chunks']}/{meta['total_chunks']}")

    # Reassemble file
    final_path = UPLOAD_DIR / meta["filename"]
    logger.info(f"Montando arquivo: {meta['filename']}...")

    with open(final_path, "wb") as outfile:
        for i in range(meta["total_chunks"]):
            chunk_path = upload_dir / f"chunk_{i:05d}"
            with open(chunk_path, "rb") as infile:
                shutil.copyfileobj(infile, outfile)

    file_size = final_path.stat().st_size
    logger.info(f"Arquivo montado: {file_size/(1024*1024):.0f}MB")

    # Clean chunks
    shutil.rmtree(upload_dir)

    # Process in background
    if background_tasks:
        background_tasks.add_task(_process_upload, str(final_path), meta["filename"])

    return {
        "status": "processing",
        "filename": meta["filename"],
        "size_mb": round(file_size / (1024 * 1024), 1),
        "message": "Arquivo recebido. Processando em background...",
    }


async def _process_upload(file_path: str, filename: str):
    """Processa o arquivo importado em background."""
    try:
        logger.info(f"Processando: {filename} ({Path(file_path).stat().st_size/(1024*1024):.0f}MB)")

        extract_dir = Path(file_path).parent / "extracted"
        extract_dir.mkdir(exist_ok=True)

        if filename.endswith(".zip"):
            # Use command line unzip (low memory)
            import subprocess
            result = subprocess.run(
                ["unzip", "-o", file_path, "-d", str(extract_dir)],
                capture_output=True, text=True, timeout=600
            )
            if result.returncode != 0:
                logger.error(f"unzip failed: {result.stderr[:500]}")
                return
            logger.info(f"ZIP extraido com unzip")

        elif filename.endswith(".7z"):
            try:
                import py7zr
                with py7zr.SevenZipFile(file_path, mode='r') as z:
                    z.extractall(path=str(extract_dir))
                logger.info(f"7z extraido")
            except ImportError:
                logger.error("py7zr nao instalado")
                return
        else:
            logger.error(f"Formato nao suportado: {filename}")
            return

        # Remove ZIP to free space
        os.remove(file_path)
        logger.info("ZIP removido para liberar espaco")

        # Find qdrant collection data
        qdrant_src = None
        for item in extract_dir.rglob("storage.sqlite"):
            qdrant_src = item.parent.parent  # collection/ parent
            break

        if not qdrant_src:
            for item in extract_dir.rglob("collection"):
                if item.is_dir():
                    qdrant_src = item.parent
                    break

        if not qdrant_src:
            qdrant_src = extract_dir
            
        logger.info(f"Qdrant source: {qdrant_src}")

        # Setup qdrant destination
        QDRANT_DIR.mkdir(parents=True, exist_ok=True)

        # Move (not copy) to save space
        for item in qdrant_src.iterdir():
            dest = QDRANT_DIR / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(str(dest))
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))
            logger.info(f"Movido: {item.name}")

        # Also copy meta.json if exists
        meta_src = qdrant_src / "meta.json"
        if meta_src.exists():
            shutil.move(str(meta_src), str(QDRANT_DIR / "meta.json"))

        logger.info(f"Qdrant data em: {QDRANT_DIR}")

        # Cleanup
        shutil.rmtree(str(extract_dir), ignore_errors=True)

        # Reset vector service to load new data
        from services import vector_service
        vector_service.reset_index()

        logger.info("IMPORT CONCLUIDO!")

    except Exception as e:
        logger.error(f"Erro processando upload: {e}")
        import traceback
        logger.error(traceback.format_exc())
