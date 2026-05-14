---
stage: planning
status: ready
created: 2026-05-15
---

# Noctune Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a music library manager that fingerprints, tags, normalizes, and syncs music files to Navidrome — with an LLM reconciliation layer and a Svelte review UI.

**Architecture:** Python 3.12+ backend (FastAPI, mutagen, watchdog, chromaprint) with Svelte+Tailwind frontend. Three-layer tag pipeline (fingerprint → extract → LLM reconcile). SQLite for pipeline state. Event-driven file watching with debounce. rsync for transfer.

**Tech Stack:** Python 3.12+, FastAPI, mutagen, watchdog, chromaprint, pyacoustid, Pydantic v2, Svelte 5, Tailwind 4, Ollama, SQLite

---

## Phase 1: Foundation

Skeleton project, config, models, and the first vertical slice — a file watched, fingerprinted, and logged.

### T1 — Project scaffold

**Objective:** Bootable Python project with FastAPI, structure, and tooling.

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/noctune/__init__.py`
- Create: `backend/src/noctune/main.py`
- Create: `backend/src/noctune/config.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/src/noctune/models/__init__.py`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "noctune"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "mutagen>=1.47",
    "watchdog>=6.0",
    "pyacoustid>=1.3",
    "httpx>=0.28",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "ANN", "B", "SIM", "TCH", "RUF"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

**Step 2: Create config.py with settings model**

```python
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    source_dir: Path = Path("~/Music/Incoming").expanduser()
    dest_host: str = "192.168.178.107"
    dest_user: str = "eversin"
    dest_dir: Path = Path("/data/music")
    db_path: Path = Path("~/.noctune/state.db").expanduser()
    debounce_seconds: float = 5.0
    confidence_threshold: float = 0.8

    model_config = {"env_prefix": "NOCTUNE_", "env_file": ".env"}
```

**Step 3: Create minimal FastAPI app**

```python
from fastapi import FastAPI

app = FastAPI(title="Noctune")

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

**Step 4: Verify**

Run: `cd backend && pip install -e ".[dev]" && uvicorn noctune.main:app --port 8000 &`
Then: `curl http://localhost:8000/health`
Expected: `{"status":"ok"}`

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: project scaffold with FastAPI, config, and tooling"
```

---

### T2 — Core data models (Pydantic)

**Objective:** Define the data structures that flow through the pipeline — every model the system needs.

**Files:**
- Create: `backend/src/noctune/models/track.py`
- Create: `backend/src/noctune/models/pipeline.py`
- Create: `backend/src/noctune/models/config.py`
- Test: `backend/tests/test_models.py`

**Step 1: Write failing test**

```python
from noctune.models.track import TrackMeta, TagSet
from noctune.models.pipeline import PipelineStatus, FileState

def test_tagset_creation():
    tags = TagSet(
        artist="Radiohead",
        album="Kid A",
        title="Everything In Its Right Place",
        track_number=1,
        year=2000,
        genre="Electronic",
    )
    assert tags.artist == "Radiohead"
    assert tags.genre == "Electronic"

def test_trackmeta_from_path():
    meta = TrackMeta(
        path=Path("/music/01 - Radiohead - Kid A.flac"),
        file_size_bytes=45000000,
        duration_seconds=248.5,
        format="flac",
        bitrate=942,
    )
    assert meta.format == "flac"
    assert meta.duration_seconds == 248.5

def test_filestate_enum():
    assert FileState.DISCOVERED == "discovered"
    assert FileState.FINGERPRINTED == "fingerprinted"

def test_pipeline_status():
    status = PipelineStatus(
        file_path="/music/test.flac",
        state=FileState.DISCOVERED,
        confidence=0.0,
    )
    assert status.state == FileState.DISCOVERED
```

**Step 2: Run test to verify failure**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — modules don't exist

**Step 3: Implement models**

`track.py`:
```python
from pathlib import Path
from pydantic import BaseModel, Field

