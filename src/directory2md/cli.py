"""Command-line interface for directory2md."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys
import warnings

from tqdm import tqdm

from directory2md.converter import convert_directory

# Suppress noisy pypdf fontTools / malformed PDF warning messages
logging.getLogger("pypdf").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", module="pypdf")


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="directory2md",
        description="Recursively convert a directory to Markdown with matching structure.",
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Source directory containing documents to convert",
    )
    parser.add_argument(
        "destination",
        type=Path,
        help="Destination directory where markdown structure will be generated",
    )
    parser.add_argument(
        "-d",
        "--days",
        type=int,
        default=180,
        help="Age threshold in days to re-convert existing markdown files (default: 180)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force re-conversion of all files regardless of age",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed progress for each file",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress informational output and show only errors",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable interactive progress bar",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", module="pypdf")

    parser = build_parser()
    args = parser.parse_args(argv)

    src_dir: Path = args.source
    dst_dir: Path = args.destination

    if not src_dir.exists():
        print(f"Error: Source directory '{src_dir}' does not exist.", file=sys.stderr)
        return 1

    if not src_dir.is_dir():
        print(f"Error: Source path '{src_dir}' is not a directory.", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"Starting directory2md:")
        print(f"  Source:      {src_dir.resolve()}")
        print(f"  Destination: {dst_dir.resolve()}")
        print(f"  Threshold:   {args.days} days")
        if args.force:
            print("  Mode:        FORCE (refreshing all files)")

    show_progress = (not args.quiet) and (not args.no_progress)
    pbar: tqdm | None = None

    def log_cb(msg: str) -> None:
        if args.verbose and not args.quiet:
            if pbar is not None and show_progress:
                tqdm.write(f"  • {msg}")
            else:
                print(f"  • {msg}")

    def progress_cb(current: int, total: int, filename: str) -> None:
        nonlocal pbar
        if not show_progress or total == 0:
            return
        if pbar is None:
            pbar = tqdm(
                total=total,
                desc="Converting files",
                unit="file",
                file=sys.stdout,
                disable=True if (args.quiet or args.no_progress) else None,
                leave=True,
            )
        display_name = Path(filename).name
        if len(display_name) > 35:
            display_name = display_name[:32] + "..."
        pbar.set_postfix_str(display_name)
        if current > pbar.n:
            pbar.update(current - pbar.n)

    try:
        stats = convert_directory(
            src_dir=src_dir,
            dst_dir=dst_dir,
            max_age_days=args.days,
            force=args.force,
            verbose=args.verbose,
            log_callback=log_cb,
            progress_callback=progress_cb,
        )

        if pbar is not None:
            pbar.close()

        if not args.quiet:
            print("\nConversion finished:")
            print(f"  Total scanned:   {stats.total_scanned}")
            print(f"  Files converted: {stats.converted}")
            print(f"  Files skipped:   {stats.skipped}")
            if stats.has_errors:
                print(f"  Errors encountered: {len(stats.errors)}", file=sys.stderr)
                for path, err in stats.errors:
                    print(f"    - {path}: {err}", file=sys.stderr)

        return 1 if stats.has_errors else 0

    except Exception as exc:
        if pbar is not None:
            pbar.close()
        print(f"Fatal error during conversion: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
