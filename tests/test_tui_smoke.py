"""Headless smoke tests for the curses TUI.

Drives ``Tui._menu_loop`` with a fake ``stdscr`` and stubbed curses functions to
verify the TUI is wired to the core manager (no stale references) and that key
handling reaches core logic (toggle) and the serializer (save).
"""

import importlib
import json
import os

import curses
import curses.textpad
import pytest

from pyconfix import pyconfix, ConfigOption, ConfigOptionType
from pyconfix.tui import Tui


SCHEMA = {
    "Smoke": {
        "FIRST_BOOL": True,
        "AN_INT": 5,
        "GRP": {"CHILD_A": True, "CHILD_B": False},
    }
}


# A schema exercising every leaf type the TUI renders/edits.
RICH_SCHEMA = {
    "Rich": {
        "B1": True,
        "B2": False,
        "NUM": {"type": "int", "default": 5},
        "TXT": {"type": "string", "default": "hi"},
        "LEVEL": {"type": "enum", "default": "A", "choices": ["A", "B", "C"]},
        "EXT_INFO": {"type": "external", "default": 7},
        "GRP": {"CHILD": True},
    }
}


class FakeStdscr:
    """Minimal curses window stand-in that feeds a scripted key sequence and
    falls back to the quit key so loops always terminate."""

    def __init__(self, keys, quit_key=ord('q'), size=(24, 80)):
        self.keys = list(keys)
        self.quit_key = quit_key
        self._size = size
        self.drawn = []

    def getch(self):
        return self.keys.pop(0) if self.keys else self.quit_key

    def getmaxyx(self):
        return self._size

    def keypad(self, *a): pass
    def clear(self): pass
    def border(self, *a): pass
    def addstr(self, *a): self.drawn.append(a)
    def refresh(self): pass
    def timeout(self, *a): pass
    def attron(self, *a): pass
    def attroff(self, *a): pass


class FakeEditWin:
    """Stand-in for the curses.newwin edit window used by _edit_option."""
    def move(self, *a): pass
    def clrtoeol(self, *a): pass
    def addstr(self, *a): pass
    def refresh(self, *a): pass


class FakeTextbox:
    """Stand-in for curses.textpad.Textbox: exercises the validate callback
    (resize + newline) then returns a scripted string."""
    result = "42"

    def __init__(self, win, insert_mode=True):
        pass

    def edit(self, validate=None):
        if validate is not None:
            validate(curses.KEY_RESIZE)          # -> triggers a redraw branch
            validate(curses.ascii.NL)            # -> newline handling
        return type(self).result


@pytest.fixture
def stub_curses(monkeypatch):
    monkeypatch.setattr(curses, "curs_set", lambda *a: None, raising=False)
    monkeypatch.setattr(curses, "start_color", lambda *a: None, raising=False)
    monkeypatch.setattr(curses, "use_default_colors", lambda *a: None, raising=False)
    monkeypatch.setattr(curses, "init_pair", lambda *a: None, raising=False)
    monkeypatch.setattr(curses, "color_pair", lambda n: 0, raising=False)
    monkeypatch.setattr(curses, "keyname", lambda k: b"k", raising=False)
    monkeypatch.setattr(curses, "LINES", 24, raising=False)
    monkeypatch.setattr(curses, "newwin", lambda *a: FakeEditWin(), raising=False)
    monkeypatch.setattr(curses, "endwin", lambda *a: None, raising=False)
    monkeypatch.setattr(curses, "initscr", lambda *a: FakeStdscr([]), raising=False)
    monkeypatch.setattr(curses, "noecho", lambda *a: None, raising=False)
    monkeypatch.setattr(curses, "cbreak", lambda *a: None, raising=False)
    monkeypatch.setattr(curses, "echo", lambda *a: None, raising=False)
    monkeypatch.setattr(curses, "nocbreak", lambda *a: None, raising=False)
    monkeypatch.setattr(curses.textpad, "rectangle", lambda *a: None, raising=False)
    monkeypatch.setattr(curses.textpad, "Textbox", FakeTextbox, raising=False)


@pytest.fixture
def app(tmp_path, monkeypatch):
    (tmp_path / "smoke.json").write_text(json.dumps(SCHEMA))
    monkeypatch.chdir(tmp_path)
    cfg = pyconfix()
    cfg.load_schema(["smoke.json"])
    return cfg


