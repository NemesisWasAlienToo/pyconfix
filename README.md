# pyconfix

> A single‑file, curses‑powered, highly customizable, menuconfig‑style configuration editor for any project.

---

## Why?

Do you need an interactive config menu like Linux menuconfig, but without C or a build step? pyconfix is forty kilobytes of pure Python you can drop into any repo—no external deps, no compilation. It also spits out JSON or Kconfig‑style header files, so it plugs straight into C/C++, CMake, Conan, Makefiles—anything that can consume a generated file.

---

## Features

* Hierarchical options – `bool`, `int`, `string`, `multiple_choice`, recursive groups.
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

---

## Quick start

Create a tiny launcher script first:

```python
# menu.py
import pyconfix

pyconfix.pyconfix(schem_file=["schem.json"]).run()
```

Then run it:

```bash
python menu.py
```

Press `/` to search, Enter to toggle/edit, `s` to save, `q` to quit.

## Headless / CI mode

Run the schema parser non‑interactively to dump a JSON config – handy for scripts and pipelines:

```bash
python - <<'PY'
import pyconfix, json
cfg = pyconfix.pyconfix(
    schem_file=["schem.json"],
    output_file="cfg.json"
)
cfg.run(graphical=False, config_file="prev.json")
PY
```

## Python API

If you’d rather drive everything from code, import the class:

```python
from pyconfix import pyconfix

cfg = pyconfix(
    schem_file=["main.json", "extras.json"],
    config_file="prev.json",      # load an existing config (optional)
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
    schem_file: list[str],
    config_file: str | None = None,
    output_file: str = "output_config.json",
    save_func: Callable[[dict, list], None] | None = None,
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
      "type": "multiple_choice",
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
| `multiple_choice` | one value from `choices` |
| `group`           | nests other options      |
| `action`          | executable task option   |

### Dependency syntax – cheatsheet

```text
!ENABLE_FEATURE_A                     # logical NOT
ENABLE_FEATURE_A && HOST=="dev"       # logical AND + comparison
TIMEOUT>5 || HOST=="localhost"        # logical OR  + relational
COUNT+5 > MAX_VALUE                     # addition + relational
SIZE-1 >= MIN_SIZE                      # subtraction + comparison
VALUE*2 == LIMIT                        # multiplication + equality
RATIO/3 < 1                             # division + relational
SIZE%4==0                               # modulus check
POWER**2 <= LIMIT                       # exponentiation + relational
BITS & 0xFF == 0xAA                     # bitwise AND + equality
FLAGS | FLAG_VERBOSE                    # bitwise OR
MASK ^ 0b1010                           # bitwise XOR
VALUE<<2 > 1024                         # left shift + relational
VALUE>>1 == 0                           # right shift + equality
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
def custom_save(json_data, _):
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

After saving a JSON config with pyconfix (`settings.json`), a Conan recipe can read that file to enable/disable features and tweak package options at build time.

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