class TagSet(BaseModel):
    artist: str = ""
    album_artist: str = ""
    album: str = ""
    title: str = ""
    track_number: int | None = None
    year: int | None = None
    genre: str = ""
    comment: str = ""

class TrackMeta(BaseModel):
    path: Path
    file_size_bytes: int
    duration_seconds: float
    format: str
    bitrate: int | None = None
    existing_tags: TagSet | None = None
    has_cover_art: bool = False
```

`pipeline.py`:
```python
from enum import StrEnum
from pydantic import BaseModel

class FileState(StrEnum):
    DISCOVERED = "discovered"
    STABLE = "stable"
    FINGERPRINTED = "fingerprinted"
    EXTRACTED = "extracted"
    RECONCILED = "reconciled"
    TAGGED = "tagged"
    QUEUED_FOR_REVIEW = "queued_for_review"
    TRANSFERRED = "transferred"
    FAILED = "failed"

class PipelineStatus(BaseModel):
    file_path: str
    state: FileState = FileState.DISCOVERED
    confidence: float = 0.0
    mb_release_group_id: str | None = None
    error: str | None = None
```

`config.py`:
```python
from pydantic import BaseModel
from pathlib import Path

class LLMConfig(BaseModel):
    direction: str = "local"
    local_base_url: str = "http://localhost:11434"
    local_model: str = "llama3:8b"
    cloud_base_url: str = "https://api.ollama.com/v1"
    cloud_api_key: str = ""
    cloud_model: str = "llama3:70b"
    fallback: str = "cloud"
    batch_size: int = 20

class NoctuneConfig(BaseModel):
    source_dir: Path
    dest_host: str
    dest_user: str
    dest_dir: Path
    valid_extensions: list[str] = [".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac"]
    genre_vocabulary: list[str] = []
    llm: LLMConfig = LLMConfig()
    confidence_threshold: float = 0.8
    debounce_seconds: float = 5.0
```

**Step 4: Run test to verify pass**

Run: `pytest tests/test_models.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: core Pydantic models — TagSet, TrackMeta, PipelineStatus, NoctuneConfig"
```

---

### T3 — SQLite state store

**Objective:** Persistent pipeline state so the 60GB bulk job can resume after a crash.

**Files:**
- Create: `backend/src/noctune/store.py`
- Test: `backend/tests/test_store.py`

**Step 1: Write failing test**

```python
import tempfile
from pathlib import Path
from noctune.store import StateStore
from noctune.models.pipeline import PipelineStatus, FileState

def test_upsert_and_get():
    with tempfile.TemporaryDirectory() as tmp:
        store = StateStore(Path(tmp) / "test.db")
        store.initialize()
        status = PipelineStatus(file_path="/music/test.flac", state=FileState.DISCOVERED)
        store.upsert(status)
        result = store.get("/music/test.flac")
        assert result is not None
        assert result.state == FileState.DISCOVERED

def test_list_by_state():
    with tempfile.TemporaryDirectory() as tmp:
        store = StateStore(Path(tmp) / "test.db")
        store.initialize()
        store.upsert(PipelineStatus(file_path="/music/a.flac", state=FileState.DISCOVERED))
        store.upsert(PipelineStatus(file_path="/music/b.flac", state=FileState.TAGGED))
        store.upsert(PipelineStatus(file_path="/music/c.flac", state=FileState.DISCOVERED))
        discovered = store.list_by_state(FileState.DISCOVERED)
        assert len(discovered) == 2
```

**Step 2: Run test to verify failure**

Run: `pytest tests/test_store.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement StateStore**

