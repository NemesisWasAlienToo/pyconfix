"""What the TUI must do for disabled options.

Pins the behaviour that depends on an option being treated as disabled: the row
shows ``[disabled]``, Enter does nothing, reads and saves give None, and the
option works again once enabled.
"""

import json

import curses
import pytest

from pyconfix import pyconfix, ConfigOption, ConfigOptionType
from pyconfix.tui import Tui
from test_tui_smoke import FakeStdscr, FakeTextbox, stub_curses


SCHEMA = {"S": {
    "FEATURE": True,
    "FLAG": {"default": True, "deps": "FEATURE"},
    "NUM": {"default": 5, "deps": "FEATURE"},
    "TXT": {"default": "hi", "deps": "FEATURE"},
    "LEVEL": {"default": "B", "choices": ["A", "B", "C"], "deps": "FEATURE"},
    "CHILD_OF_NUM": {"default": True, "deps": "NUM > 1"},
    "FREE": {"default": 7},
}}
GATED = ["FLAG", "NUM", "TXT", "LEVEL"]
TOGGLE = curses.KEY_ENTER
EXIT_SEARCH = [Tui.abort_key, -1]


class BoundedScreen(FakeStdscr):
    """Fails instead of spinning: search and the enum editor ignore the quit
    key, so a loop still open when the keys run out would never end."""

    def getch(self):
        if not self.keys and self.quit_sent:
            raise AssertionError("Screen is still waiting for keys after quit")
        self.quit_sent = not self.keys
        return super().getch()

    quit_sent = False


@pytest.fixture(autouse=True)
def curses_stubbed(stub_curses):
    pass


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    (tmp_path / "schema.json").write_text(json.dumps(SCHEMA))
    monkeypatch.chdir(tmp_path)
    return pyconfix().load_schem(["schema.json"])


@pytest.fixture
def ran(cfg):
    calls = []
    cfg.add_options(ConfigOption(
        name="go", option_type=ConfigOptionType.ACTION,
        default=lambda x: calls.append(True), dependencies=lambda x: x.FEATURE))
    return calls


def play(cfg, keys, show_disabled=True, output="out.json"):
    tui = Tui(cfg, output, show_disabled=show_disabled)
    screen = BoundedScreen(keys + [tui.quite_key])
    tui._menu_loop(screen)
    return tui, screen


def row_text(screen, name):
    """The option's row as last drawn."""
    for call in reversed(screen.drawn):
        text = call[-1]
        if isinstance(text, str) and (text.startswith(f"{name}:") or text.startswith(f"({name})")):
            return text
    raise AssertionError(f"{name} was not drawn")


def rows_to(cfg, name):
    return [o.name for o in cfg.options].index(name)


def press_on(cfg, name, keys):
    """Go down to ``name``, press ``keys`` and come back to the first row."""
    distance = rows_to(cfg, name)
    return [curses.KEY_DOWN] * distance + keys + [curses.KEY_UP] * distance


# --------------------------------------------------------------------------- #
# Display
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", GATED)
def test_disabled_option_shows_disabled(cfg, name):
    _, screen = play(cfg, [TOGGLE])
    assert row_text(screen, name) == f"{name}: [disabled]"


def test_disabled_action_shows_disabled(cfg, ran):
    _, screen = play(cfg, [TOGGLE])
    assert row_text(screen, "go") == "(go) [disabled]"


def test_dependent_of_disabled_option_shows_disabled(cfg):
    _, screen = play(cfg, [TOGGLE])
    assert row_text(screen, "CHILD_OF_NUM") == "CHILD_OF_NUM: [disabled]"


def test_option_disabled_at_startup_shows_disabled_on_first_frame(cfg):
    cfg._get("FEATURE").value = False
    _, screen = play(cfg, [])
    assert row_text(screen, "NUM") == "NUM: [disabled]"


