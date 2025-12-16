from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from assistant_builder_client import AssistantBuilderClient
from models import (
    AdvanceDebateResponse,
    CreateTemplateRequest,
    DebateRun,
    DebateTemplate,
    ErrorResponse,
    FinalRecord,
    StartDebateRequest,
)
from orchestrator import DebateOrchestrator
from storage import InMemoryStore


app = FastAPI(title="Debate Arena Orchestrator", version="0.1.0")

store = InMemoryStore()
client = AssistantBuilderClient(
    base_url=os.getenv("OVMS_BASE_URL", "http://127.0.0.1:8000"),
    max_tokens=int(os.getenv("MAX_TOKENS", "256")),
)
orchestrator = DebateOrchestrator(store=store, client=client)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/ui", StaticFiles(directory=_frontend_dir, html=True), name="frontend")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await client.aclose()


@app.on_event("startup")
async def startup_event() -> None:
    await client.warmup()


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/templates", response_model=list[DebateTemplate])
async def list_templates() -> list[DebateTemplate]:
    return store.list_templates()


@app.post("/templates", response_model=DebateTemplate, responses={400: {"model": ErrorResponse}})
async def create_template(payload: CreateTemplateRequest) -> DebateTemplate:
    try:
        template = DebateTemplate(**payload.model_dump())
        return store.add_template(template)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/templates/{template_id}")
async def delete_template(template_id: str) -> dict:
    store.delete_template(template_id)
    return {"status": "deleted"}


@app.post(
    "/debates",
    response_model=DebateRun,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def start_debate(payload: StartDebateRequest) -> DebateRun:
    try:
        return await orchestrator.start_debate(payload)
    except ValueError as exc:
        status = 404 if "template" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@app.get(
    "/debates/{debate_id}",
    response_model=DebateRun,
    responses={404: {"model": ErrorResponse}},
)
async def get_debate(debate_id: str) -> DebateRun:
    run = store.get_run(debate_id)
    if run:
        return run
    final = next((f for f in store.list_finals() if f.debate_id == debate_id), None)
    if final:
        raise HTTPException(status_code=404, detail="debate closed; only final record retained")
    raise HTTPException(status_code=404, detail="debate not found")


@app.post(
    "/debates/{debate_id}/advance",
    response_model=AdvanceDebateResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def advance_debate(debate_id: str) -> AdvanceDebateResponse:
    try:
        return await orchestrator.advance_debate(debate_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@app.post(
    "/debates/{debate_id}/cancel",
    response_model=DebateRun,
    responses={404: {"model": ErrorResponse}},
)
async def cancel_debate(debate_id: str) -> DebateRun:
    try:
        return await orchestrator.cancel(debate_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/finals", response_model=list[FinalRecord])
async def list_final_records() -> list[FinalRecord]:
    return store.list_finals()
