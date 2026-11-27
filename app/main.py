from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agent import OlistAnalyticsAgent
from app.conversation_store import ConversationStore
from app.data_store import DataStoreError, OlistDataStore
from app.llm_client import LLMConfigurationError

STATIC_DIR = Path(__file__).resolve().parent / "static"
conversation_store = ConversationStore()

app = FastAPI(
    title="Olist Analytics Agent",
    description="A stateful, read-only analytics agent with traceable SQL evidence.",
    version="0.2.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, object]:
    database_path = OlistDataStore().database_path
    return {
        "status": "ok",
        "database_ready": database_path.is_file(),
        "model_configured": bool(
            os.getenv("LLM_API_KEY") and os.getenv("LLM_MODEL")
        ),
    }


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, object]:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be blank.")
    session_id = request.session_id
    if not conversation_store.exists(session_id):
        session_id = conversation_store.create_session()
    try:
        result = OlistAnalyticsAgent().answer(
            question,
            history=conversation_store.history(session_id),
        )
        conversation_store.save_turn(session_id, question, result["answer"])
        return {"session_id": session_id, **result}
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DataStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, object]:
    if not conversation_store.exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    return {
        "session_id": session_id,
        "messages": conversation_store.messages(session_id),
    }