@pytest.mark.parametrize("name, text", [
    ("FLAG", "FLAG: True"), ("NUM", "NUM: 5"), ("TXT", "TXT: hi"), ("LEVEL", "LEVEL: B"),
])
def test_enabled_again_shows_the_value(cfg, name, text):
    _, screen = play(cfg, [TOGGLE, TOGGLE])
    assert row_text(screen, name) == text


def test_enabled_action_is_not_marked(cfg, ran):
    _, screen = play(cfg, [TOGGLE, TOGGLE])
    assert row_text(screen, "go") == "(go)"


def test_unrelated_option_is_not_marked(cfg):
    _, screen = play(cfg, [TOGGLE])
    assert row_text(screen, "FREE") == "FREE: 7"


def test_disabled_option_is_hidden_by_default(cfg):
    cfg._get("FEATURE").value = False
    _, screen = play(cfg, [], show_disabled=False)
    with pytest.raises(AssertionError):
        row_text(screen, "NUM")


def test_search_shows_disabled_option_as_disabled(cfg):
    _, screen = play(cfg, [TOGGLE, ord("/"), ord("N"), ord("U"), ord("M")] + EXIT_SEARCH)
    assert row_text(screen, "NUM") == "NUM: [disabled]"


# --------------------------------------------------------------------------- #
# Enter on a disabled row does nothing
# --------------------------------------------------------------------------- #

def test_enter_does_not_toggle_disabled_bool(cfg):
    play(cfg, [TOGGLE] + press_on(cfg, "FLAG", [TOGGLE]) + [TOGGLE])
    assert cfg.FLAG is True


@pytest.mark.parametrize("name, expected", [("NUM", 5), ("TXT", "hi")])
def test_enter_does_not_edit_disabled_option(cfg, monkeypatch, name, expected):
    monkeypatch.setattr(FakeTextbox, "result", "42")
    play(cfg, [TOGGLE] + press_on(cfg, name, [TOGGLE]) + [TOGGLE])
    assert cfg.get(name) == expected


def test_enter_does_not_open_editor_for_disabled_option(cfg, monkeypatch):
    opened = []
    monkeypatch.setattr(Tui, "_edit_option", lambda self, stdscr, option: opened.append(option.name))
    monkeypatch.setattr(Tui, "_edit_multiple_choice_option", lambda self, stdscr, option: opened.append(option.name))
    keys = [TOGGLE] + press_on(cfg, "NUM", [TOGGLE]) + press_on(cfg, "TXT", [TOGGLE]) + press_on(cfg, "LEVEL", [TOGGLE])
    play(cfg, keys)
    assert opened == []


def test_enter_does_not_edit_disabled_enum(cfg):
    play(cfg, [TOGGLE] + press_on(cfg, "LEVEL", [TOGGLE]) + [TOGGLE])
    assert cfg.LEVEL == "B"


def test_enter_does_not_run_disabled_action(cfg, ran):
    play(cfg, [TOGGLE] + press_on(cfg, "go", [TOGGLE]))
    assert ran == []


def test_enter_in_search_does_not_edit_disabled_option(cfg, monkeypatch):
    opened = []
    monkeypatch.setattr(Tui, "_edit_option", lambda self, stdscr, option: opened.append(option.name))
    play(cfg, [TOGGLE, ord("/"), ord("N"), ord("U"), ord("M"), TOGGLE] + EXIT_SEARCH)
    assert opened == []


def test_enter_still_edits_once_enabled_again(cfg, monkeypatch):
    monkeypatch.setattr(FakeTextbox, "result", "42")
    play(cfg, [TOGGLE, TOGGLE] + press_on(cfg, "NUM", [TOGGLE]))
    assert cfg.NUM == 42


# --------------------------------------------------------------------------- #
# Reads and saves see the option as disabled
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", GATED)
def test_attribute_is_none_while_disabled(cfg, name):
    play(cfg, [TOGGLE])
    assert cfg.get(name) is None


def test_dependency_reads_none_for_disabled_option(cfg):
    seen = []
    cfg.add_options(ConfigOption(name="WATCHER", default=True,
                                 dependencies=lambda x: seen.append(x.NUM) or True))
    play(cfg, [TOGGLE])
    assert seen[-1] is None