@pytest.fixture
def rich(tmp_path, monkeypatch):
    (tmp_path / "rich.json").write_text(json.dumps(RICH_SCHEMA))
    monkeypatch.chdir(tmp_path)
    cfg = pyconfix()
    cfg.load_schema(["rich.json"])
    return cfg


def _rows_to(cfg, name):
    """Number of KEY_DOWN presses to reach a top-level option from row 0."""
    return [o.name for o in cfg.options].index(name)


def test_menu_loop_quits_cleanly(app, stub_curses):
    tui = Tui(app,"out.json")
    screen = FakeStdscr([tui.quite_key])
    tui._menu_loop(screen)
    assert screen.drawn


def test_menu_loop_toggles_first_bool(app, stub_curses):
    assert app.get_option("FIRST_BOOL").value is True
    tui = Tui(app,"out.json")
    tui._menu_loop(FakeStdscr([curses.KEY_ENTER, tui.quite_key]))
    assert app.get_option("FIRST_BOOL").value is False


def test_menu_loop_save_writes_config(app, stub_curses, tmp_path):
    out = str(tmp_path / "out.json")
    tui = Tui(app,out)
    tui._menu_loop(FakeStdscr([tui.save_key, ord(' '), tui.quite_key]))
    written = json.loads((tmp_path / "out.json").read_text())
    assert written == app.dump()


def test_tui_constructs_without_terminal():
    assert Tui(object(), "out.json").app is not None


# --------------------------------------------------------------------------- #
# Saving through the runner-wired TUI invokes the save hook with the emitted
# configuration data (save_func now takes a single argument).
# --------------------------------------------------------------------------- #

def test_run_save_func_receives_config_data(tmp_path, monkeypatch, stub_curses):
    (tmp_path / "smoke.json").write_text(json.dumps(SCHEMA))
    monkeypatch.chdir(tmp_path)

    recorded = {}

    def saver(config_data):
        recorded["data"] = dict(config_data)

    cfg = pyconfix()
    cfg.load_schema(["smoke.json"])
    out = str(tmp_path / "out.json")

    # Drive the real runner graphical path: save (full dump), dismiss, then quit.
    # cfg.run() builds the Tui internally, so reference the keys on the Tui class.
    screen = FakeStdscr([Tui.save_key, ord(" "), Tui.quite_key])
    monkeypatch.setattr(curses, "wrapper", lambda func, *a: func(screen), raising=False)
    cfg.run(output_file=out, save_func=saver)

    assert recorded["data"] == cfg.dump()     # the save key writes the full dump


# --------------------------------------------------------------------------- #
# search / collapse now live on the TUI (they drive core helpers)
# --------------------------------------------------------------------------- #

def test_search_options_filters_by_name(app):
    tui = Tui(app,"out.json")
    names = [o.name for o, _ in tui._search_options(app.options, "FIRST")]
    assert "FIRST_BOOL" in names
    assert "AN_INT" not in names


def test_search_options_matches_group_children(app):
    tui = Tui(app,"out.json")
    names = [o.name for o, _ in tui._search_options(app.options, "CHILD")]
    assert "CHILD_A" in names and "CHILD_B" in names
    assert "GRP" in names  # the parent group is included as context


def test_collapse_toggles_group_expanded(app):
    tui = Tui(app,"out.json")
    grp = app.get_option("GRP")
    before = grp.expanded
    flat = tui._flatten_options(app.options)   # flatten lives on the TUI now
    idx = next(i for i, (o, _) in enumerate(flat) if o is grp)
    tui._collapse_current_group(flat, idx, search_mode=False)
    assert grp.expanded is (not before)


# --------------------------------------------------------------------------- #
# flattening for display lives on the TUI (moved off Core)
# --------------------------------------------------------------------------- #

def test_flatten_includes_expanded_group_children_with_depth(app):
    grp = app.get_option("GRP")
    grp.expanded = True
    flat = Tui(app,"out.json")._flatten_options(app.options)
    depths = {o.name: d for o, d in flat}
    assert depths["GRP"] == 0
    assert depths["CHILD_A"] == 1


def test_flatten_hides_disabled_unless_show_disabled(tmp_path, monkeypatch):
    (tmp_path / "s.json").write_text(json.dumps({
        "S": {"FLAG": True, "DEP": {"type": "int", "default": 1, "dependencies": "FLAG"}}
    }))
    monkeypatch.chdir(tmp_path)
    cfg = pyconfix()
    cfg.load_schema(["s.json"])
    cfg.get_option("FLAG").value = False        # disables DEP (depends on FLAG)

    hidden = Tui(cfg,"out.json")._flatten_options(cfg.options)
    assert "DEP" not in [o.name for o, _ in hidden]
    shown = Tui(cfg,"out.json", show_disabled=True)._flatten_options(cfg.options)
    assert "DEP" in [o.name for o, _ in shown]


