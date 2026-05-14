"""Pipeline state models."""

from enum import StrEnum

from pydantic import BaseModel


class FileState(StrEnum):
    """States a file can be in during the pipeline."""

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
    """Current status of a file in the pipeline."""

    file_path: str
    state: FileState = FileState.DISCOVERED
    confidence: float = 0.0
    mb_release_group_id: str | None = None
    error: str | None = None