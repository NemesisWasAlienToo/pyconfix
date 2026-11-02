"""Every example must keep working, so they are run here in a temporary copy."""

import importlib
import json
import os
import runpy
import shutil
import subprocess
import sys

import pytest

from pyconfix import pyconfix

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
EXAMPLES = os.path.join(ROOT, "examples")

pytest.importorskip("yaml")


@pytest.fixture
def example(tmp_path, monkeypatch):
    def enter(name):
        folder = tmp_path / name
        shutil.copytree(os.path.join(EXAMPLES, name), folder)
        monkeypatch.chdir(folder)
    return enter


def cli(*args):
    env = {**os.environ, "PYTHONPATH": ROOT}
    return subprocess.run([sys.executable, "-m", "pyconfix", *args],
                          capture_output=True, text=True, env=env)


def test_every_example_is_listed_and_has_a_readme():
    with open(os.path.join(EXAMPLES, "README.md"), encoding="utf-8") as f:
        readme = f.read()
    for name in os.listdir(EXAMPLES):
        if os.path.isdir(os.path.join(EXAMPLES, name)) and name != "__pycache__":
            assert f"[{name}]({name})" in readme
            assert os.path.exists(os.path.join(EXAMPLES, name, "README.md"))


@pytest.mark.parametrize("name", [
    "minimal", "options", "dependencies", "tasks", "aliases", "checks", "include", "export",
])
def test_schema_examples_load(example, name):
    example(name)
    assert pyconfix().load_schema().apply_config().dump()


def test_yaml_minimal_loads(example):
    example("minimal")
    runpy.run_path("minimal_yaml_example.py")   # the guard keeps the menu closed
    assert pyconfix().load_schema(["schema.yaml"]).ENABLE_FEATURE_A is True


def test_dependencies_follow_the_values(example):
    example("dependencies")
    config = pyconfix().load_schema()
    assert config.LOG_FILE is None
    config.apply_config(overlay={"LOG_LEVEL": "DEBUG"})
    assert config.LOG_FILE == "debug.log"
    config.apply_config(overlay={"ENABLE_LOGGING": False})
    assert config.LOG_FILE is None
    assert config.ROTATE is None


def test_tasks_need_a_release(example):
    example("tasks")
    assert cli("--run", "DEPLOY").returncode == 1
    result = cli("--run", "DEPLOY", "-o", "RELEASE=true")
    assert result.returncode == 0
    assert result.stdout.split("\n")[-4:-1] == ["Build done", "Testing...", "Deploying..."]


def test_aliases_from_their_own_file(example):
    example("aliases")
    assert pyconfix().load_schema().USB_DRIVER == "MODULE"
    assert cli("--run", "GREET").stdout == "Hello\n"
    assert cli("--run", "GOODBYE").stdout == "Goodbye\n"


def test_checks_run_at_load(example):
    example("checks")
    config = pyconfix().load_schema()
    assert config.HAS_GIT == (shutil.which("git") is not None)
    assert config.HAS_DOCKER == (shutil.which("docker") is not None)


def test_include_places_options(example):
    example("include")
    config = pyconfix().load_schema()
    network = config.get_option("Network")
    assert [option.name for option in network.options] == ["HOST", "PORT", "PROXY"]
    assert config.EXTRA_FEATURE is False


def test_python_example(example):
    example("python")
    config = runpy.run_path("menu.py")["create_config"]()
    assert config.config_name == "Python"
    assert config.deploy() == (True, ["deploy", "build"])
    config.apply_config(overlay={"TARGET": "windows"})
    assert config.deploy() == (None, [])


def test_export_writes_a_header(example):
    example("export")
    runpy.run_path("export.py", run_name="__main__")
    with open("output_config.h", encoding="utf-8") as f:
        assert f.read() == "#define MAX_USERS 100\n#define TIMEOUT 30\n"
    with open("pyconfix_output_config.json", encoding="utf-8") as f:
        assert json.load(f) == {"MAX_USERS": 100, "TIMEOUT": 30}


def test_everything_example_loads(example, monkeypatch):
    example("everything")
    monkeypatch.syspath_prepend(os.getcwd())
    sys.modules.pop("example", None)
    sys.modules.pop("database_module", None)
    config = importlib.import_module("example").create_config()
    assert config.dump()
    assert config.migrate()[0] is True
    sys.modules.pop("example", None)
    sys.modules.pop("database_module", None)