# --------------------------------------------------------------------------- #
# Driving the menu loop through each interaction (fake stdscr + stubbed curses)
# --------------------------------------------------------------------------- #

def test_menu_navigate_down_then_toggle_second_bool(rich, stub_curses):
    tui = Tui(rich, "out.json")
    tui._menu_loop(FakeStdscr([curses.KEY_DOWN, curses.KEY_ENTER, tui.quite_key]))
    assert rich.get_option("B1").value is True      # untouched
    assert rich.get_option("B2").value is True      # False -> True after toggle


def test_menu_navigate_up_is_clamped_at_top(rich, stub_curses):
    tui = Tui(rich, "out.json")
    # KEY_UP at the top row is a no-op; ENTER still toggles the first option.
    tui._menu_loop(FakeStdscr([curses.KEY_UP, curses.KEY_ENTER, tui.quite_key]))
    assert rich.get_option("B1").value is False


def test_menu_help_page_opens_and_returns(rich, stub_curses):
    tui = Tui(rich, "out.json")
    screen = FakeStdscr([tui.help_key, curses.KEY_DOWN, ord('q'), tui.quite_key])
    tui._menu_loop(screen)
    assert any("Help Page" in a for row in screen.drawn for a in row if isinstance(a, str))


def test_menu_description_page_opens_and_returns(rich, stub_curses):
    tui = Tui(rich, "out.json")
    screen = FakeStdscr([tui.description_key, curses.KEY_DOWN, ord('q'), tui.quite_key])
    tui._menu_loop(screen)                       # should not raise


def test_menu_collapse_key_expands_group(rich, stub_curses):
    tui = Tui(rich, "out.json")
    grp = rich.get_option("GRP")
    assert grp.expanded is False
    downs = [curses.KEY_DOWN] * _rows_to(rich, "GRP")
    tui._menu_loop(FakeStdscr(downs + [tui.collapse_key, tui.quite_key]))
    assert grp.expanded is True


def test_menu_save_diff_writes_only_changes(rich, stub_curses, tmp_path):
    out = str(tmp_path / "diff.json")
    rich.get_option("B2").value = True                 # one change from defaults
    tui = Tui(rich, out)
    tui._menu_loop(FakeStdscr([tui.save_diff_key, ord(' '), tui.quite_key]))
    written = json.loads((tmp_path / "diff.json").read_text())
    assert written == rich.diff()
    assert "B1" not in written and written.get("B2") is True


def test_menu_edit_int_option(rich, stub_curses):
    FakeTextbox.result = "42"
    tui = Tui(rich, "out.json")
    downs = [curses.KEY_DOWN] * _rows_to(rich, "NUM")
    tui._menu_loop(FakeStdscr(downs + [curses.KEY_ENTER, tui.quite_key]))
    assert rich.get_option("NUM").value == 42


def test_menu_edit_int_option_rejects_invalid(rich, stub_curses):
    FakeTextbox.result = "not-a-number"
    tui = Tui(rich, "out.json")
    downs = [curses.KEY_DOWN] * _rows_to(rich, "NUM")
    tui._menu_loop(FakeStdscr(downs + [curses.KEY_ENTER, tui.quite_key]))
    assert rich.get_option("NUM").value == 5           # kept the original on ValueError
    FakeTextbox.result = "42"                     # restore for other tests


def test_menu_edit_enum_selects_next_choice(rich, stub_curses):
    tui = Tui(rich, "out.json")
    downs = [curses.KEY_DOWN] * _rows_to(rich, "LEVEL")
    tui._menu_loop(FakeStdscr(
        downs + [curses.KEY_ENTER, curses.KEY_DOWN, curses.KEY_ENTER, tui.quite_key]))
    assert rich.LEVEL == "B"                      # A -> B


def test_menu_edit_enum_abort_keeps_original(rich, stub_curses):
    tui = Tui(rich, "out.json")
    downs = [curses.KEY_DOWN] * _rows_to(rich, "LEVEL")
    tui._menu_loop(FakeStdscr(
        downs + [curses.KEY_ENTER, curses.KEY_DOWN, tui.abort_key, tui.quite_key]))
    assert rich.LEVEL == "A"                      # aborted -> original