def test_action_reads_none_for_disabled_option(cfg):
    seen = []
    cfg.add_options(ConfigOption(name="reader", option_type=ConfigOptionType.ACTION,
                                 default=lambda x: seen.append(x.NUM)))
    play(cfg, [TOGGLE] + press_on(cfg, "reader", [TOGGLE]))
    assert seen == [None]


def test_save_writes_null_for_disabled_options(cfg, tmp_path):
    out = tmp_path / "saved.json"
    tui, _ = play(cfg, [TOGGLE, Tui.save_key, ord(" ")], output=str(out))
    written = json.loads(out.read_text())
    assert written["FEATURE"] is False
    assert all(written[name] is None for name in GATED)
    assert written["CHILD_OF_NUM"] is None
    assert written["FREE"] == 7


def test_diff_leaves_out_disabled_options(cfg):
    play(cfg, [TOGGLE])
    assert cfg.diff() == {"FEATURE": False}


def test_dump_after_enabling_again_has_the_values(cfg):
    before = cfg.dump()
    play(cfg, [TOGGLE, TOGGLE])
    assert cfg.dump() == before


# --------------------------------------------------------------------------- #
# A saved file with disabled options, loaded and opened in the TUI
# --------------------------------------------------------------------------- #

@pytest.fixture
def reloaded(cfg, tmp_path):
    """A fresh config loaded from a file saved with FEATURE off."""
    out = tmp_path / "saved.json"
    play(cfg, [TOGGLE, Tui.save_key, ord(" ")], output=str(out))
    fresh = pyconfix().load_schem(["schema.json"])
    fresh.apply_config(config_files=[str(out)])
    return fresh


def test_reloaded_disabled_option_shows_disabled(reloaded):
    _, screen = play(reloaded, [])
    assert row_text(screen, "NUM") == "NUM: [disabled]"


@pytest.mark.parametrize("name, text", [
    ("FLAG", "FLAG: True"), ("NUM", "NUM: 5"), ("TXT", "TXT: hi"), ("LEVEL", "LEVEL: B"),
])
def test_reloaded_option_gets_its_default_when_enabled(reloaded, name, text):
    _, screen = play(reloaded, [TOGGLE])
    assert row_text(screen, name) == text


def test_reloaded_option_is_editable_when_enabled(reloaded, monkeypatch):
    monkeypatch.setattr(FakeTextbox, "result", "42")
    play(reloaded, [TOGGLE] + press_on(reloaded, "NUM", [TOGGLE]))
    assert reloaded.NUM == 42


def test_reloaded_enum_is_editable_when_enabled(reloaded):
    play(reloaded, [TOGGLE] + press_on(reloaded, "LEVEL", [TOGGLE, curses.KEY_DOWN, TOGGLE]))
    assert reloaded.LEVEL == "C"


def test_reloaded_bool_is_toggleable_when_enabled(reloaded):
    play(reloaded, [TOGGLE] + press_on(reloaded, "FLAG", [TOGGLE]))
    assert reloaded.FLAG is False


def test_reloaded_option_saves_its_default_when_enabled(reloaded):
    play(reloaded, [TOGGLE])
    assert reloaded.dump()["NUM"] == 5
    assert reloaded.dump()["LEVEL"] == "B"


# --------------------------------------------------------------------------- #
# The cache only clears on a change
# --------------------------------------------------------------------------- #

def test_moving_over_disabled_options_does_not_re_evaluate(cfg):
    calls = []
    cfg.add_options(ConfigOption(name="COUNTED", default=True,
                                 dependencies=lambda x: calls.append(1) or x.FEATURE))
    cfg._get("FEATURE").value = False
    tui = Tui(cfg, "out.json", show_disabled=True)
    tui._flatten_options(cfg.options)
    tui._flatten_options(cfg.options)
    settled = len(calls)
    for _ in range(5):
        tui._flatten_options(cfg.options)
    assert len(calls) == settled
