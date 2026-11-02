import sys

import pytest

from pyconfix import __main__ as cli

SCHEMA = """{"Main": {
    "OFF": false,
    "GOOD": {"type": "action", "default": "true"},
    "BAD": {"type": "action", "default": "false"},
    "BLOCKED": {"type": "action", "needs": "BAD()", "default": "true"},
    "DISABLED": {"type": "action", "deps": "OFF", "default": "true"}
}}"""


def run(tmp_path, monkeypatch, *args):
    (tmp_path / "pyconfixfile.json").write_text(SCHEMA)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["pyconfix", *args])
    cli.main()


def test_a_task_that_succeeds_exits_normally(tmp_path, monkeypatch):
    run(tmp_path, monkeypatch, "--run", "GOOD")


@pytest.mark.parametrize("name, message", [
    ("BAD", "failed"),
    ("BLOCKED", "failed"),
    ("DISABLED", "disabled"),
    ("NOPE", "not a task"),
    ("OFF", "not a task"),
])
def test_a_task_that_did_not_succeed_exits_with_1(tmp_path, monkeypatch, capsys, name, message):
    with pytest.raises(SystemExit) as e:
        run(tmp_path, monkeypatch, "--run", name)
    assert e.value.code == 1
    assert message in capsys.readouterr().err


def test_a_python_task_returning_none_succeeded(tmp_path):
    from pyconfix import pyconfix

    config = pyconfix()

    @config.action_option()
    def build(x):
        pass

    assert cli.run_action(config, "build", False, False)


def test_value_and_trace_print_for_a_failed_task(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit):
        run(tmp_path, monkeypatch, "--run", "BAD", "-v", "-t")
    assert "Value: False" in capsys.readouterr().out