def test_menu_external_option_enter_is_noop(rich, stub_curses):
    tui = Tui(rich, "out.json")
    downs = [curses.KEY_DOWN] * _rows_to(rich, "EXT_INFO")
    tui._menu_loop(FakeStdscr(downs + [curses.KEY_ENTER, tui.quite_key]))  # no raise


def test_menu_action_enter_executes(tmp_path, monkeypatch, stub_curses):
    (tmp_path / "rich.json").write_text(json.dumps({"A": {"FLAG": True}}))
    monkeypatch.chdir(tmp_path)
    cfg = pyconfix()
    cfg.load_schema(["rich.json"])
    ran = []
    cfg.add_options(ConfigOption(name="build", option_type=ConfigOptionType.ACTION,
                                 default=lambda x: ran.append(True)))
    tui = Tui(cfg, "out.json")
    downs = [curses.KEY_DOWN] * _rows_to(cfg, "build")
    tui._menu_loop(FakeStdscr(downs + [curses.KEY_ENTER, tui.quite_key]))
    assert ran == [True]


def test_menu_search_type_then_abort(rich, stub_curses):
    tui = Tui(rich, "out.json")
    # enter search, type "B", backspace, type "B", abort (confirmed by -1), quit
    screen = FakeStdscr([tui.search_key, ord('B'), curses.KEY_BACKSPACE,
                         ord('B'), tui.abort_key, -1, tui.quite_key])
    tui._menu_loop(screen)                        # should not raise


def test_menu_search_enter_toggles_match(rich, stub_curses):
    tui = Tui(rich, "out.json")
    # search "B2" narrows to that bool; Enter toggles it, then abort + quit.
    screen = FakeStdscr([tui.search_key, ord('B'), ord('2'),
                         curses.KEY_ENTER, tui.abort_key, -1, tui.quite_key])
    tui._menu_loop(screen)
    assert rich.get_option("B2").value is True         # False -> True via search+enter


# Toggling an option in the TUI: the case from example.py, where turning off
# ENABLE_FEATURE_A crashed the redraw on POWER_TEST's INT_TYPE_DEDUCED**2 < 10.
FEATURE_SCHEMA = {"S": {
    "FEATURE": True,
    "COUNT": {"default": 2, "deps": "FEATURE"},
    "SMALL": {"default": True, "deps": "COUNT ** 2 < 10"},
    "NEGATED": {"default": True, "deps": "-COUNT < 0"},
    "AFTER": {"default": True, "deps": "SMALL"},
}}


def toggle(tui, cfg, name):
    flat = tui._flatten_options(cfg.options)
    row = [option.name for option, _ in flat].index(name)
    tui._handle_enter(flat, row, None, False)


def available(tui, cfg):
    return {option.name: bool(tui.session._is_option_available(option)) for option in cfg.options}


@pytest.fixture
def feature(tmp_path, monkeypatch):
    (tmp_path / "schema.json").write_text(json.dumps(FEATURE_SCHEMA))
    monkeypatch.chdir(tmp_path)
    return pyconfix().load_schema(["schema.json"])


def test_toggling_option_off_redraws_with_math_on_disabled_option(feature):
    tui = Tui(feature, "out.json")
    toggle(tui, feature, "FEATURE")
    assert [o.name for o, _ in tui._flatten_options(feature.options)] == ["FEATURE"]
    assert available(tui, feature) == {
        "FEATURE": True, "COUNT": False, "SMALL": False, "NEGATED": False, "AFTER": False}


def test_toggling_option_back_on_restores_dependents(feature):
    tui = Tui(feature, "out.json")
    toggle(tui, feature, "FEATURE")
    tui._flatten_options(feature.options)
    toggle(tui, feature, "FEATURE")
    assert [o.name for o, _ in tui._flatten_options(feature.options)] == list(FEATURE_SCHEMA["S"])


def test_toggling_shows_disabled_options_when_asked(feature):
    tui = Tui(feature, "out.json", show_disabled=True)
    toggle(tui, feature, "FEATURE")
    assert [o.name for o, _ in tui._flatten_options(feature.options)] == list(FEATURE_SCHEMA["S"])


def test_search_redraws_after_toggling_option_off(feature):
    tui = Tui(feature, "out.json")
    toggle(tui, feature, "FEATURE")
    assert [o.name for o, _ in tui._search_options(feature.options, "S")] == []
    assert [o.name for o, _ in tui._search_options(feature.options, "FEATURE")] == ["FEATURE"]


