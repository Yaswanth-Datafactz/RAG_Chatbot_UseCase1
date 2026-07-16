"""Verifies the constraints/cascades in the initial migration actually hold
against a live Postgres instance -- not just that the DDL compiled.
"""

import hashlib
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import Chunk, Citation, Conversation, Document, IngestionRun, Message


def _make_document(session, suffix="a"):
    doc = Document(
        source_filename=f"policy-{suffix}.pdf",
        title=f"Policy {suffix}",
        doc_type="pdf",
        sha256=hashlib.sha256(suffix.encode()).hexdigest(),
        byte_size=100,
    )
    session.add(doc)
    session.flush()
    return doc


def test_only_one_current_ingestion_run_allowed(db_session):
    run_a = IngestionRun(status="succeeded", embedding_model="text-embedding-3-small", is_current=True)
    db_session.add(run_a)
    db_session.flush()

    run_b = IngestionRun(status="succeeded", embedding_model="text-embedding-3-small", is_current=True)
    db_session.add(run_b)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_conversation_cascades_to_messages(db_session):
    convo = Conversation(title="Test convo")
    db_session.add(convo)
    db_session.flush()

    msg = Message(conversation_id=convo.id, role="user", content="hello")
    db_session.add(msg)
    db_session.flush()
    msg_id = msg.id

    db_session.delete(convo)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(Message, msg_id) is None


def test_deleting_chunk_nulls_citation_instead_of_deleting_it(db_session):
    doc = _make_document(db_session, suffix="1")
    run = IngestionRun(status="succeeded", embedding_model="text-embedding-3-small")
    db_session.add(run)
    db_session.flush()

    chunk = Chunk(
        document_id=doc.id,
        ingestion_run_id=run.id,
        chunk_index=0,
        content="PTO accrues at 1.5 days per month.",
        token_count=10,
        azure_doc_key=f"chunk-{uuid.uuid4()}",
    )
    db_session.add(chunk)
    db_session.flush()

    convo = Conversation(title="Q&A")
    db_session.add(convo)
    db_session.flush()
    msg = Message(conversation_id=convo.id, role="assistant", content="You accrue 1.5 days/month.")
    db_session.add(msg)
    db_session.flush()

    citation = Citation(
        message_id=msg.id,
        chunk_id=chunk.id,
        document_id=doc.id,
        rank=1,
        snippet="PTO accrues at 1.5 days per month.",
    )
    db_session.add(citation)
    db_session.flush()
    citation_id = citation.id

    db_session.delete(chunk)
    db_session.flush()

    surviving = db_session.get(Citation, citation_id)
    assert surviving is not None
    assert surviving.chunk_id is None
    assert surviving.document_id == doc.id


def test_documents_sha256_must_be_unique(db_session):
    _make_document(db_session, suffix="x")

    dup = Document(
        source_filename="dup.pdf",
        title="Dup",
        doc_type="pdf",
        sha256=hashlib.sha256(b"x").hexdigest(),
        byte_size=50,
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.flush()
