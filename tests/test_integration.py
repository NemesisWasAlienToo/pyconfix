"""End-to-end characterization tests for the pyconfix facade.

These exercise the full pipeline (schema load -> dependency compile -> config
apply -> dump/diff/get/actions) WITHOUT the curses TUI, by running headless
(``graphical=False``). They are written against the current behavior on purpose:
they form the safety net the module split must keep green.

Where the current behavior is a known bug that the refactor intends to fix, the
test asserts the *desired* behavior and is marked ``xfail`` with a reason, so the
suite stays green now and the marker can be dropped once the fix lands.
"""

import json
import os

import pytest

from pyconfix import pyconfix, ConfigOption, ConfigOptionType


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

MAIN_SCHEMA = {
    "Probe Config": {
        # scalar shorthands
        "SHORT_BOOL": True,
        "SHORT_INT": 10,
        "SHORT_STR": "hello",
        "SHORT_ENUM": ["DEBUG", "INFO", "WARN"],
        # object form with inference
        "OBJ_BOOL": {"default": False},
        "OBJ_ENUM": {"default": "B", "choices": ["A", "B", "C"]},
        # explicit type + dependencies covering several operator classes
        "ENABLE_FEATURE_A": {"type": "bool", "default": True},
        "DEP_ON_A": {"type": "int", "default": 5, "dependencies": "ENABLE_FEATURE_A"},
        "POWER_TEST": {"default": True, "dependencies": "SHORT_INT**2 < 10"},
        "CMP_TEST": {"default": 1, "dependencies": "SHORT_ENUM==DEBUG || SHORT_ENUM==INFO"},
        "BITWISE": {"default": 7, "dependencies": "(SHORT_INT & 0xF) == 10"},
        # explicit group with a cascading dependency
        "GROUP_EXPLICIT": {
            "type": "group",
            "dependencies": "ENABLE_FEATURE_A",
            "options": {"SUB_A": {"type": "bool", "default": False}},
        },
        # implicit group (no type/default/choices) with nesting
        "GROUP_IMPLICIT": {
            "CHILD_INT": 3,
            "NESTED": {"DEEP_BOOL": True},
        },
        "include": ["extra.json"],
    }
}

EXTRA_SCHEMA = {"Extra": {"EXTRA_FEATURE": {"type": "bool", "default": False}}}


@pytest.fixture
def make_config(tmp_path, monkeypatch):
    """Factory that writes the schema files, builds a configured pyconfix, and
    runs it headless. Returns a callable so each test gets a fresh instance.
    """
    (tmp_path / "main.json").write_text(json.dumps(MAIN_SCHEMA))
    (tmp_path / "extra.json").write_text(json.dumps(EXTRA_SCHEMA))
    monkeypatch.chdir(tmp_path)

    def _build(*, overlay=None, config_files=None, with_python_options=True):
        cfg = pyconfix(
            schem_files=["main.json"],
            output_file=str(tmp_path / "out.json"),
        )
        cfg.register_alias(
            name="tri-state",
            option_type=ConfigOptionType.ENUM,
            choices=["INTEGRATED", "MODULE", "DISABLED"],
        )
        if with_python_options:
            cfg.add_options(
                cfg.option_from_alias("tri-state", name="TRI"),
                ConfigOption(name="OS", option_type=ConfigOptionType.EXTERNAL, default="StaticOS"),
            )

            @cfg.action_option(dependencies=lambda x: x.ENABLE_FEATURE_A)
            def build(x):
                return 42

            @cfg.action_option(requires=lambda x: x.build() == 42)
            def deploy(x):
                return x.build() + 1

        cfg.run(graphical=False, overlay=overlay, config_files=config_files or [])
        return cfg

    return _build


@pytest.fixture
def cfg(make_config):
    return make_config()


