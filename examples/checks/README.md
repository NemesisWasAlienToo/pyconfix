# Checks

Options set by a script when the schema loads.

```sh
pyconfix --dump
pyconfix --run SHOW_COMMIT
```

* `HAS_GIT` and `HAS_DOCKER` are true if the tool is installed
* You can't change them in the menu, and saved settings don't change them
* `SHOW_COMMIT` needs `HAS_GIT`, and must run inside a git repo
