import pytest

from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.core.security import require_api_key


def test_require_api_key_rejects_missing_key():
    with pytest.raises(UnauthorizedError):
        require_api_key(None)


def test_require_api_key_rejects_wrong_key():
    with pytest.raises(UnauthorizedError):
        require_api_key("wrong-key")


def test_require_api_key_accepts_correct_key():
    settings = get_settings()
    assert require_api_key(settings.api_key) == settings.api_key