def find_option(options, name):
    """Recursively locate an option by name, groups included.

    ``pyconfix._get`` only descends into groups and never matches a group by its
    own name, so it returns ``None`` for groups; this helper does not, letting us
    assert on the parsed tree directly.
    """
    for opt in options:
        if opt.name == name:
            return opt
        if opt.option_type == ConfigOptionType.GROUP:
            found = find_option(opt.options, name)
            if found is not None:
                return found
    return None


# --------------------------------------------------------------------------- #
# Schema loading & type inference
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name,expected", [
    ("SHORT_BOOL", ConfigOptionType.BOOL),
    ("SHORT_INT", ConfigOptionType.INT),
    ("SHORT_STR", ConfigOptionType.STRING),
    ("SHORT_ENUM", ConfigOptionType.ENUM),
    ("OBJ_BOOL", ConfigOptionType.BOOL),
    ("OBJ_ENUM", ConfigOptionType.ENUM),
    ("GROUP_EXPLICIT", ConfigOptionType.GROUP),
    ("GROUP_IMPLICIT", ConfigOptionType.GROUP),
    ("NESTED", ConfigOptionType.GROUP),
    ("TRI", ConfigOptionType.ENUM),
    ("OS", ConfigOptionType.EXTERNAL),
])
def test_type_inference(cfg, name, expected):
    assert find_option(cfg.options, name).option_type == expected


def test_include_pulls_in_options(cfg):
    opt = cfg._get("EXTRA_FEATURE")
    assert opt is not None
    assert opt.option_type == ConfigOptionType.BOOL


def test_enum_default_is_first_choice_when_unspecified(cfg):
    assert cfg.SHORT_ENUM == "DEBUG"


def test_too_many_top_level_keys_is_rejected(tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"A": {}, "B": {}}))
    monkeypatch.chdir(tmp_path)
    cfg = pyconfix(schem_files=["bad.json"])
    with pytest.raises(SystemExit):
        cfg.load_schem(["bad.json"])


# --------------------------------------------------------------------------- #
# Dump
# --------------------------------------------------------------------------- #

def test_dump_defaults(cfg):
    dumped = cfg.dump()
    assert dumped["SHORT_BOOL"] is True
    assert dumped["SHORT_INT"] == 10
    assert dumped["SHORT_STR"] == "hello"
    assert dumped["SHORT_ENUM"] == "DEBUG"
    assert dumped["OBJ_BOOL"] is False
    assert dumped["OBJ_ENUM"] == "B"
    assert dumped["ENABLE_FEATURE_A"] is True
    assert dumped["DEP_ON_A"] == 5
    assert dumped["CMP_TEST"] == 1
    assert dumped["BITWISE"] == 7
    assert dumped["EXTRA_FEATURE"] is False
    assert dumped["TRI"] == "INTEGRATED"
    assert dumped["OS"] == "StaticOS"


def test_dump_flattens_groups(cfg):
    dumped = cfg.dump()
    # group children appear at top level; groups themselves do not
    assert dumped["SUB_A"] is False
    assert dumped["CHILD_INT"] == 3
    assert dumped["DEEP_BOOL"] is True
    assert "GROUP_EXPLICIT" not in dumped
    assert "GROUP_IMPLICIT" not in dumped


def test_dump_disabled_option_is_none(cfg):
    # SHORT_INT**2 == 100, not < 10, so POWER_TEST is unavailable
    assert cfg.dump()["POWER_TEST"] is None


def test_dump_skips_actions(cfg):
    dumped = cfg.dump()
    assert "build" not in dumped
    assert "deploy" not in dumped


# --------------------------------------------------------------------------- #
# Availability / dependencies
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name,available", [
    ("POWER_TEST", False),   # 10**2 < 10 -> False
    ("CMP_TEST", True),      # enum == DEBUG -> True
    ("BITWISE", True),       # (10 & 0xF) == 10 -> True
    ("DEP_ON_A", True),      # ENABLE_FEATURE_A -> True
    ("EXTRA_FEATURE", True),
])
def test_availability(cfg, name, available):
    assert cfg._is_option_available(cfg._get(name)) is available


