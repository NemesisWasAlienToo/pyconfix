"""Tests for the module separation and boundaries.

Layers: serializer (files) -> core (options) -> runner (top, composes core+tui).
Verifies the new seams: modular serializer, core building/applying from plain
data, runner composition/forwarding, and the curses-free headless guarantee.
"""

import json
import subprocess
import sys
import textwrap

import pytest

from pyconfix import pyconfix, Core, ConfigOption, ConfigOptionType, serializer


SCHEMA = {
    "Sep": {
        "A_BOOL": True,
        "AN_INT": {"type": "int", "default": 7},
        "GATED": {"default": 1, "dependencies": "A_BOOL"},
    }
}


@pytest.fixture
def written_schema(tmp_path, monkeypatch):
    (tmp_path / "sep.json").write_text(json.dumps(SCHEMA))
    monkeypatch.chdir(tmp_path)
    return tmp_path


# --------------------------------------------------------------------------- #
# serializer: modular file format registry + read/write
# --------------------------------------------------------------------------- #

def test_serializer_json_roundtrip(tmp_path):
    p = tmp_path / "x.json"
    serializer.write(str(p), {"a": 1, "b": "two"})
    assert serializer.read(str(p)) == {"a": 1, "b": "two"}


def test_register_custom_format(tmp_path, monkeypatch):
    class UpperJson(serializer.JsonFormat):
        extensions = (".weird",)
        def read(self, path):
            with open(path) as f:
                return {"READ_BY": "weird", **json.load(f)}

    # don't leak the registration into other tests
    monkeypatch.setattr(serializer, "_FORMATS", list(serializer._FORMATS))
    serializer.register_format(UpperJson())
    p = tmp_path / "cfg.weird"
    p.write_text(json.dumps({"k": 1}))
    assert serializer.read(str(p)) == {"READ_BY": "weird", "k": 1}


def test_unknown_extension_falls_back_to_json(tmp_path):
    p = tmp_path / "cfg.unknownext"
    serializer.write(str(p), {"k": 1})           # no handler -> JSON default
    assert serializer.read(str(p)) == {"k": 1}


def test_parse_unknown_type_raises():
    core = Core()
    with pytest.raises(ValueError):
        serializer.parse_options(core, {"X": {"type": "bogus"}})


def test_read_config_files_merges_in_order(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"A": 1, "N": 1}))
    (tmp_path / "b.json").write_text(json.dumps({"B": 2, "N": 9}))
    merged = serializer.read_config_files([str(tmp_path / "a.json"), str(tmp_path / "b.json")])
    assert merged == {"A": 1, "B": 2, "N": 9}   # later file wins


def test_read_config_files_missing_raises():
    with pytest.raises(ValueError):
        serializer.read_config_files(["/no/such/config.json"])


# --------------------------------------------------------------------------- #
# serializer parses schema dicts -> options (via core.add_options); core applies
# --------------------------------------------------------------------------- #

def _load_dict(core, schema_dict):
    """Build+register options from a plain dict, the way the serializer does."""
    core.add_options(*serializer.parse_options(core, schema_dict))
    serializer.finalize_dependencies(core)


def test_serializer_parses_options_into_core_via_add_options():
    core = Core()
    _load_dict(core, {"A": True, "N": {"type": "int", "default": 5},
                      "E": {"choices": ["x", "y"]}})
    assert core._get("A").option_type == ConfigOptionType.BOOL
    assert core._get("N").value == 5
    assert core._get("E").option_type == ConfigOptionType.ENUM


def test_core_apply_config_takes_a_dict_and_overlay():
    core = Core()
    _load_dict(core, {"N": {"type": "int", "default": 5}})
    core.apply_config({"N": 10})
    assert core.N == 10
    core.apply_config({"N": 10}, overlay={"N": 99})
    assert core.N == 99


def test_serializer_finalize_cascades_group_dependency():
    core = Core()
    _load_dict(core, {
        "A_BOOL": True,
        "G": {"type": "group", "dependencies": "A_BOOL", "options": {"CHILD": False}},
    })
    core.apply_config({"A_BOOL": False})
    assert core._is_option_available(core._get("CHILD")) is False


# --------------------------------------------------------------------------- #
# runner: composition + forwarding
# --------------------------------------------------------------------------- #

def test_runner_forwards_option_access_to_core(written_schema):
    cfg = pyconfix(schem_files=["sep.json"])
    assert isinstance(cfg.core, Core)
    # option methods/attrs resolve through to the core
    cfg.add_options(ConfigOption(name="X", option_type=ConfigOptionType.BOOL, default=True))
    assert cfg._get("X") is not None
    assert cfg.options is cfg.core.options


def test_runner_load_and_run_headless(written_schema):
    cfg = pyconfix(schem_files=["sep.json"], output_file=str(written_schema / "out.json"))
    cfg.run(graphical=False, overlay={"AN_INT": 42})
    assert cfg.config_name == "Sep"
    assert cfg.AN_INT == 42
    assert cfg._is_option_available(cfg._get("GATED")) is True


def test_load_schem_reports_multiple_top_entries(tmp_path, monkeypatch):
    (tmp_path / "bad.json").write_text(json.dumps({"A": {}, "B": {}}))
    monkeypatch.chdir(tmp_path)
    cfg = pyconfix(schem_files=["bad.json"])
    with pytest.raises(SystemExit):
        cfg.load_schem(["bad.json"])


