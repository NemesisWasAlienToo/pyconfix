# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]
### Added
- Empty

### Changed
- Empty

### Fixed
- Empty

### Deprecated
- Empty

### Removed
- Empty

### Security
- Empty

---

## [0.10.1]
### Added
- Added support for multiple config files
- Added get function for Group Proxy
- Added default title for unnamed config
- Added default value for multiple choice options
- Added aliase support
- Added a main script file
- Added flag for specifying config files to the command script

### Changed
- Unified the diff and output path
- Unified the save function by adding a diff flag and using the same function for both paths
- Improved the way arguments are passed to the object in the default command script
- Removed `graphical` from internal variables
- Unified the function for loading config files and the cache file

### Fixed
- Added error handling for loading of config files
- Fixed missing module

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