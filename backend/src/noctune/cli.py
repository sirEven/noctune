"""Noctune CLI — command-line interface for the music library manager.

Usage:
    noctune daemon    Start the daemon + web server (default)
    noctune web       Start only the web UI server
    noctune scan      Scan source directory and register discovered files
    noctune status    Show pipeline status overview
    noctune genres    List the genre vocabulary
"""

import argparse
import logging
import sys
from pathlib import Path

from noctune.genres import GENRE_VOCABULARY


logger = logging.getLogger(__name__)


def cmd_daemon(args: argparse.Namespace) -> None:
    """Start the daemon + web server."""
    import uvicorn
    from noctune.main import create_app

    app = create_app(config_path=Path(args.config))
    logger.info("Starting Noctune daemon on %s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port)


def cmd_web(args: argparse.Namespace) -> None:
    """Start only the web UI server (no daemon auto-start)."""
    import uvicorn
    from noctune.main import create_app

    app = create_app(config_path=Path(args.config))
    logger.info("Starting Noctune web UI on %s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port)


def cmd_scan(args: argparse.Namespace) -> None:
    """Scan source directory and register discovered files."""
    from noctune.config_loader import load_config
    from noctune.store import StateStore
    from noctune.models.pipeline import FileState, PipelineStatus

    config = load_config(Path(args.config))
    store = StateStore(config.source_dir / ".noctune" / "state.db")
    store.initialize()

    source = config.source_dir
    if not source.exists():
        print(f"Source directory does not exist: {source}")
        sys.exit(1)

    discovered = 0
    skipped = 0
    for ext in config.valid_extensions:
        for path in source.rglob(f"*{ext}"):
            if path.is_file():
                existing = store.get(str(path))
                if existing and existing.state != FileState.DISCOVERED:
                    skipped += 1
                    continue
                store.upsert(PipelineStatus(
                    file_path=str(path),
                    state=FileState.DISCOVERED,
                ))
                discovered += 1
                if args.verbose:
                    print(f"  Discovered: {path.relative_to(source)}")

    print(f"Scan complete: {discovered} files discovered, {skipped} skipped (already tracked)")
    if not args.quiet and discovered > 0:
        print(f"Start the daemon to process: noctune daemon --config {args.config}")


def cmd_status(args: argparse.Namespace) -> None:
    """Show pipeline status overview."""
    from noctune.config_loader import load_config
    from noctune.store import StateStore
    from noctune.models.pipeline import FileState

    config = load_config(Path(args.config))
    db_path = config.source_dir / ".noctune" / "state.db"
    if not db_path.exists():
        print("No state database found. Run 'noctune scan' first.")
        sys.exit(1)

    store = StateStore(db_path)
    store.initialize()

    states = [
        (FileState.DISCOVERED, "Discovered"),
        (FileState.STABLE, "Stable"),
        (FileState.FINGERPRINTED, "Fingerprinted"),
        (FileState.EXTRACTED, "Extracted"),
        (FileState.RECONCILED, "Reconciled"),
        (FileState.QUEUED_FOR_REVIEW, "Review Queue"),
        (FileState.TAGGED, "Tagged"),
        (FileState.TRANSFERRED, "Transferred"),
        (FileState.FAILED, "Failed"),
    ]

    total = 0
    print("Noctune Pipeline Status")
    print("=" * 40)
    for state, label in states:
        count = len(store.list_by_state(state))
        total += count
        if count > 0:
            print(f"  {label:20s} {count:>5}")
    print("-" * 40)
    print(f"  {'Total':20s} {total:>5}")


def cmd_genres(args: argparse.Namespace) -> None:
    """List the genre vocabulary."""
    print(f"Noctune Genre Vocabulary ({len(GENRE_VOCABULARY)} genres)")
    print("=" * 45)
    for genre in GENRE_VOCABULARY:
        print(f"  {genre}")


def main() -> None:
    """Entry point for the noctune CLI."""
    parser = argparse.ArgumentParser(
        prog="noctune",
        description="Noctune — Music library manager and tag reconciler",
    )
    parser.add_argument(
        "--config", "-c",
        default="~/.noctune/config.yaml",
        help="Path to config file (default: ~/.noctune/config.yaml)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Quiet output (minimal)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # daemon
    daemon_parser = subparsers.add_parser("daemon", help="Start daemon + web server")
    daemon_parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    daemon_parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")

    # web
    web_parser = subparsers.add_parser("web", help="Start web UI only (no daemon)")
    web_parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    web_parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")

    # scan
    subparsers.add_parser("scan", help="Scan source directory for music files")

    # status
    subparsers.add_parser("status", help="Show pipeline status overview")

    # genres
    subparsers.add_parser("genres", help="List the genre vocabulary")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.WARNING if args.quiet else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    if args.command == "daemon":
        cmd_daemon(args)
    elif args.command == "web":
        cmd_web(args)
    elif args.command == "scan":
        cmd_scan(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "genres":
        cmd_genres(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()