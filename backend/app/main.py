from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.chat import router as chat_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.ingestion import router as ingestion_router
from app.api.v1.models import router as models_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.services.ingestion import reap_stale_runs

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A 'pending'/'running' ingestion_runs row can only be left over from a
    # process that died before finishing it (see reap_stale_runs' docstring)
    # -- never a run this fresh process is already tracking, since it just
    # started.
    reap_stale_runs()
    yield


app = FastAPI(title="RAG Knowledge Chatbot", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(models_router, prefix="/api/v1")
