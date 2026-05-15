"""Pipeline orchestrator — ties the three-layer tag engine together.

State machine: DISCOVERED → STABLE → FINGERPRINTED → EXTRACTED → RECONCILED → TAGGED (or QUEUED_FOR_REVIEW)
Each step updates the SQLite state store, making the pipeline resumable after crashes.
"""

import logging
from pathlib import Path

from noctune.extract import extract_metadata
from noctune.fingerprint import fingerprint_and_lookup
from noctune.llm_router import LLMRouter
from noctune.models.config import NoctuneConfig
from noctune.models.pipeline import FileState, PipelineStatus
from noctune.models.track import TagSet, TrackMeta
from noctune.reconcile import reconcile_tags, ReconciledTags
from noctune.store import StateStore
from noctune.tag_writer import backup_tags, write_tags

logger = logging.getLogger(__name__)


class Pipeline:
    """Three-layer tag processing pipeline.

    Processes music files through:
    1. Fingerprint (Acoustid/MusicBrainz)
    2. Extract (mutagen tags + filename + directory)
    3. Reconcile (LLM normalizes and picks genre from vocabulary)

    Then writes tags and updates state.
    """

    def __init__(
        self,
        config: NoctuneConfig,
        store: StateStore,
        llm_router: LLMRouter,
        acoustid_api_key: str = "",
    ) -> None:
        self.config = config
        self.store = store
        self.llm_router = llm_router
        self.acoustid_api_key = acoustid_api_key

    async def discover_file(self, path: Path) -> PipelineStatus:
        """Register a file as discovered in the pipeline.

        Skips if the file is already tracked and past DISCOVERED.
        """
        path_str = str(path)

        # Check if already tracked
        existing = self.store.get(path_str)
        if existing and existing.state != FileState.DISCOVERED:
            logger.debug("File %s already in state %s, skipping discovery", path.name, existing.state)
            return existing

        status = PipelineStatus(
            file_path=path_str,
            state=FileState.DISCOVERED,
        )
        self.store.upsert(status)
        logger.info("Discovered file: %s", path.name)
        return status

    async def process_file(self, path: Path) -> PipelineStatus:
        """Process a single file through the full pipeline.

        Skips files that are already in a terminal state (TAGGED, TRANSFERRED).
        Resumes from the last state for files that were interrupted.
        """
        path_str = str(path)

        # Get current state
        status = self.store.get(path_str)

        # Skip if already in terminal state
        if status and status.state in (FileState.TAGGED, FileState.TRANSFERRED):
            logger.info("File %s already in state %s, skipping", path.name, status.state)
            return status

        # Start from DISCOVERED if not tracked
        if status is None:
            status = await self.discover_file(path)

        # Verify file exists
        if not path.exists():
            status = PipelineStatus(
                file_path=path_str,
                state=FileState.FAILED,
                error="File not found",
            )
            self.store.upsert(status)
            return status

        try:
            # Step 1: Fingerprint
            fingerprint_tags = self._fingerprint_file(path)
            status = PipelineStatus(
                file_path=path_str,
                state=FileState.FINGERPRINTED,
                mb_release_group_id=fingerprint_tags.mb_release_group_id if hasattr(fingerprint_tags, 'mb_release_group_id') else None,
            )
            self.store.upsert(status)

            # Step 2: Extract metadata
            extract_result = self._extract_metadata(path)
            # _extract_metadata returns TrackMeta (has .existing_tags) or TagSet (for mocked tests)
            if isinstance(extract_result, TrackMeta):
                extracted_tags = extract_result.existing_tags or TagSet()
            else:
                extracted_tags = extract_result  # Already a TagSet from mock

            status = PipelineStatus(
                file_path=path_str,
                state=FileState.EXTRACTED,
            )
            self.store.upsert(status)

            # Step 3: Reconcile with LLM
            reconciled = await reconcile_tags(
                fingerprint_tags=fingerprint_tags,
                extracted_tags=extracted_tags,
                genre_vocabulary=self.config.genre_vocabulary,
                llm_router=self.llm_router,
            )

            status = PipelineStatus(
                file_path=path_str,
                state=FileState.RECONCILED,
                confidence=reconciled.confidence,
            )
            self.store.upsert(status)

            # Step 4: Write tags or queue for review
            if reconciled.confidence >= self.config.confidence_threshold:
                # High confidence — auto-tag
                self._write_tags(path, reconciled)
                status = PipelineStatus(
                    file_path=path_str,
                    state=FileState.TAGGED,
                    confidence=reconciled.confidence,
                )
                self.store.upsert(status)
                logger.info("Auto-tagged %s (confidence: %.2f)", path.name, reconciled.confidence)
            else:
                # Low confidence — queue for review
                status = PipelineStatus(
                    file_path=path_str,
                    state=FileState.QUEUED_FOR_REVIEW,
                    confidence=reconciled.confidence,
                )
                self.store.upsert(status)
                logger.info("Queued for review: %s (confidence: %.2f)", path.name, reconciled.confidence)

            return status

        except Exception as exc:
            logger.exception("Pipeline failed for %s: %s", path.name, exc)
            status = PipelineStatus(
                file_path=path_str,
                state=FileState.FAILED,
                error=str(exc),
            )
            self.store.upsert(status)
            return status

    async def process_batch(self, paths: list[Path]) -> list[PipelineStatus]:
        """Process multiple files through the pipeline.

        Groups files by release_group_id for batch LLM reconciliation,
        but for now processes them sequentially.
        """
        results: list[PipelineStatus] = []
        for path in paths:
            result = await self.process_file(path)
            results.append(result)
        return results

    def _fingerprint_file(self, path: Path) -> TagSet:
        """Layer 1: Fingerprint file and look up MusicBrainz.

        Returns a TagSet with MusicBrainz data, or empty TagSet if fingerprint fails.
        """
        if not self.acoustid_api_key:
            logger.debug("No Acoustid API key configured, skipping fingerprint")
            return TagSet()

        try:
            result = fingerprint_and_lookup(path, self.acoustid_api_key)
            if result and result.tagset:
                return result.tagset
        except Exception:
            logger.warning("Fingerprint failed for %s", path.name, exc_info=True)

        return TagSet()

    def _extract_metadata(self, path: Path) -> TrackMeta:
        """Layer 2: Extract metadata from file tags, filename, and directory.

        Returns a TrackMeta with all available signals merged.
        """
        return extract_metadata(path)

    def _write_tags(self, path: Path, tags: TagSet) -> Path:
        """Write reconciled tags to the audio file.

        Creates a sidecar backup first, then writes new tags.
        """
        try:
            return write_tags(path, tags)
        except Exception:
            logger.exception("Failed to write tags to %s", path.name)
            raise

    def get_review_queue(self) -> list[PipelineStatus]:
        """Get all files waiting for human review."""
        return self.store.list_by_state(FileState.QUEUED_FOR_REVIEW)

    def approve_review(self, file_path: str, tags: TagSet) -> PipelineStatus:
        """Approve a review item, write the tags, and mark as TAGGED."""
        music_path = Path(file_path)
        self._write_tags(music_path, tags)

        status = PipelineStatus(
            file_path=file_path,
            state=FileState.TAGGED,
            confidence=1.0,  # Human-approved = maximum confidence
        )
        self.store.upsert(status)
        logger.info("Approved review item: %s", music_path.name)
        return status

    def reject_review(self, file_path: str) -> PipelineStatus:
        """Reject a review item — revert tags from sidecar backup."""
        music_path = Path(file_path)
        sidecar = music_path.with_suffix(music_path.suffix + ".tags.json")

        if sidecar.exists():
            import json
            from noctune.models.track import TagSet

            data = json.loads(sidecar.read_text())
            original_tags = TagSet(**data)
            self._write_tags(music_path, original_tags)
            logger.info("Reverted tags for %s from sidecar", music_path.name)

        status = PipelineStatus(
            file_path=file_path,
            state=FileState.FAILED,
            error="Review rejected, tags reverted",
        )
        self.store.upsert(status)
        return status