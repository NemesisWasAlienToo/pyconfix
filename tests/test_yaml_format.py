"""YAML schema files, and PyYAML staying optional."""

import builtins
import json
import os
import subprocess
import sys

import pytest

from pyconfix import pyconfix, ConfigOptionType, find_schema, serializer
from pyconfix import __main__ as cli
from pyconfix import yaml_format

SCHEMA = """
Main:
  ENABLED: true
  COUNT:
    default: 3
    deps: ENABLED
  LEVEL:
    default: INFO
    choices: [DEBUG, INFO]
  RELEASED: 2024-01-01
  G:
    type: group
    deps: "!ENABLED"
    options:
      CHILD: 5
"""


@pytest.fixture
def load(tmp_path, monkeypatch):
    pytest.importorskip("yaml")
    monkeypatch.chdir(tmp_path)

    def _load(text, name="schema.yaml"):
        (tmp_path / name).write_text(text)
        return pyconfix().load_schem([name])
    return _load


@pytest.mark.parametrize("name", ["schema.yaml", "schema.yml", "SCHEMA.YAML"])
def test_schema_loads_from_yaml(load, name):
    cfg = load(SCHEMA, name)
    assert cfg.config_name == "Main"
    assert cfg.COUNT == 3
    assert cfg.LEVEL == "INFO"
    assert cfg.CHILD is None


def test_yaml_and_json_schemas_build_the_same_options(load, tmp_path):
    from_yaml = load("Main:\n  N: 1\n  F:\n    default: true\n    deps: N > 0\n")
    (tmp_path / "schema.json").write_text(json.dumps(
        {"Main": {"N": 1, "F": {"default": True, "deps": "N > 0"}}}))
    from_json = pyconfix().load_schem(["schema.json"])
    assert from_yaml.dump() == from_json.dump()


def test_yaml_date_stays_a_string(load):
    cfg = load(SCHEMA)
    assert cfg.RELEASED == "2024-01-01"
    assert cfg.get_option("RELEASED").option_type == ConfigOptionType.STRING


def test_yaml_include_can_mix_formats(load, tmp_path):
    (tmp_path / "extra.yml").write_text("Extra:\n  FROM_YAML: 1\n")
    (tmp_path / "extra.json").write_text(json.dumps({"Extra": {"FROM_JSON": 2}}))
    cfg = load("Main:\n  include: [extra.yml, extra.json]\n")
    assert (cfg.FROM_YAML, cfg.FROM_JSON) == (1, 2)


def test_state_is_still_saved_as_json(load, tmp_path):
    cfg = load("Main:\n  N: 1\n")
    cfg.save("out.json")
    assert json.loads((tmp_path / "out.json").read_text()) == {"N": 1}


def test_saved_json_state_loads_back_on_a_yaml_schema(load, tmp_path):
    cfg = load("Main:\n  N: 1\n")
    (tmp_path / "state.json").write_text(json.dumps({"N": 9}))
    assert cfg.apply_config(config_files=["state.json"]).N == 9


@pytest.mark.parametrize("text", [
    "",
    "# only a comment\n",
    "- a\n- b\n",
    "just a string\n",
    "Main: [unclosed\n",
    "on: 1\n",
    "Main:\n  1: 2\n",
    "Main:\n  G:\n    options:\n      yes: 1\n",
    "Main:\n",
])
def test_malformed_yaml_raises_value_error_naming_the_file(load, text):
    with pytest.raises(ValueError, match="schema.yaml"):
        load(text)


def test_unquoted_on_off_choices_are_rejected(load):
    with pytest.raises(ValueError, match="POWER"):
        load("Main:\n  POWER:\n    choices: [on, off]\n")


def test_quoted_on_off_choices_work(load):
    assert load('Main:\n  POWER:\n    choices: ["on", "off"]\n').POWER == "on"


def test_yaml_cannot_run_code(load):
    with pytest.raises(ValueError, match="schema.yaml"):
        load("Main: !!python/object/apply:os.system [echo]\n")


def test_missing_pyyaml_gives_a_clear_error(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def no_yaml(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_yaml)
    monkeypatch.delitem(sys.modules, "yaml", raising=False)
    path = tmp_path / "schema.yaml"
    path.write_text("Main: {}\n")
    with pytest.raises(ImportError, match=r"pyconfix\[yaml\]"):
        serializer.read(str(path))


def test_json_only_use_never_imports_yaml(tmp_path):
    (tmp_path / "schema.json").write_text(json.dumps({"S": {"N": 1}}))
    code = (
        "import sys; from pyconfix import pyconfix; "
        "c = pyconfix().load_schem(['schema.json']); "
        "print(c.N, 'yaml' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True,
                         text=True, env={"PYTHONPATH": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))})
    assert out.stdout.split() == ["1", "False"], out.stderr


