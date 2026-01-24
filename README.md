# pyconfix

> A single‑file, curses‑powered, highly customizable, menuconfig‑style configuration editor for any project.

---

## Why?

Do you need an interactive config menu like Linux menuconfig, but without C or a build step? pyconfix is forty kilobytes of pure Python you can drop into any repo—no external deps, no compilation. It also spits out JSON or Kconfig‑style header files, so it plugs straight into C/C++, CMake, Conan, Makefiles—anything that can consume a generated file.

---

## Features

* Hierarchical options – `bool`, `int`, `string`, `enum`, recursive groups.
* Boolean & arithmetic dependencies with logical operators `&&`, `||`, `!` (keyword forms `and`, `or`, `xor`), comparison/relational operators (`==`, `!=`, `>`, `>=`, `<`, `<=`), arithmetic expressions (`+`, `-`, `*`, `/`, `%`), and bitwise operators (`&`, `|`, `^`, `<<`, `>>`).
* Composable schemas – `"include"`: split large configs.
* Instant search (`/`).
* ⏹ Abort key – Ctrl+A exits search, input boxes etc.
* Live validation – options auto‑hide when dependencies fail.
* Pluggable save hook – write JSON, YAML, C headers, env‑files – whatever.
* Action options – define executable tasks with dependencies that can be run interactively or via CLI.
* 100% standard library (Windows users: `pip install windows‑curses`).

## Installation

```bash
pip install pyconfix
```
## Quick start

### Using the command

In order to use pyconfix in the most minimal and easy-to-use setup, just create a __pyconfixfile.json__ file inside the current working directory, add your options to it (example bellow) and run:

```sh
pyconfix
```

Here's an example of how the json file could look like:

```json
{
    "name": "Test Config",
    "options": [
        {
            "name": "ENABLE_FEATURE_A",
            "type": "bool",
            "default": true,
        },
        {
            "name": "DISABLED_BY_DEFAULT",
            "type": "bool",
            "default": false
        }
    ]
}
```

### Writing runner

A minimal pyconfix script that can be run and also serve as a starting point for further customizations could look like:

```python
# menu.py
from pyconfix import pyconfix
pyconfix().run()
```

Then run it:

```bash
python menu.py
```

Press `/` to search, Enter to toggle/edit, `s` to save, `q` to quit.
The minimal example could be found in the __minimal_example.py__ script. To see a frther customized version you can check out __example.py__ script which uses the __schem.json__ file which uses more advanced features like aliases and tasks.

### Custom save function

Want to emit something other than the default JSON? Pass a `save_func` callable when you create the instance. It receives the flattened config dict and the option tree, so you can write out any format you need:

```python
def write_header(cfg, config, is_diff):
    with open("config.h", "w") as f:
        for key, value in cfg.items():
            f.write(f"#define {key} {value}\n")

pyconfix(
    schem_files=["schem.json"],
    save_func=write_header,
).run()
```

## Headless / CLI mode

Run the schema parser non‑interactively to dump a JSON config – handy for scripts and pipelines:

```bash
python - <<'PY'
import pyconfix, json
cfg = pyconfix.pyconfix(
    schem_files=["schem.json"],
    output_file="cfg.json"
)
cfg.run(graphical=False, config_files=["prev.json"])
PY
```

## Python API

If you’d rather drive everything from code, import the class:

```python
from pyconfix import pyconfix

cfg = pyconfix(
    schem_files=["main.json", "extras.json"],
    config_files=["prev.json"],      # load an existing config (optional)
    output_file="final.json",     # where to write when you press "s"
    expanded=True,                 # expand all groups initially
    show_disabled=True             # show options that currently fail deps
)
cfg.run()                # interactive TUI
print(cfg.get("HOST")) # access a value programmatically
print(cfg.HOST) # The same as
```

Constructor signature for reference:

```python
pyconfix(
    schem_files: list[str] | None = ["pyconfixfile.json"],
    output_file: str = "output_config.json",
    save_func: Callable[[dict, "pyconfix", bool], None] | None = None,
    expanded: bool = False,
    show_disabled: bool = False,
)
```

## Actions

pyconfix supports defining `action` options that represent executable tasks. Each action can depend on other options or actions, and results are cached per execution chain.

