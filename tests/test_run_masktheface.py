"""Tests for run_masktheface.py's guard clause and command construction."""

import pytest

from datasets.masking.scripts import run_masktheface


def test_run_exits_clearly_when_subset_dir_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(run_masktheface, "SUBSET_DIR", str(tmp_path / "does_not_exist"))
    with pytest.raises(SystemExit, match="run select_subset.py first"):
        run_masktheface.run()


def test_run_passes_empty_color_to_override_masktheface_s_default_blue_tint(monkeypatch, tmp_path):
    monkeypatch.setattr(run_masktheface, "SUBSET_DIR", str(tmp_path))
    captured = {}
    monkeypatch.setattr(run_masktheface.subprocess, "run",
                         lambda cmd, cwd, check: captured.update(cmd=cmd))

    run_masktheface.run()

    color_index = captured["cmd"].index("--color")
    assert captured["cmd"][color_index + 1] == ""