def test_only_yaml_format_mentions_yaml():
    assert yaml_format.YamlFormat.extensions == (".yaml", ".yml")
    assert not hasattr(serializer, "yaml")


@pytest.mark.parametrize("existing, expected", [
    (["s.json", "s.yaml", "s.yml"], "s.json"),
    (["s.yaml", "s.yml"], "s.yaml"),
    (["s.yml"], "s.yml"),
])
def test_find_schema_prefers_json_then_yaml(tmp_path, monkeypatch, existing, expected):
    monkeypatch.chdir(tmp_path)
    for name in existing:
        (tmp_path / name).write_text("")
    assert find_schema("s") == expected


def run_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["pyconfix", "--dump"])
    cli.main()
    return capsys.readouterr().out


def test_extensions_are_oldest_format_first():
    assert serializer.extensions()[:3] == [".json", ".yaml", ".yml"]


def test_available_extensions_leave_out_yaml_without_pyyaml(monkeypatch):
    hide_pyyaml(monkeypatch)
    assert serializer.available_extensions() == [".json"]


def test_serializer_knows_nothing_about_finding_schemas():
    assert not hasattr(serializer, "find_schema")
    assert not hasattr(serializer, "find_file")


def test_cli_finds_yaml_schema(tmp_path, monkeypatch, capsys):
    pytest.importorskip("yaml")
    (tmp_path / "pyconfixfile.yaml").write_text("Main:\n  FROM_YAML: 1\n")
    assert "FROM_YAML" in run_cli(tmp_path, monkeypatch, capsys)


def test_cli_prefers_json_schema(tmp_path, monkeypatch, capsys):
    (tmp_path / "pyconfixfile.yaml").write_text("Main:\n  FROM_YAML: 1\n")
    (tmp_path / "pyconfixfile.json").write_text(json.dumps({"Main": {"FROM_JSON": 1}}))
    out = run_cli(tmp_path, monkeypatch, capsys)
    assert "FROM_JSON" in out and "FROM_YAML" not in out


def test_cli_without_a_schema_lists_what_it_looked_for(tmp_path, monkeypatch, capsys):
    with pytest.raises(ValueError, match="pyconfixfile.json"):
        run_cli(tmp_path, monkeypatch, capsys)


def test_load_schem_finds_yaml_by_default(tmp_path, monkeypatch):
    pytest.importorskip("yaml")
    (tmp_path / "pyconfixfile.yml").write_text("Main:\n  N: 1\n")
    monkeypatch.chdir(tmp_path)
    assert pyconfix().load_schem().N == 1


def test_load_schem_prefers_json_by_default(tmp_path, monkeypatch):
    (tmp_path / "pyconfixfile.yaml").write_text("Main:\n  N: 1\n")
    (tmp_path / "pyconfixfile.json").write_text(json.dumps({"Main": {"N": 2}}))
    monkeypatch.chdir(tmp_path)
    assert pyconfix().load_schem().N == 2


def test_load_schem_with_empty_list_loads_nothing(tmp_path, monkeypatch):
    (tmp_path / "pyconfixfile.json").write_text(json.dumps({"Main": {"N": 2}}))
    monkeypatch.chdir(tmp_path)
    assert pyconfix().load_schem([]).options == []


def test_explicit_missing_schema_names_that_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="other.yaml"):
        pyconfix().load_schem(["other.yaml"])


def hide_pyyaml(monkeypatch):
    real = yaml_format.importlib.util.find_spec
    monkeypatch.setattr(yaml_format.importlib.util, "find_spec",
                        lambda name, *a: None if name == "yaml" else real(name, *a))


def test_missing_schema_message_offers_yaml_when_installed(tmp_path, monkeypatch):
    pytest.importorskip("yaml")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError) as e:
        pyconfix().load_schem()
    assert str(e.value) == (
        "No schema file found, looked for: "
        "pyconfixfile.json, pyconfixfile.yaml, pyconfixfile.yml")


def test_missing_schema_message_hides_yaml_when_not_installed(tmp_path, monkeypatch):
    hide_pyyaml(monkeypatch)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError) as e:
        pyconfix().load_schem()
    assert str(e.value) == "No schema file found, looked for: pyconfixfile.json"


def test_yaml_file_without_pyyaml_still_found_and_asks_for_it(tmp_path, monkeypatch):
    hide_pyyaml(monkeypatch)
    (tmp_path / "s.yaml").write_text("Main: {}\n")
    monkeypatch.chdir(tmp_path)
    assert find_schema("s") == "s.yaml"
