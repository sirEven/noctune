---
stage: inbox
status: idea
created: 2026-05-14
---

# Noctune

Music library manager, tag reconciler, and sync tool for Navidrome.

## Problem

- Navidrome has no native metadata editing — tagging must be done externally
- Existing tag editors are clumsy (Picard, Kid3, etc.)
- Current `file-transfer` script is hardcoded, macOS-only, no bulk sync
- Music sits on source machines, needs to land on Pi `/data/music`

## Scope

### Core: File Watcher + Sync
- Watch source directory (any OS)
- Detect new/changed music files
- Sync to remote destination via rsync (not SCP)
- Initial bulk sync capability
- Move processed files to `transferred/`
- Run as daemon (macOS LaunchAgent, Linux systemd)

### Web Dashboard
- Live status: what's being watched, what's syncing, history
- Lightweight — embedded web server (e.g., FastAPI + HTMX)

### Metadata Editor
- Read/write ID3v2, Vorbis, FLAC tags
- Batch editing: select multiple files, set fields at once
- Auto-tag from filename patterns
- Cover art management (extract, embed, download from MusicBrainz)
- Navidrome integration — trigger rescan after tag edits

## Tech Stack & Rules

- **Language**: Python 3.12+
- **Tag library**: mutagen (ID3v2.3/v2.4, Vorbis, FLAC, MP4, APE)
- **File watching**: watchdog
- **Web**: Svelte + Tailwind, FastAPI backend
- **UI principle**: desktop-only tool, no mobile
- **Models**: Pydantic v2 — all data models validated, no raw dicts
- **Transfer**: rsync (not SCP)
- **Config**: single YAML file
- **Daemon**: macOS LaunchAgent + Linux systemd

### Non-negotiable coding rules
- **Fully typed** — every function signature, enforced by ruff + pylance
- **TDD** — red, green, refactor. One test at a time.
- **SOLID** — single responsibility, dependency injection, no god classes
- **No runtime surprises** — if pylance can't type-check it, rewrite it

## Architecture

### Tag Engine — Three-Layer Pipeline

**Layer 1 — Fingerprint & Identify (zero hallucination)**
- Acoustid (chromaprint) generates audio fingerprint per file
- Lookup against MusicBrainz database → canonical tags
- Handles 80-90% of library automatically
- No LLM involved — database ground truth

**Layer 2 — Metadata Extraction (signal gathering)**
- Parse existing tags (mutagen) — however broken
- Parse filename patterns (`01 - Radiohead - Kid A.mp3`)
- Parse directory structure (`Music/Radiohead/Kid A/...`)
- Extract cover art if present

**Layer 3 — LLM Reconciliation (conflict resolution)**
- Fed all signals from Layer 1 + 2
- Resolves: artist name variants → canonical form
- Resolves: genre sprawl → controlled vocabulary
- Resolves: missing fields → infer from context
- Resolves: conflicting years, spellings, feat. variants
- Produces single normalized tag set with confidence score

### Review Queue
- High confidence → auto-transfer to Pi
- Low confidence → park for human glance (2 min, not 2 hours)
- Minimal UI: list of uncertain files, confirm or correct in batch

### Sync Flow
```
drop files into watched folder
  → fingerprint batch (background)
  → collect metadata signals
  → LLM reconciles → normalized tags
  → mutagen writes tags in-place on source machine
  → confidence score per file
  → high confidence: auto-transfer via rsync
  → low confidence: review queue → human confirms → transfer
```

### Key Decisions
- Tags fixed BEFORE transfer — nothing hits Pi dirty
- Tag engine runs on source machine (laptop), not Pi
- No extra UI on Pi, no touching Navidrome code
- Initial bulk (60GB) and ongoing trickle use the same pipeline

### LLM Routing

Configurable direction layer — route LLM calls to local or cloud:
- **Local**: Ollama on the same machine (default for when Framework laptop is available)
- **Cloud**: Ollama Cloud API with key (fallback until September, or for burst capacity)
- **Any OpenAI-compatible endpoint**: same interface, different base URL

```yaml
llm:
  direction: local  # "local" or "cloud"
  local:
    base_url: http://localhost:11434
    model: llama3:8b
  cloud:
    base_url: https://api.ollama.com/v1  # or any OpenAI-compatible endpoint
    api_key: ${OLLAMA_API_KEY}
    model: llama3:70b
  fallback: cloud  # if local fails, route to cloud
  batch_size: 20
```

Same prompt schema goes in, same Pydantic-validated response comes out. The routing layer is transparent to the reconciliation pipeline.

### Transfer
- rsync to Pi (not SCP)
- Pluggable backends (rsync, cp)
- Watched folder triggers pipeline automatically
- Single YAML config

## Related

- [[Open Questions]] — unresolved design questions
- [[Decisions]] — resolved decisions with rationale
- [[Juke Pi]] — the Navidrome Pi setup
- `file-transfer` repo — the existing script to replace