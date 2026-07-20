"""Route-level tests for /api/v1/conversations: auth enforcement, status
codes, and the nested messages/citations serialization on the detail
route. These call the real app via TestClient against the real local
Postgres (like test_ingestion.py, this commits for real), so fixtures are
cleaned up explicitly rather than relying on a rollback fixture.
"""

import uuid

from app.core.config import get_settings
from app.db.models import Citation, Conversation, Message
from app.db.session import SessionLocal

API_KEY_HEADER = {"X-API-Key": get_settings().api_key}


def _cleanup_conversation(conversation_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        conversation = db.get(Conversation, conversation_id)
        if conversation is not None:
            db.delete(conversation)  # cascades messages -> citations
            db.commit()
    finally:
        db.close()


def test_create_conversation_requires_api_key(client):
    response = client.post("/api/v1/conversations", json={"title": "no key"})

    assert response.status_code == 401
    assert response.json()["error"]["type"] == "unauthorized"


def test_list_conversations_requires_api_key(client):
    response = client.get("/api/v1/conversations")

    assert response.status_code == 401


def test_create_list_and_get_conversation(client):
    create_response = client.post("/api/v1/conversations", json={"title": "PTO questions"}, headers=API_KEY_HEADER)
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["title"] == "PTO questions"
    conversation_id = uuid.UUID(body["id"])

    try:
        list_response = client.get("/api/v1/conversations", headers=API_KEY_HEADER)
        assert list_response.status_code == 200
        assert any(c["id"] == body["id"] for c in list_response.json())

        detail_response = client.get(f"/api/v1/conversations/{conversation_id}", headers=API_KEY_HEADER)
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["id"] == body["id"]
        assert detail["messages"] == []

        # Insert a message + two citations (out of rank order) directly,
        # then confirm the detail route returns citations ordered by rank.
        db = SessionLocal()
        try:
            message = Message(conversation_id=conversation_id, role="assistant", content="Full-time PTO is 15 days/year.")
            db.add(message)
            db.flush()
            db.add_all(
                [
                    Citation(
                        message_id=message.id,
                        document_id=uuid.uuid4(),
                        rank=2,
                        section_path="B",
                        snippet="second",
                    ),
                    Citation(
                        message_id=message.id,
                        document_id=uuid.uuid4(),
                        rank=1,
                        section_path="A",
                        snippet="first",
                    ),
                ]
            )
            db.commit()
        finally:
            db.close()

        detail_response = client.get(f"/api/v1/conversations/{conversation_id}", headers=API_KEY_HEADER)
        detail = detail_response.json()
        assert len(detail["messages"]) == 1
        citations = detail["messages"][0]["citations"]
        assert [c["rank"] for c in citations] == [1, 2]
        assert [c["snippet"] for c in citations] == ["first", "second"]
    finally:
        _cleanup_conversation(conversation_id)


def test_get_conversation_404_for_unknown_id(client):
    response = client.get(f"/api/v1/conversations/{uuid.uuid4()}", headers=API_KEY_HEADER)

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "not_found"


def test_delete_conversation_requires_api_key(client):
    response = client.delete(f"/api/v1/conversations/{uuid.uuid4()}")

    assert response.status_code == 401


def test_delete_conversation_404_for_unknown_id(client):
    response = client.delete(f"/api/v1/conversations/{uuid.uuid4()}", headers=API_KEY_HEADER)

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "not_found"


def test_delete_conversation_removes_it_and_cascades_messages_and_citations(client):
    create_response = client.post("/api/v1/conversations", json={"title": "to delete"}, headers=API_KEY_HEADER)
    conversation_id = uuid.UUID(create_response.json()["id"])

    db = SessionLocal()
    try:
        message = Message(conversation_id=conversation_id, role="assistant", content="Some cited answer.")
        db.add(message)
        db.flush()
        db.add(Citation(message_id=message.id, document_id=uuid.uuid4(), rank=1, section_path="A", snippet="s"))
        db.commit()
        message_id = message.id
    finally:
        db.close()

    delete_response = client.delete(f"/api/v1/conversations/{conversation_id}", headers=API_KEY_HEADER)
    assert delete_response.status_code == 204
    assert delete_response.content == b""

    get_response = client.get(f"/api/v1/conversations/{conversation_id}", headers=API_KEY_HEADER)
    assert get_response.status_code == 404

    db = SessionLocal()
    try:
        assert db.get(Conversation, conversation_id) is None
        assert db.get(Message, message_id) is None
    finally:
        db.close()
