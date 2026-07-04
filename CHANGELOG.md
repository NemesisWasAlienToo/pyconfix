# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]
### Added
- Explicit, chainable `load_schem()` and `apply_config()` steps on the runner (each returns the instance), so API users control when and in what order the schema is loaded and saved selections are applied.
- Sensible defaults for the schema file (`pyconfixfile.json`) and config file (`output_config.json`) so the minimal example is a one-liner.
- Decorator API (`action_option` / `group_option`) now lives on the runner.
- `pyconfix.save(output_file, output_diff=False, save_func=None)` — one method that writes the config (full dump, or diff when `output_diff=True`) and runs the optional save hook, returning the written data. The TUI, `example.py`, and `python -m pyconfix` all persist through it.

### Changed
- Loading and applying no longer happen implicitly inside `run()`; call `load_schem()` / `apply_config()` explicitly first.
- `run()` now only launches the interactive TUI and takes the TUI-only settings `output_file`, `show_disabled`, and `save_func`.
- `save_func` now receives a single argument — the flattened config dict: `save_func(config_data)`.
- `serializer.write_config(output_file, config_data, save_func=None)` new signature.
- Flattening for display (`_flatten_options`) moved from Core to the TUI.
- Config-file merging and `overlay` handling moved from `Core.apply_config` to the runner's `apply_config`.
- `apply_config()` with no arguments now applies nothing (schema defaults are kept) instead of loading a default file; a named config file must exist or a `ValueError` is raised. The shipped `example.py` and `python -m pyconfix` check `os.path.exists` before loading the saved `output_config.json`, so a fresh checkout works and the TUI's save creates the file for later runs.

### Fixed
- Fixed a crash on entering TUI search mode (it referenced a helper that had moved to the TUI).
- Updated `python -m pyconfix` to the new load/apply/run API.
- In-session action attribute lookups report unknown keys before checking availability, giving a clear error instead of a `NoneType` failure.

### Deprecated
- Empty

### Removed
- Constructor no longer accepts `schem_files`, `output_file`, or `expanded`; `run()` no longer accepts `graphical`, `config_files`, or `overlay`.

### Security
- Empty

---

## [0.12.1]
### Added
- Added missing power operator
- New syntax for simplicity

### Changed
- Syntax of the json file

### Fixed
- Power operator
- Operator order
- Fixed search for groups

### Deprecated
- Old json syntax

---

## [0.10.6]
### Added
- Added support for multiple config files
- Added get function for Group Proxy
- Added default title for unnamed config
- Added default value for multiple choice options
- Added aliase support
- Added a main script file
- Added flag for specifying config files to the command script
- Added version flag to the command script

### Changed
- Unified the diff and output path
- Unified the save function by adding a diff flag and using the same function for both paths
- Improved the way arguments are passed to the object in the default command script
- Removed `graphical` from internal variables
- Unified the function for loading config files and the cache file
- Changed minimal python version for this package
- Cleaned up the folder structure

### Fixed
- Added error handling for loading of config files
- Fixed missing module
- Windows command

---

## [0.8.0]
### Added
- Stack trace for action execution
- Added capability to create groups and actions in it using decorators
- Added create_config fucntoin architecure example in the example for integration with other tools like conan, CMake, etc

### Changed
- Changed the name of the multiple option type to enum
- Change the option type implementation from string to StrEnum for safety

### Fixed
- Fixed the checked stack for the case the action is disabled

### Deprecated
- multiple_option type

### Removed
- --no-file-write flag in example.py removed since it was superficial and could be reproduced with other functions

---

## [0.7.0] - 2025-06-14
### Added
- action_option decorator added for easy function addition

### Removed
- Write to function option removed due to it being reproducible now using the API functions

### Changed
- Example improved

---