def test_group_dependency_cascades_to_children(make_config):
    # disabling ENABLE_FEATURE_A should disable GROUP_EXPLICIT's child SUB_A
    cfg = make_config(overlay={"ENABLE_FEATURE_A": False})
    assert cfg._is_option_available(cfg._get("SUB_A")) is False
    assert cfg.dump()["SUB_A"] is None


# --------------------------------------------------------------------------- #
# Diff
# --------------------------------------------------------------------------- #

def test_diff_empty_at_defaults(cfg):
    assert cfg.diff() == {}


def test_diff_reports_only_changed(make_config):
    cfg = make_config(overlay={"SHORT_INT": 99, "SHORT_STR": "changed"})
    assert cfg.SHORT_INT == 99
    assert cfg.diff() == {"SHORT_INT": 99, "SHORT_STR": "changed"}


# --------------------------------------------------------------------------- #
# Attribute / get access
# --------------------------------------------------------------------------- #

def test_attribute_access(cfg):
    assert cfg.SHORT_BOOL is True
    assert cfg.SHORT_INT == 10
    assert cfg.SHORT_ENUM == "DEBUG"      # enum -> choice string
    assert cfg.OBJ_ENUM == "B"
    assert cfg.OS == "StaticOS"


def test_attribute_access_disabled_returns_none(cfg):
    assert cfg.POWER_TEST is None


def test_attribute_access_unknown_raises(cfg):
    with pytest.raises(AttributeError):
        _ = cfg.DOES_NOT_EXIST


def test_get_existing(cfg):
    assert cfg.get("SHORT_INT") == 10


def test_get_missing_returns_default(cfg):
    assert cfg.get("DOES_NOT_EXIST", "fallback") == "fallback"


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #

def test_action_top_level_returns_value_and_trace(cfg):
    # NOTE: top-level action access returns a (value, trace) tuple; this
    # asymmetry (in-session calls return the bare value) is relied on by
    # example.py and is pinned here intentionally.
    assert cfg.build() == (42, ["build"])


def test_execute_action_returns_value_and_trace(cfg):
    assert cfg._execute_action(cfg._get("build")) == (42, ["build"])


def test_action_with_requires_and_chained_dependency(cfg):
    value, trace = cfg.deploy()
    assert value == 43
    assert trace[0] == "deploy"
    assert "build" in trace


def test_in_session_action_returns_bare_value(cfg):
    # deploy's body does `x.build() + 1`; if in-session returned a tuple this
    # arithmetic would fail. Reaching 43 proves the bare-value shape.
    value, _ = cfg.deploy()
    assert value == 43


# --------------------------------------------------------------------------- #
# Serialization to disk
# --------------------------------------------------------------------------- #

def test_write_config_roundtrip(cfg, tmp_path):
    cfg._write_config(output_diff=False)
    written = json.loads((tmp_path / "out.json").read_text())
    assert written == cfg.dump()


def test_save_func_is_invoked(make_config, tmp_path, monkeypatch):
    (tmp_path / "main.json").write_text(json.dumps(MAIN_SCHEMA))
    (tmp_path / "extra.json").write_text(json.dumps(EXTRA_SCHEMA))
    monkeypatch.chdir(tmp_path)

    calls = []

    def saver(config_data, config, is_diff):
        calls.append((dict(config_data), is_diff))

    cfg = pyconfix(schem_files=["main.json"], output_file=str(tmp_path / "out.json"),
                   save_func=saver)
    cfg.register_alias(name="tri-state", option_type=ConfigOptionType.ENUM,
                       choices=["INTEGRATED", "MODULE", "DISABLED"])
    cfg.run(graphical=False)
    cfg._write_config(output_diff=True)

    assert len(calls) == 1
    assert calls[0][1] is True