### Defining actions

Actions must be defined via Python code:

```python
from pyconfix import pyconfix, ConfigOption

def build(x):
    print("Building...")
    return True

def deploy(x):
    print("Deploying...")
    return True

cfg = pyconfix(schem_files=["schem.json"], expanded=True, show_disabled=True)
cfg.options.extend([
    ConfigOption(
        name='build',
        option_type='action',
        description='Builds the software',
        dependencies='ENABLE_FEATURE_A',
        default=build,
        requires=lambda x: x.LOG_LEVEL
    ),
    ConfigOption(
        name='deploy',
        option_type='action',
        description='Deploys the software',
        dependencies='ENABLE_FEATURE_A',
        default=deploy,
        requires=lambda x: x.build()
    ),
])
```

### Running actions

* **Interactive mode**: Highlight an action in the TUI and press Enter. pyconfix will topologically sort and execute its dependencies, then the action itself, caching results.

* **CLI mode**: Use the `--run` flag:

  ```bash
  python menu.py --cli --run build
  ```

* **Programmatically**:

  ```python
  cfg.run(graphical=False)
  result = cfg.get("build")()
  # or simply
  result = cfg.build()
  ```

## Key bindings

| Action             | Key    |
| ------------------ | ------ |
| Navigate           | ↑ / ↓  |
| Toggle / edit      | Enter  |
| Collapse / expand  | c      |
| Search             | /      |
| Save               | s      |
| Show description   | Ctrl+D |
| Help               | h      |
| Abort search/input | Ctrl+A |
| Quit               | q      |

## Schema format

```json
{
  "name": "Main Config",
  "options": [
    { "name": "ENABLE_FEATURE_A", "type": "bool", "default": true },
    {
      "name": "LogLevel",
      "type": "enum",
      "default": "INFO",
      "choices": ["DEBUG", "INFO", "WARN", "ERROR"],
      "dependencies": "ENABLE_FEATURE_A"
    },
    { "name": "TIMEOUT", "type": "int", "default": 10, "dependencies": "ENABLE_FEATURE_A && LogLevel==DEBUG" },
    { "name": "Network", "type": "group", "options": [
      { "name": "HOST", "type": "string", "default": "localhost" }
    ]}
  ],
  "include": ["extra_schem.json"]
}
```

### Supported option types

| Type              | Notes                    |
| ----------------- | ------------------------ |
| `bool`            | `true` / `false`         |
| `int`             | any integer              |
| `string`          | unicode string           |
| `enum` | one value from `choices` |
| `group`           | nests other options      |
| `action`          | executable task option   |

### Aliases

You can register alias types (currently **ENUM** only) and reuse them in both JSON schema files and the Python API. This is useful for reusing common choice sets like tri-state options.

- Python usage: register the alias before loading the schema (or before `run()`), then create options from it:
```python
cfg.register_alias(
    name='tri-state', 
    option_type=ConfigOptionType.ENUM,
    choices=['INTEGRATED', 'MODULE', 'DISABLED']
)
```

> **Note:** Registering aliases is currently only available through the python API and only enum aliases are supported for now.

### Dependency syntax – cheatsheet

```text
!ENABLE_FEATURE_A                     # logical NOT
ENABLE_FEATURE_A && HOST=="dev"       # logical AND + comparison
TIMEOUT>5 || HOST=="localhost"        # logical OR  + relational
COUNT+5 > MAX_VALUE                   # addition + relational
SIZE-1 >= MIN_SIZE                    # subtraction + comparison
VALUE*2 == LIMIT                      # multiplication + equality
RATIO/3 < 1                           # division + relational
SIZE%4==0                             # modulus check
POWER**2 <= LIMIT                     # exponentiation + relational
BITS & 0xFF == 0xAA                   # bitwise AND + equality
FLAGS | FLAG_VERBOSE                  # bitwise OR
MASK ^ 0b1010                         # bitwise XOR
VALUE<<2 > 1024                       # left shift + relational
VALUE>>1 == 0                         # right shift + equality
```

## Advanced usage