```python
import sqlite3
from pathlib import Path
from noctune.models.pipeline import PipelineStatus, FileState

class StateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_state (
                    file_path TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    mb_release_group_id TEXT,
                    error TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)

    def upsert(self, status: PipelineStatus) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO pipeline_state (file_path, state, confidence, mb_release_group_id, error)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    state=excluded.state,
                    confidence=excluded.confidence,
                    mb_release_group_id=excluded.mb_release_group_id,
                    error=excluded.error,
                    updated_at=datetime('now')
            """, (status.file_path, status.state, status.confidence,
                  status.mb_release_group_id, status.error))

    def get(self, file_path: str) -> PipelineStatus | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT file_path, state, confidence, mb_release_group_id, error FROM pipeline_state WHERE file_path = ?",
                (file_path,)
            ).fetchone()
            if row is None:
                return None
            return PipelineStatus(
                file_path=row[0], state=FileState(row[1]),
                confidence=row[2], mb_release_group_id=row[3], error=row[4]
            )

    def list_by_state(self, state: FileState) -> list[PipelineStatus]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT file_path, state, confidence, mb_release_group_id, error FROM pipeline_state WHERE state = ?",
                (state.value,)
            ).fetchall()
            return [PipelineStatus(
                file_path=r[0], state=FileState(r[1]),
                confidence=r[2], mb_release_group_id=r[3], error=r[4]
            ) for r in rows]
```

**Step 4: Run test to verify pass**

Run: `pytest tests/test_store.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: SQLite state store for pipeline resumability"
```

---

### T4 — Config loading (YAML)

**Objective:** Load the full Noctune config from a YAML file, including genre vocabulary and LLM routing.

**Files:**
- Create: `backend/src/noctune/config_loader.py`
- Test: `backend/tests/test_config_loader.py`
- Create: `backend/config.example.yaml`

**Step 1: Write failing test**

```python
import tempfile
from pathlib import Path
from noctune.config_loader import load_config

def test_load_config():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "config.yaml"
        config_path.write_text("""
source_dir: ~/Music/Incoming
dest_host: 192.168.178.107
dest_user: eversin
dest_dir: /data/music
valid_extensions: [.mp3, .flac, .m4a, .ogg]
genre_vocabulary:
  - Rock
  - Pop
  - Electronic
  - Jazz
llm:
  direction: local
  local_model: llama3:8b
  batch_size: 20
confidence_threshold: 0.8
""")
        config = load_config(config_path)
        assert config.source_dir == Path("~/Music/Incoming").expanduser()
        assert len(config.genre_vocabulary) == 4
        assert config.genre_vocabulary[2] == "Electronic"
        assert config.llm.direction == "local"
        assert config.llm.batch_size == 20
```

**Step 2: Run test to verify failure**

**Step 3: Implement config_loader.py**

```python
import yaml
from pathlib import Path
from noctune.models.config import NoctuneConfig

def load_config(path: Path) -> NoctuneConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)
    raw["source_dir"] = Path(raw["source_dir"]).expanduser()
    raw["dest_dir"] = Path(raw["dest_dir"])
    return NoctuneConfig(**raw)
```

**Step 4: Run test to verify pass**

**Step 5: Create config.example.yaml** (full example config with all fields and comments)

**Step 6: Commit**

```bash
git add -A && git commit -m "feat: YAML config loading with genre vocabulary and LLM routing"
```

---

## Phase 2: Pipeline Core

The three-layer tag engine + file watcher + debounce.

### T5 — File watcher with debounce

**Objective:** Watch a directory for music files, debounce events, emit stable file paths.

**Files:**
- Create: `backend/src/noctune/watcher.py`
- Test: `backend/tests/test_watcher.py`

**Step 1: Write failing test for debounce logic** (unit test the timer, not the filesystem observer)

```python
import asyncio
from noctune.watcher import DebouncedWatcher

async def test_debounce_collects_events():
    watcher = DebouncedWatcher(debounce_seconds=0.1)
    events: list[str] = []
    watcher.on_stable(lambda path: events.append(str(path)))

    # Simulate rapid events
    watcher._handle_event(type("Event", (), {"src_path": "/music/test.flac", "event_type": "created"}) )
    watcher._handle_event(type("Event", (), {"src_path": "/music/test.flac", "event_type": "modified"}) )

    await asyncio.sleep(0.3)
    assert len(events) == 1
    assert "/music/test.flac" in events[0]
```

**Step 2: Run test to verify failure**

**Step 3: Implement DebouncedWatcher**

