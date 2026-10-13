"""Tests for file and directory exclusion mechanisms in directory2md."""

from pathlib import Path
import pytest

from directory2md.cli import main
from directory2md.config import Config, load_config, update_missing_config_keys
from directory2md.converter import convert_directory, should_exclude


def test_should_exclude_basic_names():
    # Empty pattern list
    assert not should_exclude("file.txt", Path("file.txt"), is_dir=False, exclude_patterns=[])

    patterns = [".git", "node_modules", "secret.txt", "*.tmp"]

    # Exact directory name matches
    assert should_exclude(".git", Path(".git"), is_dir=True, exclude_patterns=patterns)
    assert should_exclude("node_modules", Path("sub/node_modules"), is_dir=True, exclude_patterns=patterns)

    # Exact file name match
    assert should_exclude("secret.txt", Path("secret.txt"), is_dir=False, exclude_patterns=patterns)
    assert should_exclude("secret.txt", Path("docs/secret.txt"), is_dir=False, exclude_patterns=patterns)

    # Glob wildcard extension
    assert should_exclude("test.tmp", Path("test.tmp"), is_dir=False, exclude_patterns=patterns)
    assert should_exclude("other.tmp", Path("nested/deep/other.tmp"), is_dir=False, exclude_patterns=patterns)

    # Non-matching
    assert not should_exclude("normal.txt", Path("normal.txt"), is_dir=False, exclude_patterns=patterns)
    assert not should_exclude("src", Path("src"), is_dir=True, exclude_patterns=patterns)


def test_should_exclude_directory_indicator_slash():
    patterns = ["cache/", "build/"]

    # Should match directory
    assert should_exclude("cache", Path("cache"), is_dir=True, exclude_patterns=patterns)
    assert should_exclude("cache", Path("sub/cache"), is_dir=True, exclude_patterns=patterns)

    # Should NOT match file with same name
    assert not should_exclude("cache", Path("cache"), is_dir=False, exclude_patterns=patterns)
    assert not should_exclude("build", Path("sub/build"), is_dir=False, exclude_patterns=patterns)


def test_should_exclude_rooted_paths():
    patterns = ["/build", "./vendor"]

    # Rooted matches at root
    assert should_exclude("build", Path("build"), is_dir=True, exclude_patterns=patterns)
    assert should_exclude("vendor", Path("vendor"), is_dir=True, exclude_patterns=patterns)

    # Does NOT match in subdirectories because it is anchored to root
    assert not should_exclude("build", Path("sub/build"), is_dir=True, exclude_patterns=patterns)
    assert not should_exclude("vendor", Path("packages/vendor"), is_dir=True, exclude_patterns=patterns)


def test_should_exclude_relative_paths():
    patterns = ["docs/internal", "assets/*.png"]

    assert should_exclude("internal", Path("docs/internal"), is_dir=True, exclude_patterns=patterns)
    assert should_exclude("pic.png", Path("assets/pic.png"), is_dir=False, exclude_patterns=patterns)

    # Should not match other directories
    assert not should_exclude("internal", Path("other/internal"), is_dir=True, exclude_patterns=patterns)
    assert not should_exclude("pic.png", Path("other/pic.png"), is_dir=False, exclude_patterns=patterns)


def test_config_load_and_update_exclude(tmp_path: Path):
    cfg_file = tmp_path / "directory2md.yaml"

    # YAML with list of excludes
    cfg_file.write_text(
        "days: 90\nforce: true\nverbose: true\nexclude:\n  - '.git'\n  - 'node_modules'\n  - '*.log'\n",
        encoding="utf-8",
    )
    config = load_config(cfg_file)
    assert config.exclude == [".git", "node_modules", "*.log"]
    assert config.days == 90
    assert config.force is True
    assert config.verbose is True

    # YAML with missing exclude key gets updated automatically
    old_cfg_file = tmp_path / "old.yaml"
    old_cfg_file.write_text("days: 100\nforce: false\nverbose: false\n", encoding="utf-8")
    added = update_missing_config_keys(old_cfg_file)
    assert "exclude" in added
    content = old_cfg_file.read_text(encoding="utf-8")
    assert "exclude: []" in content


def test_convert_directory_excludes_files_and_directories(tmp_path: Path):
    src = tmp_path / "source"
    dst = tmp_path / "dest"
    src.mkdir()

    # Normal file
    (src / "document.txt").write_text("Normal document")

    # Excluded file by extension
    (src / "debug.log").write_text("Log info")

    # Excluded file by exact name
    (src / "passwords.txt").write_text("Secret")

    # Excluded directory
    node_modules = src / "node_modules"
    node_modules.mkdir()
    (node_modules / "pkg.txt").write_text("Module file")
    (node_modules / "sub").mkdir()
    (node_modules / "sub" / "deep.txt").write_text("Deep module file")

    # Regular subfolder with an excluded file inside
    docs = src / "docs"
    docs.mkdir()
    (docs / "guide.txt").write_text("User guide")
    (docs / "temp.log").write_text("Temp log")

    config = Config(exclude=["node_modules", "*.log", "passwords.txt"])
    stats = convert_directory(src, dst, config=config, verbose=True)

    # Checked processed files: document.txt, docs/guide.txt
    assert stats.converted == 2
    assert stats.excluded > 0

    # Normal destination files exist
    assert (dst / "document.txt.directory2md.md").exists()
    assert (dst / "docs" / "guide.txt.directory2md.md").exists()

    # Excluded files must NOT exist
    assert not (dst / "debug.log.directory2md.md").exists()
    assert not (dst / "passwords.txt.directory2md.md").exists()
    assert not (dst / "docs" / "temp.log.directory2md.md").exists()

    # Excluded directory must NOT exist in destination
    assert not (dst / "node_modules").exists()


def test_cli_exclude_via_config(tmp_path: Path, capsys):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()

    (src / "included.txt").write_text("Included")
    (src / "excluded.txt").write_text("Excluded")
    (src / "test.tmp").write_text("Temporary")

    # Run 1: initializes config
    main([str(src), str(dst)])
    capsys.readouterr()

    # Configure exclude list in destination directory2md.yaml
    cfg_file = dst / "directory2md.yaml"
    cfg_file.write_text("exclude:\n  - 'excluded.txt'\n  - '*.tmp'\n", encoding="utf-8")

    # Run 2: executes conversion using configuration file
    code = main([str(src), str(dst), "--verbose"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Exclude:     excluded.txt, *.tmp" in captured.out
    assert "Excluded:" in captured.out

    assert (dst / "included.txt.directory2md.md").exists()
    assert not (dst / "excluded.txt.directory2md.md").exists()
    assert not (dst / "test.tmp.directory2md.md").exists()
