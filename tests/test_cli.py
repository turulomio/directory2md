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

    # First run: creates config file and prompts user to edit
    code1 = main([str(src), str(dst), "--verbose"])
    assert code1 == 0
    captured1 = capsys.readouterr()
    assert "Se ha creado el archivo de configuración en:" in captured1.out
    assert (dst / "directory2md.yaml").exists()

    # Second run: config exists, executes conversion
    code2 = main([str(src), str(dst), "--verbose"])
    assert code2 == 0
    captured2 = capsys.readouterr()
    assert "Starting directory2md:" in captured2.out
    assert "Conversion finished:" in captured2.out
    assert (dst / "test.txt.md").exists()


def test_cli_nonexistent_source(tmp_path: Path, capsys):
    src = tmp_path / "nonexistent"
    dst = tmp_path / "dst"

    code = main([str(src), str(dst)])
    assert code == 1
    captured = capsys.readouterr()
    assert "Error: Source directory" in captured.err


def test_cli_default_quiet_and_summary(tmp_path: Path, capsys):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "test.txt").write_text("sample")

    # First run to initialize config
    main([str(src), str(dst)])
    capsys.readouterr()

    # Second run without --verbose: quiet by default (no Starting directory2md header)
    code = main([str(src), str(dst)])
    assert code == 0
    captured = capsys.readouterr()
    assert "Starting directory2md:" not in captured.out
    assert "Conversion finished:" in captured.out
    assert (dst / "test.txt.md").exists()


def test_cli_destination_inside_source(tmp_path: Path, capsys):
    src = tmp_path / "source"
    src.mkdir()
    dst_inside = src / "output"

    code = main([str(src), str(dst_inside)])
    assert code == 1
    captured = capsys.readouterr()
    assert "Error: Destination directory" in captured.err
    assert "cannot be inside or the same as source directory" in captured.err


def test_cli_force_targeted(tmp_path: Path, capsys):
    src = tmp_path / "source"
    dst = tmp_path / "dest"
    src.mkdir()
    (src / "other.txt").write_text("other")
    sub = src / "subfolder"
    sub.mkdir()
    (sub / "doc.txt").write_text("doc")

    # First run creates config
    main([str(src), str(dst)])
    capsys.readouterr()

    # Second run with --force subfolder and --verbose
    code = main([str(src), str(dst), "--force", "subfolder", "--verbose"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Mode:        FORCE (target: 'subfolder')" in captured.out
    assert (dst / "subfolder" / "doc.txt.md").exists()
    assert not (dst / "other.txt.md").exists()


def test_cli_updates_old_config_keys(tmp_path: Path, capsys):
    src = tmp_path / "source"
    dst = tmp_path / "dest"
    src.mkdir()
    dst.mkdir()
    (src / "doc.txt").write_text("content")

    # Manually write an old config file missing ai and verbose keys
    (dst / "directory2md.yaml").write_text("days: 120\nforce: false\n", encoding="utf-8")

    code = main([str(src), str(dst), "--verbose"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Updated keys:" in captured.out
    assert "ai.language" in captured.out

    # Config file should now contain the missing keys
    config_content = (dst / "directory2md.yaml").read_text(encoding="utf-8")
    assert "days: 120" in config_content
    assert "language: \"es\"" in config_content




