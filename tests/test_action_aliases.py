"""Action aliases: reusable actions with arguments, in schemas and in Python."""

import json

import pytest

from pyconfix import pyconfix, Core, ConfigOption, ConfigOptionType, shell_action
from pyconfix.schema import parse_options

ACTION = ConfigOptionType.ACTION
WRITE = 'echo "$message" >> out.txt'


def schema(aliases, **options):
    return {"aliases": aliases, **options}


def lines(tmp_path):
    out = tmp_path / "out.txt"
    return out.read_text().splitlines() if out.exists() else []


@pytest.fixture
def load(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def _load(data):
        (tmp_path / "schema.json").write_text(json.dumps({"Main": data}))
        return pyconfix().load_schema(["schema.json"])
    return _load


ALIAS = {"say": {"type": "action", "default": WRITE}}


def test_schema_alias_passes_its_argument(load, tmp_path):
    cfg = load(schema(ALIAS, HI={"type": "say", "message": "hello"}))
    assert cfg.HI() == (True, ["HI"])
    assert lines(tmp_path) == ["hello"]


def test_alias_is_shared_by_several_actions(load, tmp_path):
    cfg = load(schema(ALIAS,
                      A={"type": "say", "message": "one"},
                      B={"type": "say", "message": "two"}))
    cfg.A()
    cfg.B()
    assert lines(tmp_path) == ["one", "two"]


def test_alias_defined_after_its_use_in_the_file(load, tmp_path):
    cfg = load({"HI": {"type": "say", "message": "hello"}, "aliases": ALIAS})
    cfg.HI()
    assert lines(tmp_path) == ["hello"]


@pytest.mark.parametrize("value", [
    "two words", "it\'s", 'say "hi"', "$HOME", "a; touch hacked", "`touch hacked`",
])
def test_argument_is_never_run_as_shell(load, tmp_path, value):
    cfg = load(schema(ALIAS, HI={"type": "say", "message": value}))
    cfg.HI()
    assert lines(tmp_path) == [value]
    assert not (tmp_path / "hacked").exists()


def test_multi_line_argument_is_kept(load, tmp_path):
    cfg = load(schema(ALIAS, HI={"type": "say", "message": "one\ntwo"}))
    cfg.HI()
    assert lines(tmp_path) == ["one", "two"]


@pytest.mark.parametrize("name", ["script", "SCRIPT", "Script", "_my_arg2"])
def test_param_names_are_used_exactly_as_written(load, tmp_path, name):
    alias = {"say": {"type": "action", "default": f'echo "${name}" >> out.txt'}}
    cfg = load(schema(alias, HI={"type": "say", name: "hello"}))
    cfg.HI()
    assert lines(tmp_path) == ["hello"]


def test_param_default_is_used_and_can_be_overridden(load, tmp_path):
    alias = {"say": {"type": "action", "message": "fallback", "default": WRITE}}
    cfg = load(schema(alias, A={"type": "say"}, B={"type": "say", "message": "mine"}))
    cfg.A()
    cfg.B()
    assert lines(tmp_path) == ["fallback", "mine"]


def test_non_string_argument_reaches_the_script(load, tmp_path):
    cfg = load(schema(ALIAS, HI={"type": "say", "message": 5}))
    cfg.HI()
    assert lines(tmp_path) == ["5"]


def test_failing_alias_script_returns_false(load):
    alias = {"fail": {"type": "action", "default": "exit 1"}}
    assert load(schema(alias, F={"type": "fail"})).F()[0] is False


def test_loading_runs_nothing(load, tmp_path):
    load(schema(ALIAS, HI={"type": "say", "message": "x"}))
    assert lines(tmp_path) == []


def test_alias_option_works_with_deps_and_needs(load, tmp_path):
    cfg = load(schema(
        ALIAS,
        ON=True,
        HI={"type": "say", "message": "hi", "deps": "ON"},
        BYE={"type": "say", "message": "bye", "needs": "HI()"},
    ))
    assert cfg.BYE() == (True, ["BYE", "HI"])
    assert lines(tmp_path) == ["hi", "bye"]
    cfg.get_option("ON").value = False
    assert cfg.HI() == (None, [])


def test_alias_can_carry_deps_for_its_actions(load):
    alias = {"say": {"type": "action", "default": WRITE, "deps": "ON"}}
    cfg = load(schema(alias, ON=False, HI={"type": "say", "message": "x"}))
    assert cfg.HI() == (None, [])


def test_alias_action_is_not_saved(load):
    assert load(schema(ALIAS, HI={"type": "say", "message": "x"})).dump() == {}


def test_enum_alias_in_schema(load):
    cfg = load(schema({"tri": {"type": "enum", "choices": ["A", "B"]}}, T={"type": "tri", "default": "B"}))
    assert cfg.T == "B"


def test_alias_from_an_included_file(load, tmp_path):
    (tmp_path / "lib.json").write_text(json.dumps({"Lib": {"aliases": ALIAS}}))
    cfg = load({"include": ["lib.json"]})
    assert "say" in cfg.aliases


@pytest.mark.parametrize("name", ["aliases"])
def test_aliases_is_reserved(name):
    with pytest.raises(ValueError):
        parse_options(Core(), {name: True})


def test_extra_fields_on_an_enum_alias_are_rejected(load):
    with pytest.raises(ValueError, match="T"):
        load(schema({"tri": {"type": "enum", "choices": ["A"]}}, T={"type": "tri", "a": 1}))


def test_extra_fields_on_an_enum_alias_definition_are_rejected(load):
    with pytest.raises(ValueError, match="tri"):
        load(schema({"tri": {"type": "enum", "choices": ["A"], "a": 1}}))


def test_argument_on_an_option_overrides_only_that_argument(load, tmp_path):
    alias = {"say": {"type": "action", "first": "a", "second": "b",
                     "default": 'echo "$first$second" >> out.txt'}}
    cfg = load(schema(alias, S={"type": "say", "second": "z"}))
    cfg.S()
    assert lines(tmp_path) == ["az"]


def test_reserved_fields_are_not_arguments(load):
    cfg = load(schema(ALIAS, S={"type": "say", "message": "x", "description": "d"}))
    assert cfg.get_option("S").description == "d"


def test_clone_with_binds_extra_keywords_as_params():
    option = ConfigOption("A", option_type=ACTION, default=lambda x, a, b: (a, b), b=2)
    clone = option.clone_with(name="B", a=1)
    assert clone.name == "B"
    assert clone.default(None) == (1, 2)


def test_clone_with_overrides_a_param():
    option = ConfigOption("A", option_type=ACTION, default=lambda x, a: a, a=1)
    assert option.clone_with(a=2).default(None) == 2
    assert option.default(None) == 1


def test_constructor_binds_extra_keywords_as_params():
    option = ConfigOption("A", option_type=ACTION, default=lambda x, a: a, a=1)
    assert option.default(None) == 1


def test_invalid_param_name_on_an_option_using_an_alias_fails_on_load(load):
    with pytest.raises(ValueError, match="my-arg"):
        load(schema(ALIAS, HI={"type": "say", "my-arg": "x"}))


def test_clone_with_extra_keyword_on_a_plain_option_raises():
    with pytest.raises(ValueError, match="X"):
        ConfigOption("X", 1).clone_with(a=1)


@pytest.mark.parametrize("name", ["my-arg", "1st", "two words"])
def test_invalid_param_name_is_rejected(name):
    with pytest.raises(ValueError, match="X"):
        ConfigOption("X", option_type=ACTION, default=lambda x: 1, **{name: 1})


def test_params_only_on_actions():
    with pytest.raises(ValueError, match="X"):
        ConfigOption("X", 1, a=1)


def test_other_alias_types_stay_rejected():
    with pytest.raises(ValueError):
        Core().register_alias("x", ConfigOptionType.BOOL, default=True)


# Python API

def test_python_alias_with_a_function():
    cfg = pyconfix()
    cfg.register_alias("add", ACTION, default=lambda x, a, b: a + b)
    cfg.add_options(cfg.option_from_alias("add", name="SUM", a=1, b=2))
    assert cfg.SUM() == (3, ["SUM"])


def test_python_function_alias_can_read_the_session():
    cfg = pyconfix()
    cfg.add_options(ConfigOption("BASE", 10))
    cfg.register_alias("add", ACTION, default=lambda x, a: x.BASE + a)
    cfg.add_options(cfg.option_from_alias("add", name="SUM", a=1))
    assert cfg.SUM()[0] == 11


def test_python_alias_with_a_script(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = pyconfix()
    cfg.register_alias("say", ACTION, default=shell_action(WRITE))
    cfg.add_options(cfg.option_from_alias("say", name="HI", message="hello"))
    assert cfg.HI()[0] is True
    assert lines(tmp_path) == ["hello"]


def test_python_alias_is_usable_from_a_schema(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "schema.json").write_text(json.dumps(
        {"Main": {"SUM": {"type": "add", "a": 2}}}))
    cfg = pyconfix()
    cfg.register_alias("add", ACTION, default=lambda x, a: a + 1)
    cfg.load_schema(["schema.json"])
    assert cfg.SUM()[0] == 3


def test_python_alias_default_argument():
    cfg = pyconfix()
    cfg.register_alias("pair", ACTION, default=lambda x, a, b: (a, b), b=2)
    cfg.add_options(cfg.option_from_alias("pair", name="P", a=1))
    assert cfg.P()[0] == (1, 2)


def test_python_alias_without_arguments():
    cfg = pyconfix()
    cfg.register_alias("one", ACTION, default=lambda x: 1)
    cfg.add_options(cfg.option_from_alias("one", name="O"))
    assert cfg.O()[0] == 1


def test_alias_action_runs_in_a_group():
    cfg = pyconfix()
    cfg.register_alias("one", ACTION, default=lambda x: 1)
    group = cfg.group_option("G", dependencies=lambda x: False)
    group.add_options(cfg.option_from_alias("one", name="O"))
    assert cfg.O() == (None, [])


def test_alias_name_cannot_be_a_builtin_type():
    with pytest.raises(ValueError):
        Core().register_alias("action", ACTION, default=lambda x: 1)


# External options computed by a script

@pytest.mark.parametrize("script, expected", [("true", True), ("false", False), ("exit 3", False)])
def test_external_script_gives_its_result(load, script, expected):
    assert load({"X": {"type": "external", "default": script}}).X is expected


def test_external_script_gates_an_alias_action(load, tmp_path):
    cfg = load(schema(
        ALIAS,
        NOPE={"type": "external", "default": "command -v no-such-program-here"},
        HI={"type": "say", "message": "x", "deps": "NOPE"},
    ))
    assert cfg.HI() == (None, [])
    assert lines(tmp_path) == []


def test_external_script_output_is_hidden(load, capfd):
    load({"X": {"type": "external", "default": "echo noise; echo noise >&2"}})
    assert capfd.readouterr() == ("", "")


@pytest.mark.parametrize("value", [True, False, 7])
def test_external_value_that_is_not_a_string_stays_literal(load, value):
    assert load({"X": {"type": "external", "default": value}}).X == value


def test_python_external_string_stays_literal():
    core = Core()
    core.add_options(ConfigOption("X", "exit 1", option_type=ConfigOptionType.EXTERNAL))
    assert core.X == "exit 1"


def test_external_script_can_span_several_lines(load):
    assert load({"X": {"type": "external", "default": "false\ntrue\n"}}).X is True


def test_alias_param_may_be_called_script(load, tmp_path):
    alias = {"run": {"type": "action", "default": 'sh -c "$script"'}}
    cfg = load(schema(alias, GO={"type": "run", "script": "echo ok >> out.txt"}))
    cfg.GO()
    assert lines(tmp_path) == ["ok"]


def tri_state_config():
    cfg = pyconfix()
    cfg.register_alias(name="tri", option_type=ConfigOptionType.ENUM, choices=["A", "B"])
    return cfg


def test_include_imports_aliases():
    other = tri_state_config()
    other.add_options(other.option_from_alias("tri", name="OLD"))

    cfg = pyconfix().include(other)
    cfg.add_options(cfg.option_from_alias("tri", name="NEW", default="B"))
    assert cfg.OLD == "A"
    assert cfg.NEW == "B"


def test_include_of_a_config_with_only_aliases():
    cfg = pyconfix().include(tri_state_config())
    cfg.add_options(cfg.option_from_alias("tri", name="NEW"))
    assert cfg.NEW == "A"


def test_included_aliases_work_in_a_schema(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "s.json").write_text('{"M": {"NEW": {"type": "tri"}}}')
    assert pyconfix().include(tri_state_config()).load_schema(["s.json"]).NEW == "A"


def test_include_refuses_a_duplicate_alias_and_changes_nothing():
    other = tri_state_config()
    other.add_options(ConfigOption("OPT", 1))
    cfg = tri_state_config()
    with pytest.raises(ValueError, match="already exists"):
        cfg.include(other)
    assert cfg.get_option("OPT") is None


def test_a_failed_include_adds_no_aliases():
    other = tri_state_config()
    other.add_options(ConfigOption("OPT", 1))
    cfg = pyconfix()
    cfg.add_options(ConfigOption("OPT", 2))
    with pytest.raises(ValueError, match="Duplicate"):
        cfg.include(other)
    assert cfg.aliases == {}
