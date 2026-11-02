import json

from pyconfix import pyconfix, ConfigOption, ConfigOptionType


def external(value=True):
    return ConfigOption("HAS_TOOL", value, option_type=ConfigOptionType.EXTERNAL)


def test_a_saved_file_does_not_override_an_external(tmp_path):
    saved = tmp_path / "saved.json"
    saved.write_text(json.dumps({"HAS_TOOL": False}))
    config = pyconfix()
    config.add_options(external())
    config.apply_config([str(saved)])
    assert config.HAS_TOOL is True


def test_an_overlay_does_not_override_an_external():
    config = pyconfix()
    config.add_options(external())
    config.apply_config(overlay={"HAS_TOOL": False})
    assert config.HAS_TOOL is True


def test_an_external_inside_a_group_is_also_skipped():
    config = pyconfix()
    config.add_options(ConfigOption("GROUP", options=[external()]))
    config.apply_config(overlay={"HAS_TOOL": False})
    assert config.HAS_TOOL is True


def test_other_options_are_still_applied():
    config = pyconfix()
    config.add_options(external(), ConfigOption("PORT", 1))
    config.apply_config(overlay={"HAS_TOOL": False, "PORT": 2})
    assert config.PORT == 2


def test_a_schema_check_runs_again_after_a_save(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "s.json").write_text(json.dumps({"M": {
        "HAS_TOOL": {"type": "external", "default": "test -e tool"},
    }}))
    (tmp_path / "tool").touch()
    pyconfix().load_schema(["s.json"]).save("saved.json")
    assert json.loads((tmp_path / "saved.json").read_text()) == {"HAS_TOOL": True}

    (tmp_path / "tool").unlink()
    config = pyconfix().load_schema(["s.json"]).apply_config(["saved.json"])
    assert config.HAS_TOOL is False