def test_dump_and_diff_after_toggling_option_off(feature):
    tui = Tui(feature, "out.json")
    toggle(tui, feature, "FEATURE")
    tui._flatten_options(feature.options)
    assert feature.dump() == {
        "FEATURE": False, "COUNT": None, "SMALL": None, "NEGATED": None, "AFTER": None}
    assert feature.diff() == {"FEATURE": False}


@pytest.mark.parametrize("expression", [
    "COUNT > 1", "COUNT < 9", "COUNT >= 1", "COUNT <= 9", "1 < COUNT",
    "COUNT + 1", "COUNT - 1", "COUNT * 2", "COUNT / 2", "COUNT ** 2", "COUNT % 3",
    "COUNT & 3", "COUNT | 1", "COUNT ^ 1", "COUNT >> 1", "COUNT << 1", "-COUNT",
    "(COUNT + 1) * 2 > 3", "COUNT == 2", "NAME == 'x'", "MODE == DEBUG",
])
def test_every_operator_on_disabled_option_disables_dependent(tmp_path, monkeypatch, expression):
    (tmp_path / "schema.json").write_text(json.dumps({"S": {
        "FEATURE": True,
        "COUNT": {"default": 2, "deps": "FEATURE"},
        "NAME": {"default": "x", "deps": "FEATURE"},
        "MODE": {"default": "DEBUG", "choices": ["DEBUG", "INFO"], "deps": "FEATURE"},
        "DEPENDENT": {"default": True, "deps": expression},
    }}))
    monkeypatch.chdir(tmp_path)
    cfg = pyconfix().load_schema(["schema.json"])
    tui = Tui(cfg, "out.json")

    assert "DEPENDENT" in [o.name for o, _ in tui._flatten_options(cfg.options)]
    toggle(tui, cfg, "FEATURE")
    assert "DEPENDENT" not in [o.name for o, _ in tui._flatten_options(cfg.options)]
    toggle(tui, cfg, "FEATURE")
    assert "DEPENDENT" in [o.name for o, _ in tui._flatten_options(cfg.options)]


def test_negated_math_on_disabled_option_enables_dependent(tmp_path, monkeypatch):
    (tmp_path / "schema.json").write_text(json.dumps({"S": {
        "FEATURE": True,
        "COUNT": {"default": 2, "deps": "FEATURE"},
        "FALLBACK": {"default": True, "deps": "!(COUNT > 1)"},
    }}))
    monkeypatch.chdir(tmp_path)
    cfg = pyconfix().load_schema(["schema.json"])
    tui = Tui(cfg, "out.json")

    assert "FALLBACK" not in [o.name for o, _ in tui._flatten_options(cfg.options)]
    toggle(tui, cfg, "FEATURE")
    assert "FALLBACK" in [o.name for o, _ in tui._flatten_options(cfg.options)]


def test_action_and_group_gated_by_math_on_disabled_option(tmp_path, monkeypatch):
    (tmp_path / "schema.json").write_text(json.dumps({"S": {
        "FEATURE": True,
        "COUNT": {"default": 2, "deps": "FEATURE"},
        "GRP": {"type": "group", "deps": "COUNT > 1", "options": {"CHILD": True}},
    }}))
    monkeypatch.chdir(tmp_path)
    cfg = pyconfix().load_schema(["schema.json"])

    @cfg.action_option(dependencies=lambda x: x.COUNT is not None and x.COUNT > 1)
    def run_it(x):
        return "ran"

    tui = Tui(cfg, "out.json")
    assert cfg.run_it()[0] == "ran"
    toggle(tui, cfg, "FEATURE")
    names = [o.name for o, _ in tui._flatten_options(cfg.options)]
    assert "GRP" not in names and "run_it" not in names
    assert cfg.run_it() == (None, [])


def test_every_example_bool_survives_toggling(monkeypatch):
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(root)
    example = importlib.import_module("example")
    cfg = example.create_config()
    tui = Tui(cfg, "out.json", show_disabled=True)

    assert cfg.ENABLE_FEATURE_A is True
    for option in list(cfg.option_map.values()):
        if option.option_type == ConfigOptionType.BOOL:
            for _ in range(2):
                tui._handle_enter([(option, 0)], 0, None, False)
                tui._flatten_options(cfg.options)
                cfg.dump()