Uses `asyncio` timers. When an event fires, reset the debounce timer. When the timer expires, the file is stable and callbacks fire.

**Step 4: Run test to verify pass**

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: file watcher with async debounce logic"
```

---

### T6 — Layer 1: Fingerprint & MusicBrainz lookup

**Objective:** Given a stable file path, fingerprint it with chromaprint and look up against Acoustid/MusicBrainz. Returns a `TagSet` with canonical data.

**Files:**
- Create: `backend/src/noctune/fingerprint.py`
- Test: `backend/tests/test_fingerprint.py`

**Step 1: Write failing test** (mock the Acoustid API call)

```python
from unittest.mock import patch
from noctune.fingerprint import fingerprint_and_lookup

def test_fingerprint_lookup_returns_tagset():
    with patch("noctune.fingerprint._acoustid_lookup") as mock_lookup:
        mock_lookup.return_value = {
            "artist": "Radiohead",
            "album": "Kid A",
            "title": "Everything In Its Right Place",
            "track_number": 1,
            "year": 2000,
            "release_group_id": "mb-abc123",
        }
        api_key = "test-key"
        result = fingerprint_and_lookup(Path("/music/test.flac"), api_key)
        assert result.artist == "Radiohead"
        assert result.album == "Kid A"
        assert result.year == 2000
```

**Step 2: Run test to verify failure**

**Step 3: Implement fingerprint.py**

Uses `pyacoustid` for fingerprinting + `httpx` for MusicBrainz lookup. Returns a `TagSet` with a `release_group_id` for album grouping.

**Step 4: Run test to verify pass**

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: Layer 1 — fingerprint and MusicBrainz lookup"
```

---

### T7 — Layer 2: Metadata extraction

**Objective:** Extract existing tags from mutagen, parse filenames, parse directory structure into a `TagSet`.

**Files:**
- Create: `backend/src/noctune/extract.py`
- Test: `backend/tests/test_extract.py`

**Step 1: Write failing test**

```python
from noctune.extract import extract_metadata, parse_filename, parse_directory

def test_parse_filename_standard():
    result = parse_filename("01 - Radiohead - Everything In Its Right Place.flac")
    assert result.artist == "Radiohead"
    assert result.track_number == 1
    assert result.title == "Everything In Its Right Place"

def test_parse_directory():
    result = parse_directory(Path("/music/Radiohead/Kid A/01 - Track.flac"))
    assert result.artist == "Radiohead"
    assert result.album == "Kid A"

def test_extract_metadata_merges_signals():
    # Mocks mutagen call, filename parse, directory parse
    # Returns merged TagSet with all available signals
    ...
```

**Step 2: Run test to verify failure**

**Step 3: Implement extract.py**

Three functions: `parse_filename`, `parse_directory`, `extract_metadata` (calls mutagen + filename parser + directory parser, merges all signals).

**Step 4: Run test to verify pass**

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: Layer 2 — metadata extraction from tags, filename, directory"
```

---

### T8 — Layer 3: LLM reconciliation

**Objective:** Feed Layer 1 + Layer 2 signals to LLM, receive normalized `TagSet` with confidence score.

**Files:**
- Create: `backend/src/noctune/reconcile.py`
- Create: `backend/src/noctune/llm_router.py`
- Test: `backend/tests/test_reconcile.py`

**Step 1: Write failing test**

```python
from unittest.mock import AsyncMock
from noctune.reconcile import reconcile_tags
from noctune.models.track import TagSet

async def test_reconcile_produces_normalized_tagset():
    mock_router = AsyncMock()
    mock_router.complete.return_value = '{"artist": "Radiohead", "album": "Kid A", "title": "Everything In Its Right Place", "track_number": 1, "year": 2000, "genre": "Electronic", "confidence": 0.95}'

    result = await reconcile_tags(
        fingerprint_tags=TagSet(artist="Radiohead", album="Kid A", title="Everything In Its Right Place", year=2000),
        extracted_tags=TagSet(artist="Radiohead", album="Kid A", title="Everything In Its Right Place"),
        genre_vocabulary=["Rock", "Pop", "Electronic", "Jazz"],
        llm_router=mock_router,
    )
    assert result.genre == "Electronic"
    assert result.confidence == 0.95