```python
import json, pyconfix

def save_as_header(cfg, _):
    with open("config.h", "w") as f:
        for k, v in cfg.items():
            f.write(f"#define {k} {v}\n")

pyconfix.pyconfix(
    schem_files=["schem.json", "extras.json"],
    output_file="settings.json",
    save_func=save_as_header
).run()
```

## Export in any format
The configurations can be exported in any desirable format by using custom save functions. Here is an example pf the current configurations bein exported in the kconfig format:
```py
def custom_save(json_data, config, is_diff):
    with open("output_defconfig", 'w') as f:
        for key, value in json_data.items():
            if value == None or (isinstance(value, bool) and value == False):
                continue
            if isinstance(value, str):
                f.write(f"CONFIG_{key}=\"{value}\"\n")
            else:
                f.write(f"CONFIG_{key}={value if value != True else 'y'}\n")

# ...
# The rest of the code
# ...

config = pyconfix(schem_files=["schem.json"], save_func=custom_save)

# ...
# The rest of the code
# ...
```

## Practical remarks

There are multiple ways of attain the value of an option. Options can be treated as config's attributes or their value can be retrieved using the `get` function:

```py
config = pyconfix(schem_files=["schem.json"])
config.run()

# Options can be treated as attributes
print(f"{config.FEATURES_NAME}")
print(f"{config.ACTIONS_NAME()}")

# Options can be retrieved using `get` function
print(f"{config.get("FEATURES_NAME", False)}")
print(f"{config.get("ACTIONS_NAME", lambda: False)()}")
```

__IMPORTANT:__ The big difference between attribute syntax and `get` function is that in case of such an option not existing, the attribute syntax will throw an exception while the `get` function returns the default value provided to it.

## Conan integration example

THe recommended way of retrieving the settings in conan is to use the pyconfix to read and dump the current settings. If you are using the default command and the default config names this i trivial:

```python
# conanfile.py
from conan import ConanFile
from pyconfix import pyconfix

config = pyconfix()
config.run(graphical=False)

class MyProject(ConanFile):
    name = "myproject"
    version = "1.0"

    # The default options can also be parsed from config.options
    # but for this example we can just type them in
    options = {
        "feature_a": [True, False],
        "log_level": ["DEBUG", "INFO", "WARN", "ERROR"],
    }
    # This could also directly be parsed from config.dump()
    default_options = {
        "feature_a": bool(config.ENABLE_FEATURE_A),
        "log_level": bool(config.LOG_LEVEL),
    }
```

Or if you are using a customized script version, you can create and return your config in a function and use it in your conanfile. Let's assume that function is called __get_config__:

```python
# conanfile.py
from conan import ConanFile
from pyconfix import pyconfix

config = my_script.get_config()
config.run(graphical=False)

class MyProject(ConanFile):
    name = "myproject"
    version = "1.0"

    # The default options can also be parsed from config.options
    # but for this example we can just type them in
    options = {
        "feature_a": [True, False],
        "log_level": ["DEBUG", "INFO", "WARN", "ERROR"],
    }
    # This could also directly be parsed from config.dump()
    default_options = {
        "feature_a": bool(config.ENABLE_FEATURE_A),
        "log_level": bool(config.LOG_LEVEL),
    }
```

This eliminates the need to sync up the customized settings inside the conanfile and running script.
You could also just read the config json files directly and this might be less complex, but then the file names needs to stay sync if a custom runner script is used:

```python
# conanfile.py
from conan import ConanFile
import os, json

_cfg = {}
try:
    with open(os.getenv("CFG", "settings.json")) as f:
        _cfg = json.load(f)
except FileNotFoundError:
    pass

class MyProject(ConanFile):
    name = "myproject"
    version = "1.0"
    options = {
        "feature_a": [True, False],
        "log_level": ["DEBUG", "INFO", "WARN", "ERROR"],
    }
    default_options = {
        "feature_a": bool(_cfg.ENABLE_FEATURE_A),
        "log_level": bool(_cfg.LOG_LEVEL),
    }
```

Call it with:

```bash
python pyconfix.py              # produce settings.json
CFG=settings.json conan install .
```

## Roadmap

* Add unit tests + GitHub Actions CI
* Cache dependency evaluation for massive configs

Contributions are welcome – fork, hack, send PRs!

---

© 2025 Nemesis – MIT License
