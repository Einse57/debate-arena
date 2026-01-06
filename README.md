# Debate Arena

Minimal local debate orchestrator that fronts OVMS (OpenVINO Model Server) via its OpenAI-compatible `/v3/chat/completions` endpoint and serves a lightweight UI.

![Debate Arena UI](debate_arena_UI.png)

## Architecture
```
+------------+           +-----------------------+           +------------------------------+
|  Browser   |  HTTP     | FastAPI app (/ui, API)|  HTTP     | OVMS OpenAI REST endpoint    |
|  UI (SPA)  |<--------->| - Orchestrator        |<--------->| /v3/chat/completions         |
|            |           | - In-memory store     |           | (models on local OVMS)       |
+------------+           +-----------------------+           +------------------------------+
```
- UI is static HTML/JS served from `/ui` on the FastAPI app.
- Orchestrator coordinates debate templates/runs and fans out chat calls to OVMS via `httpx`.
- In-memory store holds templates/runs/finals (non-persistent).

## Prerequisites
- Python 3.12 (or compatible)
- OVMS running locally with an OpenAI-style chat endpoint at `http://127.0.0.1:8000/v3/chat/completions` or similar.
- A model or multiple models available to OVMS (e.g., `OpenVINO/Phi-3.5-mini-instruct-int4-ov`).

### Example OVMS runs

#### Bare metal
```powershell
# Set HF token if pulling models from Hugging Face
$Env:HF_TOKEN = "hf_your_token"

# Launch OVMS with the provided multi-model config
ovms --config_path models/config.json --rest_port 8000 --rest_bind_address 0.0.0.0 --cache_size 2
```

Alternatively, single model without config:
```powershell
ovms --model_name phi35-mini --model_path models/OpenVINO/Phi-3.5-mini-instruct-int4-ov --rest_port 8000 --target_device GPU --task text_generation --cache_size 2
```

#### Docker
```bash
# From a folder containing your model (mounted at /models inside the container)
docker run --rm \
  -p 8000:8000 \
  -v %cd%/models:/models \
  openvino/model_server:latest \
  --config_path /models/config.json \
  --rest_port 8000 \
  --rest_bind_address 0.0.0.0
```

#### Health check
```bash
curl -X POST http://127.0.0.1:8000/v3/chat/completions \ 
  -H "Content-Type: application/json" \ 
  -d '{"model":"phi35-mini","max_tokens":30,"temperature":0,"stream":false,"messages":[{"role":"system","content":"You are a helpful assistant."},{"role":"user","content":"Say hi"}]}'
```

## Setup

### 1. Backend
```
cd backend
python -m venv .venv
# PowerShell
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

### 2. Configuration (optional)
Copy `.env.example` to `.env` and adjust as needed:
```
OVMS_BASE_URL=http://127.0.0.1:8000
MAX_TOKENS=256
```

## Run

### Quick start (PowerShell)
From repo root:
```
pwsh ./start.ps1
```
Defaults: host `127.0.0.1`, port `8001`, `OVMS_BASE_URL=http://127.0.0.1:8000`. Override as needed:
```
pwsh ./start.ps1 -Host 0.0.0.0 -Port 8001 -OvmsBaseUrl http://localhost:8000
```

### Manual (within backend dir)
```
$env:OVMS_BASE_URL="http://127.0.0.1:8000"
uvicorn app:app --port 8001 --reload
```

Open the UI at: http://127.0.0.1:8001/ui/

## Usage
- Fill in topic, rounds, mode (auto or step), and participants (odd count; model IDs must match OVMS models).
- Start Debate.
  - Auto mode: UI polls and renders as phases complete.
  - Step mode: UI auto-advances phases to stream updates as they finish.
- Debate Arena panel shows chat-style outputs per participant/phase and final outcome.

## Notes
- Storage is in-memory; restarting the app clears templates/runs.
- Final records are still recorded server-side for API access, but the UI focuses on live debate output.
- Frontend automatically detects API base URL (works with any host/port).
- See `models/config.json` for multi-model OVMS setup with phi35-mini, qwen2.5-7b, and qwen2.5-0.5b.
