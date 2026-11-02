# pyconfix

[![Tests](https://github.com/NemesisWasAlienToo/pyconfig/actions/workflows/tests.yml/badge.svg)](https://github.com/NemesisWasAlienToo/pyconfig/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> The only automation tool you'll ever need.

Write your settings and tasks in one file. Pick your settings in a menu. Run your tasks from the menu or the command line.

```yaml
My Project:
  RELEASE: false
  TARGET: [linux, windows]

  BUILD:
    type: action
    default: echo "Building..."

  TEST:
    type: action
    needs: BUILD()
    default: echo "Testing..."

  DEPLOY:
    type: action
    deps: RELEASE && TARGET == linux
    needs: TEST()
    default: echo "Deploying..."
```

Save this as `pyconfixfile.yaml`, then open the menu:

```sh
pyconfix
```

Or run a task directly:

```sh
pyconfix --run DEPLOY -o RELEASE=true
```

```text
Building...
Testing...
Deploying...
```

## Contents

* [Features](#features)
* [Installation](#installation)
* [Command line](#command-line)
* [Menu keys](#menu-keys)
* [Options](#options)
* [Types](#types)
* [Fields](#fields)
* [Groups](#groups)
* [Include](#include)
* [Tasks](#tasks)
* [Running other tasks](#running-other-tasks)
* [Checks](#checks)
* [Aliases](#aliases)
* [Expressions](#expressions)
* [YAML](#yaml)
* [JSON](#json)
* [Python](#python)
  * [Minimal example](#minimal-example)
  * [Reading values](#reading-values)
  * [The session](#the-session)
  * [Splitting configs](#splitting-configs)
  * [Saving in any format](#saving-in-any-format)
  * [Conan](#conan)
  * [API reference](#api-reference)
* [New file formats](#new-file-formats)
* [Examples](#examples)
* [Roadmap](#roadmap)

## Features

* Settings: bool, int, string, enum and groups
* Tasks written as shell scripts or Python functions
* Tasks that run other tasks
* Options that turn on and off based on other options
* A terminal menu with search
* Schemas in YAML or JSON, or options in Python
* Aliases: reusable tasks and enums
* Checks that run when the schema loads
* Save your settings in any format
* Works with C/C++, CMake, Conan, Makefiles and anything else that reads a file

## Installation

```sh
pip install pyconfix[yaml]
```

Needs Python 3.11 or newer. Leave out `[yaml]` if you don't use YAML.

## Command line

| Command                       | What it does                 |
| ----------------------------- | ---------------------------- |
| `pyconfix`                    | Open the menu                |
| `pyconfix file.yaml`          | Use a specific schema        |
| `pyconfix --run NAME`         | Run a task                   |
| `pyconfix --run NAME -v`      | Also print its return value  |
| `pyconfix --run NAME -t`      | Also print the tasks it ran  |
| `pyconfix --print NAME`       | Print an option's value      |
| `pyconfix --dump`             | Print all values             |
| `pyconfix -o NAME=VALUE`      | Set a value for this run     |
| `pyconfix -l saved.json`      | Load saved settings          |
| `pyconfix --show-disabled`    | Show disabled options        |
| `pyconfix --version`          | Print the version            |

Without a file name, pyconfix looks for `pyconfixfile.json`, then `pyconfixfile.yaml`.

The menu saves to `pyconfix_output_config.json`. The next run loads it.

`--run` exits with 1 if the task fails, is disabled or doesn't exist. Otherwise it exits with 0.

## Menu keys

| Key    | What it does            |
| ------ | ----------------------- |
| ↑ / ↓  | Move                    |
| Enter  | Toggle or edit          |
| c      | Collapse or expand      |
| /      | Search                  |
| s      | Save                    |
| d      | Save only what changed  |
| Ctrl+D | Show description        |
| h      | Help                    |
| Ctrl+A | Cancel input            |
| q      | Quit                    |

## Options

A schema file has one top entry, which is the name of the config. Everything inside it is an option.

The type comes from the value.

**YAML**

```yaml
Main Config:
  ENABLED: true
  PORT: 8080
  HOST: localhost
  LOG_LEVEL: [DEBUG, INFO, ERROR]
```

**JSON**

```json
{
  "Main Config": {
    "ENABLED": true,
    "PORT": 8080,
    "HOST": "localhost",
    "LOG_LEVEL": ["DEBUG", "INFO", "ERROR"]
  }
}
```

**Python**

```python
from pyconfix import pyconfix, ConfigOption

config = pyconfix()
config.add_options(
    ConfigOption("ENABLED", True),
    ConfigOption("PORT", 8080),
    ConfigOption("HOST", "localhost"),
    ConfigOption("LOG_LEVEL", choices=["DEBUG", "INFO", "ERROR"]),
)
```

Option names can't contain spaces and must be unique across the whole config.

An enum starts at its first choice unless you set a `default`.

## Types

| Type       | Holds                                    |
| ---------- | ---------------------------------------- |
| `bool`     | true or false                            |
| `int`      | A whole number                           |
| `string`   | Text                                     |
| `enum`     | One of its choices                       |
| `group`    | Other options                            |
| `action`   | A task                                   |
| `external` | A read-only value                        |

Values are type checked. A wrong type raises an error. This also applies to saved files.

## Fields

Give an option more fields to describe it.

**YAML**

```yaml
Main Config:
  ENABLED: true

  LOG_LEVEL:
    default: INFO
    choices: [DEBUG, INFO, ERROR]
    desc: How much to log
    deps: ENABLED
```

**JSON**

```json
{
  "Main Config": {
    "ENABLED": true,
    "LOG_LEVEL": {
      "default": "INFO",
      "choices": ["DEBUG", "INFO", "ERROR"],
      "desc": "How much to log",
      "deps": "ENABLED"
    }
  }
}
```

**Python**

```python
from pyconfix import pyconfix, ConfigOption

config = pyconfix()
config.add_options(
    ConfigOption("ENABLED", True),
    ConfigOption(
        "LOG_LEVEL",
        default="INFO",
        choices=["DEBUG", "INFO", "ERROR"],
        description="How much to log",
        dependencies="ENABLED",
    ),
)
```

| YAML / JSON    | Short  | Python         | What it does                        |
| -------------- | ------ | -------------- | ----------------------------------- |
| `type`         |        | `option_type`  | The option's type                   |
| `default`      | `def`  | `default`      | The starting value, or a task       |
| `choices`      |        | `choices`      | The values of an enum               |
| `description`  | `desc` | `description`  | Shown in the menu with Ctrl+D       |
| `dependencies` | `deps` | `dependencies` | Disables the option when false      |
| `needs`        |        | `needs`        | Must be true before a task runs     |
| `options`      | `opts` | `options`      | The options inside a group          |
| `data`         |        | `data`         | Anything you want, for your own use |
| `do_not_cache` |        | `do_not_cache` | Recompute on every use              |

In a schema, you can't name an option after one of these fields, or `include` or `aliases`. This only applies to lowercase, so `TYPE` is fine.

## Groups

A group holds other options. Its `deps` and `needs` apply to everything inside it.

**YAML**

```yaml
Main Config:
  ENABLED: true

  Network:
    type: group
    deps: ENABLED
    options:
      HOST: localhost
      PORT: 8080
```

**JSON**

```json
{
  "Main Config": {
    "ENABLED": true,
    "Network": {
      "type": "group",
      "deps": "ENABLED",
      "options": {
        "HOST": "localhost",
        "PORT": 8080
      }
    }
  }
}
```

**Python**

```python
from pyconfix import pyconfix, ConfigOption

config = pyconfix()
config.add_options(
    ConfigOption("ENABLED", True),
    ConfigOption(
        "Network",
        dependencies="ENABLED",
        options=[
            ConfigOption("HOST", "localhost"),
            ConfigOption("PORT", 8080),
        ],
    ),
)
```

In YAML and JSON, a group with no fields of its own can be written by nesting:

```yaml
Main Config:
  Network:
    HOST: localhost
    PORT: 8080
```

## Include

Pull options in from somewhere else. They land where the `include` sits, so an `include` inside a group adds to that group.

The top entry of an included file is ignored. YAML and JSON can include each other.

**YAML**

```yaml
Main Config:
  ENABLED: true

  Network:
    HOST: localhost
    include: [network.yaml]

  include: [extras.json]
```

**JSON**

```json
{
  "Main Config": {
    "ENABLED": true,
    "Network": {
      "HOST": "localhost",
      "include": ["network.yaml"]
    },
    "include": ["extras.json"]
  }
}
```

**Python**

```python
from pyconfix import pyconfix, ConfigOption

database = pyconfix()
database.add_options(ConfigOption("DB_HOST", "localhost"))

web = pyconfix()
web.add_options(ConfigOption("WEB_PORT", 8080))

config = pyconfix()
config.include(database)                                      # at the top level
config.include(web, parent=config.group_option("web").get())  # inside a group
```

## Tasks

A task is an option with the type `action`. In a schema, its `default` is a script. In Python, it is a function or `shell_action`.

A script task returns true if the script exits with 0. A Python task fails if it returns `False`.

Scripts can't read option values yet. Python functions can.

**YAML**

```yaml
Main Config:
  BUILD:
    type: action
    desc: Compiles the project
    default: |
      set -e
      mkdir -p build
      echo done > build/result.txt
```

**JSON**

```json
{
  "Main Config": {
    "BUILD": {
      "type": "action",
      "desc": "Compiles the project",
      "default": "mkdir -p build && echo done > build/result.txt"
    }
  }
}
```

**Python**

```python
from pyconfix import pyconfix, ConfigOption, shell_action

config = pyconfix()

config.add_options(
    ConfigOption("BUILD", shell_action("mkdir -p build && echo done > build/result.txt")),
)

@config.action_option()
def clean(x):
    print("Cleaning...")
    return True
```

## Running other tasks

Use `needs` to run other tasks first. Add `()` to run a task.

Use `deps` to decide if an option is available. `deps` can't run tasks.

**YAML**

```yaml
Main Config:
  BUILD:
    type: action
    default: echo "Building..."

  TEST:
    type: action
    default: echo "Testing..."

  RELEASE:
    type: action
    needs: BUILD() && TEST()
    default: echo "Releasing..."
```

**JSON**

```json
{
  "Main Config": {
    "BUILD": { "type": "action", "default": "echo \"Building...\"" },
    "TEST": { "type": "action", "default": "echo \"Testing...\"" },
    "RELEASE": {
      "type": "action",
      "needs": "BUILD() && TEST()",
      "default": "echo \"Releasing...\""
    }
  }
}
```

**Python**

```python
from pyconfix import pyconfix

config = pyconfix()

@config.action_option()
def build(x):
    print("Building...")
    return True

@config.action_option()
def test(x):
    print("Testing...")
    return True

@config.action_option(needs="build() && test()")
def release(x):
    print("Releasing...")
    return True

config.release()
```

If `BUILD` fails, `TEST` and `RELEASE` don't run, and `RELEASE` returns false.

Each task runs once per run. Set `do_not_cache` to run it every time.

## Checks

An `external` option is a value from outside. You can't change it in the menu, and saved settings don't change it.

In a schema, its `default` is a script that runs when the schema loads. Its value is true if the script exits with 0. In Python, work out the value yourself.

**YAML**

```yaml
Main Config:
  HAS_DOCKER:
    type: external
    default: command -v docker

  CONTAINER_BUILD:
    type: action
    deps: HAS_DOCKER
    default: docker build .
```

**JSON**

```json
{
  "Main Config": {
    "HAS_DOCKER": { "type": "external", "default": "command -v docker" },
    "CONTAINER_BUILD": {
      "type": "action",
      "deps": "HAS_DOCKER",
      "default": "docker build ."
    }
  }
}
```

**Python**

```python
import shutil
from pyconfix import pyconfix, ConfigOption, ConfigOptionType, shell_action

config = pyconfix()
config.add_options(
    ConfigOption(
        "HAS_DOCKER",
        shutil.which("docker") is not None,
        option_type=ConfigOptionType.EXTERNAL,
    ),
    ConfigOption(
        "CONTAINER_BUILD",
        shell_action("docker build ."),
        dependencies="HAS_DOCKER",
    ),
)
```

## Aliases

An alias is a reusable type. It can be an enum or a task.

Any extra field on a task alias is an argument. A script reads it as an environment variable, so `text` becomes `$text`. Values set on the alias are defaults, and each option can change them.

**YAML**

```yaml
Main Config:
  aliases:
    tri-state:
      choices: [INTEGRATED, MODULE, DISABLED]
    say:
      type: action
      text: Hello
      default: echo "$text"

  USB_DRIVER:
    type: tri-state
    default: MODULE

  GREET:
    type: say

  GOODBYE:
    type: say
    text: Goodbye
```

**JSON**

```json
{
  "Main Config": {
    "aliases": {
      "tri-state": { "choices": ["INTEGRATED", "MODULE", "DISABLED"] },
      "say": {
        "type": "action",
        "text": "Hello",
        "default": "echo \"$text\""
      }
    },

    "USB_DRIVER": { "type": "tri-state", "default": "MODULE" },
    "GREET": { "type": "say" },
    "GOODBYE": { "type": "say", "text": "Goodbye" }
  }
}
```

**Python**

```python
from pyconfix import pyconfix, ConfigOptionType, shell_action

config = pyconfix()

config.register_alias(
    name="tri-state",
    option_type=ConfigOptionType.ENUM,
    choices=["INTEGRATED", "MODULE", "DISABLED"],
)

config.register_alias(
    name="say",
    option_type=ConfigOptionType.ACTION,
    default=shell_action('echo "$text"'),
    text="Hello",
)

config.add_options(
    config.option_from_alias("tri-state", name="USB_DRIVER", default="MODULE"),
    config.option_from_alias("say", name="GREET"),
    config.option_from_alias("say", name="GOODBYE", text="Goodbye"),
)
```

A Python function works too. It receives the arguments as keywords:

```python
from pyconfix import pyconfix, ConfigOptionType

def say(x, text):
    print(text)

config = pyconfix()
config.register_alias(name="say", option_type=ConfigOptionType.ACTION, default=say, text="Hello")
config.add_options(config.option_from_alias("say", name="GREET"))
```

This docker alias shows why they are useful:

```yaml
Main Config:
  aliases:
    docker:
      type: action
      image: debian:stable-slim
      default: docker run --rm -e script "$image" sh -c "$script"

  HELLO:
    type: docker
    script: echo "Hello from Debian"

  HELLO_ALPINE:
    type: docker
    image: alpine:3.20
    script: echo "Hello from Alpine"
```

* An alias can't use the name of a built-in type
* An alias name can only be registered once
* Aliases registered in Python work in a schema, if you register them before `load_schema`

## Expressions

`deps` and `needs` use the same expressions in YAML, JSON and Python:

```text
!DEBUG                        # not
DEBUG && PORT == 8080         # and
DEBUG || HOST == 'localhost'  # or
COUNT + 5 > LIMIT             # + - * / % **
OFFSET > -1                   # negative numbers
FLAGS & 0xFF == 0xAA          # & | ^ << >>
MASK ^ 0b1010                 # hex and binary
LOG_LEVEL == INFO             # enum choices
BUILD() && TEST()             # run tasks, in needs only
```

* Text goes in single quotes
* Enum choices are case sensitive
* A disabled option is `None`
* Doing math with `None` results in `None`
* `&&` and `||` stop as soon as they know the result

## YAML

Needs `pip install pyconfix[yaml]`. Use a `.yaml` or `.yml` file.

Save this as `pyconfixfile.yaml` and run `pyconfix`:

```yaml
My Project:
  ENABLED: true
```

Multi-line scripts are easy with `|`:

```yaml
My Project:
  BUILD:
    type: action
    default: |
      set -e
      mkdir -p build
      echo "Done"
```

* Keys must be text, so quote a key like `"on"`
* Dates stay as text

## JSON

Works with no extra install.

Save this as `pyconfixfile.json` and run `pyconfix`:

```json
{
  "My Project": {
    "ENABLED": true
  }
}
```

If a schema exists in both JSON and YAML, JSON wins.

Scripts are one string in JSON, so quote inner quotes with `\"`.

Saved settings are always JSON, whichever schema format you use.

## Python

### Minimal example

Without a schema:

```python
from pyconfix import pyconfix, ConfigOption

config = pyconfix()
config.add_options(ConfigOption("ENABLED", True))
config.run()
```

With a schema:

```python
from pyconfix import pyconfix

pyconfix().load_schema().apply_config().run()
```

`run()` opens the menu. Without it, nothing is shown.

In Python, `dependencies` and `needs` can be a string or a function:

```python
from pyconfix import pyconfix, ConfigOption

config = pyconfix()
config.add_options(
    ConfigOption("ENABLED", True),
    ConfigOption("PORT", 8080, dependencies="ENABLED"),
    ConfigOption("HOST", "localhost", dependencies=lambda x: x.ENABLED),
)
```

### Reading values

```python
from pyconfix import pyconfix

config = pyconfix().load_schema(["pyconfixfile.yaml"]).apply_config()

print(config.TARGET)                  # the value
print(config.get("TARGET"))           # the same
print(config.get("MISSING", "none"))  # with a fallback
print(config.get_option("TARGET"))    # the option itself
print(config.dump())                  # all values

value, trace = config.BUILD()         # run a task
```

`config.NAME` raises an error if the name doesn't exist. `config.get` returns the fallback.

### The session

Functions for `dependencies`, `needs` and tasks all receive a session, called `x` here. It works out each option once.

```python
from pyconfix import pyconfix, ConfigOption

config = pyconfix()
config.add_options(
    ConfigOption("LEVEL", choices=["DEBUG", "INFO"]),
    ConfigOption("test", lambda x: True),
)

@config.action_option()
def build(x):
    x.LEVEL                # a value
    x.get("LEVEL", "INFO") # a value with a fallback
    x.get_option("LEVEL")  # the option itself
    x.test()               # run a task
    x.config               # the config
```

Inside a session, a task returns its value. On the config, it returns `(value, trace)`.

You can make your own session. Call `invalidate_cache()` after changing a value:

```python
from pyconfix import pyconfix, ConfigOption

config = pyconfix()
config.add_options(ConfigOption("LEVEL", choices=["DEBUG", "INFO"]))

session = config.create_evaluation_session()
print(session.LEVEL)  # DEBUG

config.get_option("LEVEL").value = "INFO"
session.invalidate_cache()
print(session.LEVEL)  # INFO
```

Use one session per thread.

### Splitting configs

Use `group_option` to fill a group bit by bit, even from different files. Each part made with `pyconfix()` can still run on its own.

```python
from pyconfix import pyconfix, ConfigOption

config = pyconfix()
config.add_options(ConfigOption("ENABLED", True))

deploy = config.group_option("deploy", dependencies="ENABLED")
deploy.add_options(ConfigOption("REGION", "eu"))

@deploy.action_option()
def upload(x):
    print(f"Uploading to {x.REGION}")

config.upload()
```

### Saving in any format

Pass a `save_func` to write your settings in any format. It receives all the values.

```python
from pyconfix import pyconfix

def write_header(values):
    with open("config.h", "w") as f:
        for name, value in values.items():
            f.write(f"#define {name} {value}\n")

pyconfix().load_schema().apply_config().run(save_func=write_header)
```

To save without the menu:

```python
from pyconfix import pyconfix

config = pyconfix().load_schema().apply_config()
config.save("settings.json")
```

### Conan

Read your settings in a conanfile, so you only keep them in one place:

```python
from conan import ConanFile
from pyconfix import pyconfix

config = pyconfix().load_schema().apply_config()

class MyProject(ConanFile):
    name = "myproject"
    version = "1.0"
    options = {
        "release": [True, False],
        "target": ["linux", "windows"],
    }
    default_options = {
        "release": config.RELEASE,
        "target": config.TARGET,
    }
```

### API reference

Everything below is imported from `pyconfix`.

#### `pyconfix()`

| Method                                                                | What it does                               |
| --------------------------------------------------------------------- | ------------------------------------------ |
| `load_schema(schema_files=None)`                                        | Load schema files                          |
| `apply_config(config_files=None, overlay=None)`                       | Apply saved files, then a dict of values   |
| `run(output_file=..., show_disabled=False, save_func=None)`           | Open the menu                              |
| `save(output_file=..., output_diff=False, save_func=None)`            | Save without the menu                      |
| `include(other, parent=None)`                                         | Add the options of another config          |
| `add_options(*options, parent=None)`                                  | Add options, or add them to a group        |
| `action_option(name=None, dependencies=None, needs=None, do_not_cache=False)` | Decorator that adds a task         |
| `group_option(name, dependencies=None)`                               | Add a group                                |
| `register_alias(name, option_type, choices=None, default=None, **params)` | Define an alias                        |
| `option_from_alias(alias_name, name, **kwargs)`                       | Make an option from an alias               |
| `get(key, default=None)`                                              | Get a value, with a fallback               |
| `get_option(name)`                                                    | Get the option itself                      |
| `dump()`                                                              | All values as a dict                       |
| `diff()`                                                              | Only values that differ from their default |
| `create_evaluation_session()`                                         | Make a session                             |

* `output_file` defaults to `pyconfix_output_config.json`
* `load_schema`, `apply_config` and `include` return the config, so you can chain them
* `apply_config` raises an error if a file is missing
* `load_schema()` looks for `pyconfixfile`. `load_schema([])` loads nothing
* `save_func` receives a dict of values
* `option_from_alias` also takes a built-in type, like `"string"`
* `config.NAME` reads a value, and `config.NAME()` runs a task

`group_option` returns an object with these methods:

| Method                  | What it does              |
| ----------------------- | ------------------------- |
| `add_options(*options)` | Add options to the group  |
| `action_option(...)`    | Add a task to the group   |
| `get()`                 | Get the group option      |

#### `ConfigOption`

| Argument       | What it does                                     |
| -------------- | ------------------------------------------------ |
| `name`         | The option's name                                |
| `default`      | The starting value, or a task's function         |
| `option_type`  | The type. Worked out from the value if left out  |
| `data`         | Anything you want, for your own use              |
| `description`  | Shown in the menu with Ctrl+D                    |
| `dependencies` | A string or function that disables the option    |
| `options`      | The options inside a group                       |
| `choices`      | The values of an enum                            |
| `expanded`     | Shows a group open in the menu                   |
| `needs`        | A string or function checked before a task runs  |
| `do_not_cache` | Recompute on every use                           |
| Anything else  | An argument of a task                            |

An option also has:

| Attribute or method    | What it does                       |
| ---------------------- | ---------------------------------- |
| `value`                | The current value                  |
| `clone_with(**kwargs)` | A copy with some fields changed    |
| `to_dict()`            | The option's fields as a dict      |

#### `ConfigOptionType`

`BOOL`, `INT`, `STRING`, `ENUM`, `GROUP`, `ACTION` and `EXTERNAL`.

#### Session

| Method or attribute        | What it does                  |
| -------------------------- | ----------------------------- |
| `x.NAME`                   | Read a value                  |
| `x.NAME()`                 | Run a task                    |
| `x.get(key, default=None)` | Get a value, with a fallback  |
| `x.get_option(name)`       | Get the option itself         |
| `x.invalidate_cache()`     | Forget cached results         |
| `x.config`                 | The config                    |

#### Functions

| Function               | What it does                                                 |
| ---------------------- | ------------------------------------------------------------ |
| `find_schema(stem)`    | Find `stem.json`, then `stem.yaml`, then `stem.yml`. Raises if none exist |
| `shell_action(script)` | Make a task from a script                                    |

## New file formats

Each schema format is one file in `pyconfix/formats/`. Add a file and it is picked up.

```python
extensions = (".toml",)

def available():
    return True

def read(path):
    ...
```

* `extensions` lists the file extensions it handles
* `available` returns false if a library is missing
* `read` returns the file as a dict

## Examples

* __minimal_example.py__: the smallest runner
* __minimal_yaml_example.py__: the same with a YAML schema
* __extra_schem.yaml__: tasks, aliases and checks in YAML
* __example.py__: everything together

## Roadmap

* Let scripts read option values

Contributions are welcome. Fork it and send a PR.

---

© 2026 Nemesis – MIT License
