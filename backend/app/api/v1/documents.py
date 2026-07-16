"""GET /documents (with current-run chunk counts) and
GET /documents/{id}/chunks/{chunk_index} (citation -> source passage)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.security import require_api_key
from app.db.models import Chunk, Document, IngestionRun
from app.db.session import get_db
from app.schemas.document import ChunkOut, DocumentOut

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(require_api_key)],
    responses={401: {"description": "Missing or invalid API key"}},
)


def _current_run_id(db: Session) -> uuid.UUID | None:
    run = db.execute(select(IngestionRun).where(IngestionRun.is_current.is_(True))).scalar_one_or_none()
    return run.id if run is not None else None


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Annotated[Session, Depends(get_db)]) -> list[DocumentOut]:
    current_run_id = _current_run_id(db)
    documents = db.execute(select(Document).order_by(Document.title)).scalars().all()

    counts: dict[uuid.UUID, int] = {}
    if current_run_id is not None:
        rows = db.execute(
            select(Chunk.document_id, func.count(Chunk.id))
            .where(Chunk.ingestion_run_id == current_run_id)
            .group_by(Chunk.document_id)
        ).all()
        counts = dict(rows)

    return [
        DocumentOut(
            id=doc.id,
            source_filename=doc.source_filename,
            title=doc.title,
            doc_type=doc.doc_type,
            byte_size=doc.byte_size,
            created_at=doc.created_at,
            current_chunk_count=counts.get(doc.id, 0),
        )
        for doc in documents
    ]


@router.get(
    "/{document_id}/chunks/{chunk_index}",
    response_model=ChunkOut,
    responses={404: {"description": "Document not found, or no chunk at that index in the current index"}},
)
def get_document_chunk(
    document_id: uuid.UUID,
    chunk_index: int,
    db: Annotated[Session, Depends(get_db)],
) -> ChunkOut:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} not found")

    current_run_id = _current_run_id(db)
    chunk = None
    if current_run_id is not None:
        chunk = db.execute(
            select(Chunk).where(
                Chunk.document_id == document_id,
                Chunk.ingestion_run_id == current_run_id,
                Chunk.chunk_index == chunk_index,
            )
        ).scalar_one_or_none()

    if chunk is None:
        raise NotFoundError(f"Chunk {chunk_index} not found for document {document_id} in the current index")

    return ChunkOut(
        id=chunk.id,
        document_id=document.id,
        document_title=document.title,
        chunk_index=chunk.chunk_index,
        section_path=chunk.section_path,
        content=chunk.content,
        token_count=chunk.token_count,
        page_no=chunk.page_no,
    )