```

**Step 2: Run test to verify failure**

**Step 3: Implement llm_router.py**

```python
class LLMRouter:
    """Routes LLM calls to local Ollama or cloud endpoint."""
    def __init__(self, config: LLMConfig) -> None: ...
    async def complete(self, prompt: str) -> str: ...
```

Uses `httpx.AsyncClient` to call OpenAI-compatible chat completions endpoint. Config decides local vs cloud. Fallback logic built in.

**Step 4: Implement reconcile.py**

Structures the prompt (all signals as structured JSON), sends to LLM router, parses the response into a Pydantic-validated `TagSet` with `confidence` field. Genre is constrained to vocabulary.

**Step 5: Run test to verify pass**

**Step 6: Commit**

```bash
git add -A && git commit -m "feat: Layer 3 — LLM reconciliation with genre-constrained output"
```

---

### T9 — Tag writer (mutagen) + sidecar backup

**Objective:** Write normalized tags to audio files. Before writing, save original tags to `.tags.json` sidecar.

**Files:**
- Create: `backend/src/noctune/tag_writer.py`
- Test: `backend/tests/test_tag_writer.py`

**Step 1: Write failing test** (uses tiny test audio files)

**Step 2: Implement tag_writer.py**

```python
def backup_tags(path: Path) -> Path:
    """Save original tags to sidecar file. Returns sidecar path."""

def write_tags(path: Path, tags: TagSet) -> Path:
    """Write normalized tags to audio file. Backs up first."""
```

Supports MP3 (ID3v2.4), FLAC (Vorbis), M4A (MP4), OGG (Vorbis). Mutagen handles format detection.

**Step 3: Run test to verify pass**

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: tag writer with sidecar backup and multi-format support"
```

---

### T10 — Pipeline orchestrator

**Objective:** Tie all three layers together. For a given file path, run fingerprint → extract → reconcile → write tags → update state.

**Files:**
- Create: `backend/src/noctune/pipeline.py`
- Test: `backend/tests/test_pipeline.py`

**Step 1: Write failing test** (mocks each layer, verifies state transitions)

**Step 2: Implement Pipeline class**

```python
class Pipeline:
    def __init__(self, config: NoctuneConfig, store: StateStore, llm_router: LLMRouter) -> None: ...

    async def process_file(self, path: Path) -> PipelineStatus:
        """Run a file through the full three-layer pipeline."""

    async def process_batch(self, paths: list[Path]) -> list[PipelineStatus]:
        """Group by release_group_id, batch-reconcile albums together."""
```

State machine: DISCOVERED → STABLE → FINGERPRINTED → EXTRACTED → RECONCILED → TAGGED → TRANSFERRED (or QUEUED_FOR_REVIEW). Each step updates SQLite.

**Step 3: Run test to verify pass**

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: pipeline orchestrator — three-layer pipeline with state transitions"
```

---

## Phase 3: Transfer & Sync

### T11 — rsync transfer backend

**Objective:** Sync tagged files to Pi via rsync. Pluggable interface for future backends.

**Files:**
- Create: `backend/src/noctune/transfer.py`
- Test: `backend/tests/test_transfer.py`

**Step 1: Write failing test**

**Step 2: Implement transfer backends**

```python
class TransferBackend(Protocol):
    async def transfer(self, local_path: Path, remote_dir: Path) -> bool: ...

class RsyncBackend:
    def __init__(self, host: str, user: str) -> None: ...
    async def transfer(self, local_path: Path, remote_dir: Path) -> bool: ...

class CopyBackend:
    """For local testing — just cp to a directory."""
    async def transfer(self, local_path: Path, remote_dir: Path) -> bool: ...
```

**Step 3: Run test to verify pass**

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: rsync transfer backend with pluggable interface"
```

