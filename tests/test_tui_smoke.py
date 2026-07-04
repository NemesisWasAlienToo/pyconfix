"""Headless smoke tests for the curses TUI.

Drives ``Tui._menu_loop`` with a fake ``stdscr`` and stubbed curses functions to
verify the TUI is wired to the core manager (no stale references) and that key
handling reaches core logic (toggle) and the serializer (save).
"""

import json

import curses
import pytest

from pyconfix import pyconfix
from pyconfix.tui import Tui


SCHEMA = {
    "Smoke": {
        "FIRST_BOOL": True,
        "AN_INT": 5,
        "GRP": {"CHILD_A": True, "CHILD_B": False},
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


@pytest.fixture
def stub_curses(monkeypatch):
    monkeypatch.setattr(curses, "curs_set", lambda *a: None, raising=False)
    monkeypatch.setattr(curses, "start_color", lambda *a: None, raising=False)
    monkeypatch.setattr(curses, "use_default_colors", lambda *a: None, raising=False)
    monkeypatch.setattr(curses, "init_pair", lambda *a: None, raising=False)
    monkeypatch.setattr(curses, "color_pair", lambda n: 0, raising=False)
    monkeypatch.setattr(curses, "keyname", lambda k: b"k", raising=False)


@pytest.fixture
def app(tmp_path, monkeypatch):
    (tmp_path / "smoke.json").write_text(json.dumps(SCHEMA))
    monkeypatch.chdir(tmp_path)
    cfg = pyconfix()
    cfg.load_schem(["smoke.json"])
    return cfg


def test_menu_loop_quits_cleanly(app, stub_curses):
    tui = Tui(app,"out.json")
    screen = FakeStdscr([tui.quite_key])
    tui._menu_loop(screen)
    assert screen.drawn


def test_menu_loop_toggles_first_bool(app, stub_curses):
    assert app._get("FIRST_BOOL").value is True
    tui = Tui(app,"out.json")
    tui._menu_loop(FakeStdscr([curses.KEY_ENTER, tui.quite_key]))
    assert app._get("FIRST_BOOL").value is False


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
    cfg.load_schem(["smoke.json"])
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
    grp = app._get("GRP")
    before = grp.expanded
    flat = tui._flatten_options(app.options)   # flatten lives on the TUI now
    idx = next(i for i, (o, _) in enumerate(flat) if o is grp)
    tui._collapse_current_group(flat, idx, search_mode=False)
    assert grp.expanded is (not before)


# --------------------------------------------------------------------------- #
# flattening for display lives on the TUI (moved off Core)
# --------------------------------------------------------------------------- #

def test_flatten_includes_expanded_group_children_with_depth(app):
    grp = app._get("GRP")
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
    cfg.load_schem(["s.json"])
    cfg._get("FLAG").value = False        # disables DEP (depends on FLAG)

    hidden = Tui(cfg,"out.json")._flatten_options(cfg.options)
    assert "DEP" not in [o.name for o, _ in hidden]
    shown = Tui(cfg,"out.json", show_disabled=True)._flatten_options(cfg.options)
    assert "DEP" in [o.name for o, _ in shown]
