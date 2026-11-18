# /// script
# requires-python = ">=3.12"
# dependencies = ["fastapi", "uvicorn", "httpx"]
# ///
"""limn draw-button server.

Pipeline: Atom VoiceS3R --WAV--> POST /upload --> OpenRouter STT --> omp headless
in the limn workspace --> frameit (fal.ai) --> newest _upscaled.png in images/
served to the TV kiosk page.

Run:  uv run draw_server.py
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import threading
import time
import wave
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

SERVER_DIR = Path(__file__).resolve().parent
HOME = Path.home()

LIMN_DIR = Path(os.environ.get("LIMN_DIR", HOME / "src" / "limn"))
IMAGES_DIR = LIMN_DIR / "images"
UPLOADS_DIR = SERVER_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
OMP_BIN = os.environ.get("OMP_BIN", str(HOME / ".bun" / "bin" / "omp"))
OMP_TIMEOUT_S = int(os.environ.get("OMP_TIMEOUT_S", "600"))
STT_MODEL = os.environ.get("STT_MODEL", "openai/whisper-large-v3")
STT_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
PORT = int(os.environ.get("PORT", "8000"))

# ---------------------------------------------------------------------------
# config: env > server/.env > omp's stored openrouter credential
# ---------------------------------------------------------------------------

def _load_dotenv() -> dict[str, str]:
    vals: dict[str, str] = {}
    env_file = SERVER_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def _omp_openrouter_key() -> str | None:
    db = HOME / ".omp" / "agent" / "agent.db"
    if not db.exists():
        return None
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
            row = con.execute(
                "SELECT data FROM auth_credentials WHERE provider = 'openrouter' LIMIT 1"
            ).fetchone()
        if row:
            import json

            return json.loads(row[0]).get("key")
    except Exception:
        return None
    return None


_DOTENV = _load_dotenv()
OPENROUTER_API_KEY = (
    os.environ.get("OPENROUTER_API_KEY") or _DOTENV.get("OPENROUTER_API_KEY") or _omp_openrouter_key()
)
FAL_KEY = os.environ.get("FAL_KEY") or _DOTENV.get("FAL_KEY") or ""

# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_state: dict = {
    "status": "idle",  # idle | thinking | done | error
    "transcript": "",
    "image": None,  # /image/<filename>
    "ts": 0,
    "error": "",
}
_job_seq = 0

app = FastAPI()


def _set_state(**kw) -> None:
    with _lock:
        _state.update(kw)
        _state["ts"] = time.time()


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

def _transcribe(wav_path: Path) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "no OpenRouter API key (set OPENROUTER_API_KEY in env or server/.env)"
        )
    b64 = base64_bytes(wav_path)
    resp = httpx.post(
        STT_URL,
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
        json={
            "model": STT_MODEL,
            "input_audio": {"data": b64, "format": "wav"},
        },
        timeout=120,
    )
    resp.raise_for_status()
    text = resp.json().get("text", "").strip()
    if not text:
        raise RuntimeError("empty transcript")
    return text


def base64_bytes(wav_path: Path) -> str:
    import base64

    return base64.b64encode(wav_path.read_bytes()).decode("ascii")


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------

def _newest_image_after(ts: float) -> Path | None:
    candidates = [
        p
        for p in IMAGES_DIR.iterdir()
        if p.suffix in (".png", ".jpg") and p.stat().st_mtime >= ts
    ]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _run_generation(job_id: int, transcript: str) -> None:
    started = time.time() - 1
    _set_state(status="thinking", transcript=transcript, error="")
    prompt = (
        f'Voice request from the draw button (a small child spoke this): "{transcript}". '
        "Treat it as an image request. Improve the prompt per your instructions, "
        "then generate it with skills/frameit using `--size tv` (fast TV-resolution "
        "path). This is a one-shot request: generate exactly once; if the generation "
        "fails, report the failure instead of retrying. If the request refers to a "
        "previous image (e.g. \"make it bigger\", \"make it snowier\"), treat it as an "
        "edit of the most recent image per skills/frameit edit rules and say so in "
        "your reply."
    )
    env = os.environ.copy()
    if FAL_KEY:
        env["FAL_KEY"] = FAL_KEY
    try:
        proc = subprocess.Popen(
            [OMP_BIN, "-p", prompt, "--no-session", "--cwd", str(LIMN_DIR)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            out, err = proc.communicate(timeout=OMP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), 15)  # omp spawns children; kill the group
            raise RuntimeError(f"omp timed out after {OMP_TIMEOUT_S}s")
        if proc.returncode != 0:
            raise RuntimeError(f"omp exit {proc.returncode}: {err[-500:]}")
        img = _newest_image_after(started)
        if img is None:
            raise RuntimeError("omp finished but no new image appeared in images/")
        _set_state(status="done", image=f"/image/{img.name}")
    except Exception as e:  # noqa: BLE001
        _set_state(status="error", error=str(e))


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

@app.post("/upload")
async def upload(request: Request) -> JSONResponse:
    global _job_seq
    body = await request.body()
    if len(body) < 100 or body[:4] != b"RIFF":
        return JSONResponse({"ok": False, "error": "expected WAV body"}, status_code=400)
    ts = time.strftime("%Y%m%d_%H%M%S")
    wav_path = UPLOADS_DIR / f"{ts}_{_job_seq:04d}.wav"
    _job_seq += 1
    wav_path.write_bytes(body)

    # prune old uploads, keep newest 100
    ups = sorted(UPLOADS_DIR.glob("*.wav"))
    for old in ups[:-100]:
        old.unlink(missing_ok=True)

    try:
        transcript = _transcribe(wav_path)
    except Exception as e:  # noqa: BLE001
        _set_state(status="error", error=f"stt: {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)

    threading.Thread(
        target=_run_generation, args=(_job_seq, transcript), daemon=True
    ).start()
    return JSONResponse({"ok": True, "transcript": transcript})


@app.get("/state")
async def state() -> JSONResponse:
    with _lock:
        return JSONResponse(dict(_state))


_IMAGE_RE = re.compile(r"^[A-Za-z0-9_\-]+\.(?:png|jpg)$")


@app.get("/image/{name}")
async def image(name: str) -> FileResponse:
    if not _IMAGE_RE.match(name):
        return JSONResponse({"error": "bad name"}, status_code=400)
    path = IMAGES_DIR / name
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    media = "image/png" if name.endswith(".png") else "image/jpeg"
    return FileResponse(path, media_type=media, headers={"Cache-Control": "no-cache"})


@app.get("/")
async def kiosk() -> HTMLResponse:
    return HTMLResponse(KIOSK_HTML)


KIOSK_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>limn</title>
<style>
  html, body { margin: 0; height: 100%; background: #000; overflow: hidden; }
  #stage { position: fixed; inset: 0; }
  img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain;
        opacity: 0; transition: opacity 1.2s ease; }
  img.show { opacity: 1; }
  #hint { position: fixed; left: 50%; top: 50%; transform: translate(-50%, -50%);
          color: #444; font: 5vh sans-serif; }
  #wait { position: fixed; left: 50%; bottom: 6vh; transform: translateX(-50%);
          color: #666; font: 4vh sans-serif; display: none; }
  #wait span { animation: pulse 1.2s infinite; display: inline-block; }
  #wait span:nth-child(2) { animation-delay: .2s; }
  #wait span:nth-child(3) { animation-delay: .4s; }
  @keyframes pulse { 0%, 100% { opacity: .2; } 50% { opacity: 1; } }
</style>
</head>
<body>
<div id="stage"></div>
<div id="hint">say something to the little box</div>
<div id="wait">drawing<span>.</span><span>.</span><span>.</span></div>
<script>
const stage = document.getElementById('stage');
const hint = document.getElementById('hint');
const wait = document.getElementById('wait');
let shown = null;
let a = document.createElement('img'), b = document.createElement('img');
let front = a;
stage.append(a, b);

function show(src) {
  const back = front === a ? b : a;
  back.src = src;
  back.onload = () => {
    back.classList.add('show');
    front.classList.remove('show');
    front = back;
    hint.style.display = 'none';
  };
}

async function poll() {
  try {
    const s = await (await fetch('/state')).json();
    wait.style.display = s.status === 'thinking' ? 'block' : 'none';
    if (s.image && s.image !== shown) { shown = s.image; show(s.image + '?t=' + s.ts); }
    if (!s.image && s.status === 'idle') hint.style.display = 'block';
  } catch (e) { /* server briefly down; keep last image */ }
}
setInterval(poll, 1000);
poll();
</script>
</body>
</html>"""


if __name__ == "__main__":
    print(f"limn draw server: limn={LIMN_DIR} stt={STT_MODEL} "
          f"openrouter_key={'set' if OPENROUTER_API_KEY else 'MISSING'} "
          f"fal_key={'set' if FAL_KEY else 'MISSING'}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