---

### T12 — Library normalizer

**Objective:** Restructure tagged files into `Artist/Album (Year)/01 - Track.flac` based on their tags.

**Files:**
- Create: `backend/src/noctune/normalize.py`
- Test: `backend/tests/test_normalize.py`

**Step 1: Write failing test**

```python
from noctune.normalize import compute_target_path

def test_compute_target_path():
    tags = TagSet(artist="Radiohead", album="Kid A", track_number=1, title="Everything In Its Right Place", year=2000, genre="Electronic")
    result = compute_target_path(tags, Path("/music"))
    assert result == Path("/music/Radiohead/Kid A (2000)/01 - Everything In Its Right Place.flac")
```

**Step 2: Implement normalize.py**

`compute_target_path(tags, base_dir)` → derives target path from tags. `preview_normalization(files)` → returns list of (old_path, new_path) pairs. `execute_normalization(pairs)` → renames files. Source stays untouched until confirmed.

**Step 3: Run test to verify pass**

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: library normalizer — tags-first restructuring with preview"
```

---

## Phase 4: FastAPI Endpoints

### T13 — REST API endpoints

**Objective:** Expose pipeline state, config, review queue, and trigger actions via FastAPI.

**Files:**
- Create: `backend/src/noctune/api.py`
- Test: `backend/tests/test_api.py`

**Endpoints:**

```
GET  /api/health              — health check
GET  /api/status               — overall pipeline status (counts by state)
GET  /api/files                — list files, filterable by state
GET  /api/files/{path}         — detail for one file
POST /api/files                — add file(s) to pipeline
POST /api/pipeline/start       — start processing all DISCOVERED files
POST /api/pipeline/stop        — stop background processing
GET  /api/review               — list files in QUEUED_FOR_REVIEW state
POST /api/review/{path}/approve — approve review item, write tags
POST /api/review/{path}/reject  — reject, revert tags from sidecar
POST /api/normalize/preview    — preview normalization
POST /api/normalize/execute    — execute normalization
POST /api/transfer/{path}      — transfer a tagged file to Pi
GET  /api/config               — read config
```

**Step 1: Write failing test** (using FastAPI TestClient)

**Step 2: Implement api.py**

Wire up endpoints to StateStore, Pipeline, and TransferBackend. All request/response models are Pydantic.

**Step 3: Run test to verify pass**

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: FastAPI REST endpoints for pipeline control"
```

---

## Phase 5: Svelte Frontend

### T14 — Svelte + Tailwind scaffold

**Objective:** Bootable Svelte 5 project with Tailwind, wired to DESIGN.md tokens.

**Files:**
- Create: `frontend/` (Svelte 5 + Vite + Tailwind 4 scaffold)
- Create: `frontend/src/lib/design.ts` (design tokens from DESIGN.md)

**Step 1: Scaffold**

```bash
cd frontend && npx sv create . --template minimal --types ts
npm install -D tailwindcss @tailwindcss/vite
```

**Step 2: Convert DESIGN.md to Tailwind theme**

Run: `npx @google/design.md export --format tailwind DESIGN.md > frontend/src/lib/tailwind.theme.json`

