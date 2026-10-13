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
        "-f",
        "--force",
        nargs="?",
        const=True,
        default=False,
        metavar="TARGET",
        help="Force re-conversion of all files, or a specific file or directory (recursively)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed progress for each file and initial configuration",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    from directory2md.config import create_default_config_file, load_config

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

    src_resolved = src_dir.resolve()
    dst_resolved = dst_dir.resolve()
    if dst_resolved == src_resolved or dst_resolved.is_relative_to(src_resolved):
        print(
            f"Error: Destination directory '{dst_dir}' cannot be inside or the same as source directory '{src_dir}'.",
            file=sys.stderr,
        )
        return 1

    # Configuration file in destination directory: create on first run and prompt edit
    config_file: Path = dst_dir / "directory2md.yaml"
    if not config_file.exists():
        create_default_config_file(config_file)
        print("Se ha creado el archivo de configuración en:")
        print(f"  {config_file.resolve()}\n")
        print("Por favor, revisa y edita este archivo para configurar tus modelos de IA u otras opciones,")
        print("y vuelve a ejecutar directory2md.")
        return 0

    config = load_config(config_file)
    days = config.days
    force = args.force if args.force else config.force
    verbose = args.verbose or config.verbose

    if verbose:
        print(f"Starting directory2md:")
        print(f"  Source:      {src_dir.resolve()}")
        print(f"  Destination: {dst_dir.resolve()}")
        print(f"  Config:      {config_file.resolve()}")
        print(f"  Threshold:   {days} days")
        if force is True:
            print("  Mode:        FORCE (refreshing all files)")
        elif force:
            print(f"  Mode:        FORCE (target: '{force}')")
        if config.ai.enabled:
            print(f"  AI (Ollama): ENABLED (Vision: '{config.ai.vision_model or 'none'}', Audio: '{config.ai.audio_model or 'none'}')")

    pbar: tqdm | None = None

    def log_cb(msg: str) -> None:
        if verbose:
            if pbar is not None:
                tqdm.write(f"  • {msg}")
            else:
                print(f"  • {msg}")

    def progress_cb(current: int, total: int, filename: str) -> None:
        nonlocal pbar
        if total == 0:
            return
        if pbar is None:
            pbar = tqdm(
                total=total,
                desc="Converting files",
                unit="file",
                file=sys.stdout,
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
            max_age_days=days,
            force=force,
            verbose=verbose,
            log_callback=log_cb,
            progress_callback=progress_cb,
            config=config,
        )

        if pbar is not None:
            pbar.close()

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