def test_load_schem_then_run_does_not_duplicate(written_schema):
    # Loading the schema twice must not append a second copy of the tree.
    cfg = pyconfix(schem_files=["sep.json"], output_file=str(written_schema / "out.json"))
    cfg.load_schem(["sep.json"])
    cfg.run(graphical=False)
    names = [o.name for o in cfg.options]
    assert names == list(dict.fromkeys(names)), f"duplicated options: {names}"


def test_run_twice_is_idempotent(written_schema):
    cfg = pyconfix(schem_files=["sep.json"], output_file=str(written_schema / "out.json"))
    cfg.run(graphical=False)
    first = [o.name for o in cfg.options]
    cfg.run(graphical=False)
    assert [o.name for o in cfg.options] == first


# --------------------------------------------------------------------------- #
# runner: decorator API for actions and groups (moved off Core)
# --------------------------------------------------------------------------- #

def test_runner_action_option_registers_on_core():
    cfg = pyconfix()

    @cfg.action_option()
    def build(x):
        return "built"

    assert cfg._get("build").option_type == ConfigOptionType.ACTION
    assert cfg.core._get("build") is not None      # lives on the underlying core
    assert cfg.build() == ("built", ["build"])


def test_runner_group_option_and_grouped_action():
    cfg = pyconfix()
    proxy = cfg.group_option("deploy")
    assert proxy.get().option_type == ConfigOptionType.GROUP
    assert cfg.core.options[-1] is proxy.get()      # group appended to the core

    @proxy.action_option()
    def ship(x):
        return "shipped"

    assert cfg._get("ship").option_type == ConfigOptionType.ACTION
    # the action was registered inside the group, not at top level
    assert any(o.name == "ship" for o in proxy.get().options)


# --------------------------------------------------------------------------- #
# serializer: 'include' resolution (top-level and nested inside a group)
# --------------------------------------------------------------------------- #

def test_nested_group_include_is_loaded(tmp_path, monkeypatch):
    (tmp_path / "main.json").write_text(json.dumps({
        "App": {"GRP": {"options": {"include": ["extra.json"], "CHILD": True}}}
    }))
    (tmp_path / "extra.json").write_text(json.dumps({
        "Extra": {"NESTED_INCLUDED": True}
    }))
    monkeypatch.chdir(tmp_path)

    cfg = pyconfix(schem_files=["main.json"], output_file=str(tmp_path / "out.json"))
    cfg.run(graphical=False)

    assert cfg._get("CHILD") is not None
    assert cfg._get("NESTED_INCLUDED") is not None
    assert cfg._get("NESTED_INCLUDED").option_type == ConfigOptionType.BOOL


def test_top_level_include_is_loaded(tmp_path, monkeypatch):
    # Guard: the common top-level include must keep working.
    (tmp_path / "main.json").write_text(json.dumps({
        "App": {"X": True, "include": ["extra.json"]}
    }))
    (tmp_path / "extra.json").write_text(json.dumps({"Extra": {"Y": True}}))
    monkeypatch.chdir(tmp_path)

    cfg = pyconfix(schem_files=["main.json"], output_file=str(tmp_path / "out.json"))
    cfg.run(graphical=False)
    assert cfg._get("Y") is not None


# --------------------------------------------------------------------------- #
# serializer: enum default coercion matches the direct ConfigOption path
# --------------------------------------------------------------------------- #

def test_schema_enum_out_of_range_default_is_coerced():
    opts = serializer.parse_options(Core(), {"E": {"choices": ["A", "B"], "default": "ZZZ"}})
    e = opts[0]
    assert e.option_type == ConfigOptionType.ENUM
    assert e.default == "A"          # coerced to first choice, like ConfigOption does
    assert e.value == 0


def test_schema_enum_valid_default_unaffected():
    opts = serializer.parse_options(Core(), {"E": {"choices": ["A", "B"], "default": "B"}})
    e = opts[0]
    assert e.default == "B"
    assert e.value == 1


def test_schema_enum_matches_direct_configoption_coercion():
    direct = ConfigOption(name="E", option_type=ConfigOptionType.ENUM,
                          choices=["A", "B"], default="ZZZ")
    via_schema = serializer.parse_options(
        Core(), {"E": {"choices": ["A", "B"], "default": "ZZZ"}})[0]
    assert (direct.default, direct.value) == (via_schema.default, via_schema.value)


# --------------------------------------------------------------------------- #
# curses-free headless guarantee
# --------------------------------------------------------------------------- #

def test_headless_path_never_imports_curses(tmp_path):
    (tmp_path / "sep.json").write_text(json.dumps(SCHEMA))
    script = textwrap.dedent("""
        import sys
        sys.modules['curses'] = None          # any 'import curses' now fails
        import pyconfix.core, pyconfix.serializer, pyconfix.runner
        from pyconfix import pyconfix as P
        cfg = P(schem_files=['sep.json'], output_file='out.json')
        cfg.run(graphical=False)              # load + apply, no TUI
        print(cfg.dump()['AN_INT'])
    """)
    result = subprocess.run([sys.executable, "-c", script],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("7")


def test_tui_is_the_curses_boundary(tmp_path):
    script = textwrap.dedent("""
        import sys
        sys.modules['curses'] = None
        try:
            import pyconfix.tui
        except (ImportError, AttributeError):
            print("tui-needs-curses")
        else:
            print("tui-imported")
    """)
    result = subprocess.run([sys.executable, "-c", script],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "tui-needs-curses"