**Step 3: Create base layout** — dark sidebar, main content area per DESIGN.md

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: Svelte 5 + Tailwind scaffold with design tokens"
```

---

### T15 — Pipeline status view

**Objective:** Main dashboard showing pipeline progress — file counts by state, current batch, recent activity.

**Files:**
- Create: `frontend/src/routes/+page.svelte`
- Create: `frontend/src/lib/components/PipelineStatus.svelte`
- Create: `frontend/src/lib/components/StatusPill.svelte`

Pill badges per DESIGN.md (badge-success, badge-warning, badge-error, badge-confidence). Status counts. Dark theme.

**Step 1: Build static layout first** (no API calls)
**Step 2: Wire to GET /api/status**
**Step 3: Commit**

```bash
git add -A && git commit -m "feat: pipeline status dashboard with design tokens"
```

---

### T16 — Review queue view

**Objective:** List low-confidence files. Click to expand, see tags, approve or reject.

**Files:**
- Create: `frontend/src/routes/review/+page.svelte`
- Create: `frontend/src/lib/components/ReviewCard.svelte`
- Create: `frontend/src/lib/components/TagEditor.svelte`

Left-border card per DESIGN.md. Expand to see all tag fields. Edit inline. Approve (writes tags, transfers) or Reject (revert from sidecar).

**Step 1: Build static layout**
**Step 2: Wire to GET /api/review, POST /api/review/{path}/approve, POST /api/review/{path}/reject**
**Step 3: Commit**

```bash
git add -A && git commit -m "feat: review queue with inline tag editing"
```

---

### T17 — Duplicate detection view

**Objective:** Side-by-side file comparison. Highlight higher quality. One-click quarantine.

**Files:**
- Create: `frontend/src/routes/duplicates/+page.svelte`
- Create: `frontend/src/lib/components/DuplicateCard.svelte`

Shows both files, quality badges (bitrate, format, tag completeness), suggested keeper with reason. Confirm button quarantines the lesser file.

**Step 1: Build static layout**
**Step 2: Wire to GET /api/duplicates**
**Step 3: Commit**

---

### T18 — Normalizer preview view

**Objective:** Tree diff showing old path → new path before committing restructuring.

**Files:**
- Create: `frontend/src/routes/normalize/+page.svelte`
- Create: `frontend/src/lib/components/PathDiff.svelte`

Monospace font per DESIGN.md (`mono` typography). Old path in muted text, new path in primary text. Confirm button executes.

**Step 1: Build static layout**
**Step 2: Wire to POST /api/normalize/preview, POST /api/normalize/execute**
**Step 3: Commit**

---

## Phase 6: Integration & Daemon

### T19 — Full integration test

**Objective:** End-to-end test: drop a real audio file into watched dir → it appears as DISCOVERED → runs through pipeline → tags written → available in review or auto-transferred.

**Files:**
- Create: `backend/tests/test_integration.py`

Uses a temp directory, a real tiny MP3 file, mocked LLM router, mocked rsync. Verifies state transitions through the full pipeline.

---

### T20 — Daemon mode (systemd + LaunchAgent)

**Objective:** Run Noctune as a background service that watches and processes automatically.

**Files:**
- Create: `scripts/noctune.service` (Linux systemd)
- Create: `scripts/com.noctune.plist` (macOS LaunchAgent)
- Create: `backend/src/noctune/daemon.py`

**Step 1: Implement daemon.py** — starts watcher + pipeline, runs forever, graceful shutdown on SIGTERM

**Step 2: Create service files**

**Step 3: Commit**

```bash
git add -A && git commit -m "feat: daemon mode with systemd and LaunchAgent support"
```

---

## Phase 7: Genre Vocabulary & Final Polish

### T21 — Curated genre vocabulary

**Objective:** Ship a ~60-genre curated list as the default in config.yaml.

**Files:**
- Modify: `backend/config.example.yaml` (add genre list)

~60 genres from ID3v2 ∩ Navidrome defaults ∩ common sense. Alphabetical. User can edit.

---

### T22 — CLI entry point

**Objective:** `noctune` command to start daemon, run bulk scan, or open web UI.

**Files:**
- Create: `backend/src/noctune/cli.py`
- Modify: `backend/pyproject.toml` (add `[project.scripts]`)

```bash
noctune daemon          # start file watcher + pipeline
noctune scan            # one-shot scan of source_dir
noctune web             # start web UI only
noctune config show     # print loaded config
```

---

## Notes

- Phase 1-3 are pure Python backend — no frontend needed to verify
- Phase 4 (API) makes Phase 5-7 (frontend) possible
- Each task is TDD: write failing test first, then implement
- Config and genre vocabulary are loaded at startup, not fetched remotely
- LLM router is mockable at every level — tests never need a real Ollama connection
- Genre vocabulary growth happens through the review queue: LLM suggests, human approves, config updates