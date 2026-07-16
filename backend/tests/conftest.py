import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import engine
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session():
    """Yield a Session bound to a connection whose transaction is rolled
    back at teardown, so schema-integrity tests never leave rows behind in
    the dev database."""
    connection = engine.connect()
    transaction = connection.begin()
    testing_session_local = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session: Session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
