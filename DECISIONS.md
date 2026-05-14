---
stage: inbox
status: researching
created: 2026-05-14
---

# Music Sync — Decisions

Resolved answers to the open questions.

---

## Q1. LLM — Local Ollama on Framework laptop (September)

Intel Core Ultra 7 + 32GB RAM is sufficient. Not real-time chat — batch reconciliation.
- Llama 3 8B / Mistral 7B in Ollama: ~5-10 seconds per batch of 20 tracks
- 10k files = ~500 calls = ~90 minutes total LLM time (background job)
- Intel NPU + oneAPI support in Ollama for acceleration
- Until September: API fallback for LLM calls (Claude/GPT)
- v2.0: optional Ollama cloud API with free tier

**Decision: Local LLM on most powerful machine, API as fallback.**

---

## Q2. Genre vocabulary — Curated, growthrough approval

~60 core genres from ID3v2 ∩ Navidrome defaults ∩ common sense. LLM can only pick from this list.
- Can't map → flags file for review with suggested new genre
- User approves/rejects suggested additions
- Approved additions go into config YAML
- List grows organically but every addition flows through human approval

**Decision: Curated core, human-gated growth.**

---

## Q3. Fixing botched files after transfer

Tag backup sidecar before every write. "Recently transferred" view in UI.
- Spot a botched file → click → re-process with corrected info → re-tag → re-sync
- Full revert: restore original tags from sidecar
- No need to use Navidrome's UI for corrections

**Decision: Tool is the single surface for tagging + sync + correction.**

---

## Q4. Duplicate handling — Flag with suggestion, quarantine on delete

Show both files side by side. Highlight higher quality (bitrate, format, tag completeness, file size). Suggest which to keep with reason.
- One-click confirm to remove the lesser duplicate
- Removed files go to quarantine folder (not truly deleted, reversible)
- Clean, intuitive UI — this is the differentiator

**Decision: Flag + suggest + quarantine. Never auto-delete.**

---

## Q5. Cover art — Auto-download + embed, flag missing for review

MusicBrainz Cover Art Archive for auto-download. Embed in tags (one source of truth).
- High confidence cover match: auto-embed
- Low/no match: flag in review queue
- Existing cover art: preserve unless explicitly replacing

**Decision: Auto-download with confidence scoring, flag uncertain.**

---

## Q6. Bulk initial sync — Background job, runs overnight

MusicBrainz API rate limit: ~1 req/sec. 10k files = ~3 hours for fingerprint lookups.
- This is a background batch job, not interactive
- Start it, check results in the morning
- Progress bar in UI
- Resumable: state file tracks what's been processed

**Decision: Long-running background job with progress tracking. Resumable.**

---

## Q7. File stability — Debounce timer, not polling

Current script polls file size 3 times. Better: debounce timer on watchdog events.
- Any event on a file → start/reset a timer
- Timer expires (5 seconds of no events) → file is stable, process it
- Configurable debounce duration
- No polling, no size checking, cross-platform, works with watchdog events

**Decision: Event-driven debounce. Configurable timeout. No size polling.**

---

## Q8. Library normalizer — Restructure messy folder hierarchy

Decades of iTunes/Apple mess = nested chaos. The normalizer:
- Runs AFTER tagging (tags drive structure, not the other way around)
- Derives clean folder/filename from normalized tags
- Target structure: `Artist/Album (Year)/01 - Track.flac`
- Preview before executing (show old path → new path)
- Source folder untouched until user confirms
- Optional: remove empty directories after reorganization

**Decision: Tags-first restructuring. Preview before commit. Source stays intact until confirmed.**

---

## Q9. Engine runs on most powerful machine

Configurable — any machine with Python + chromaprint + Ollama can run it.
- In practice: the machine with best hardware runs the LLM
- Until Framework laptop (September): API fallback
- v2.0: cloud Ollama option

**Decision: Portable, but LLM prefers powerful hardware.**

---

## Q10. Undo/rollback — Tag backup sidecar

Before any tag write, save original tags to a sidecar file (`.json` alongside the audio file).
- "Revert this album" = read sidecar, restore original tags
- Sidecars stored in the source directory, named `<filename>.tags.json`
- Optional cleanup: after N days or after verified, delete sidecars

**Decision: Sidecar-based tag backup. One-click revert.**

---

## Q11. Config — YAML with hardcoded genre vocabulary

Genre vocabulary starts in the config file. User can edit it. No dynamic fetching from Navidrome (can add a command later).

**Decision: YAML config. Genre vocabulary in config, editable, not fetched.**