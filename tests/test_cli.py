"""Tests for CLI interface."""

from pathlib import Path
import pytest

from directory2md.cli import main


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "directory2md" in captured.out


def test_cli_execution(tmp_path: Path, capsys):
    src = tmp_path / "src_dir"
    dst = tmp_path / "dst_dir"
    src.mkdir()

    f = src / "test.txt"
    f.write_text("Command line test")

    code = main([str(src), str(dst), "--verbose"])
    assert code == 0

    captured = capsys.readouterr()
    assert "Starting directory2md:" in captured.out
    assert "Conversion finished:" in captured.out
    assert (dst / "test.txt.md").exists()


def test_cli_nonexistent_source(tmp_path: Path, capsys):
    src = tmp_path / "nonexistent"
    dst = tmp_path / "dst"

    code = main([str(src), str(dst)])
    assert code == 1
    captured = capsys.readouterr()
    assert "Error: Source directory" in captured.err
