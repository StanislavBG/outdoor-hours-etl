import subprocess

import pytest

import scripts._claude as claude_mod
from scripts import gen_monthly_summaries, gen_range_overview, gen_region_profiles


class _R:
    def __init__(self, rc=0, out="ok\n", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_run_claude_pins_model(monkeypatch):
    seen = {}

    def fake(argv, **kw):
        seen["argv"], seen["kw"] = argv, kw
        return _R()

    monkeypatch.setattr(subprocess, "run", fake)
    assert claude_mod.run_claude("hi", timeout=7) == "ok"
    argv = seen["argv"]
    assert argv[argv.index("--model") + 1] == claude_mod.CLAUDE_MODEL
    assert seen["kw"]["input"] == "hi" and seen["kw"]["timeout"] == 7


def test_run_claude_nonzero_raises(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R(2, "", "x" * 500))
    with pytest.raises(RuntimeError) as e:
        claude_mod.run_claude("hi")
    assert "rc=2" in str(e.value) and "x" * 201 not in str(e.value)


def _patch(monkeypatch, mod, text):
    calls = []
    monkeypatch.setattr(mod, "run_claude", lambda p, **k: calls.append((p, k)) or text)
    return calls


def test_range_overview_uses_run_claude(monkeypatch):
    calls = _patch(monkeypatch, gen_range_overview, "sentence")
    assert gen_range_overview.call_claude("p") == "sentence"
    assert calls[0][1]["timeout"] == 120


def test_region_profiles_uses_run_claude(monkeypatch):
    calls = _patch(
        monkeypatch, gen_region_profiles,
        '```json\n{"best_time":"a","strengths":"b","watch_out":"c"}\n```',
    )
    assert gen_region_profiles.call_claude("p") == {"best_time": "a", "strengths": "b", "watch_out": "c"}
    assert calls[0][1]["timeout"] == 90


def test_monthly_summaries_uses_run_claude(monkeypatch):
    calls = _patch(monkeypatch, gen_monthly_summaries, "txt")
    assert gen_monthly_summaries.call_claude("p") == "txt"
    assert calls[0][1]["timeout"] == 90
