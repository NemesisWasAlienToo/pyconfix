# Dependencies

Options that turn on and off based on other options.

```sh
pyconfix
```

* Set `LOG_LEVEL` to `DEBUG` and `LOG_FILE` appears
* Turn off `ENABLE_LOGGING` and everything that depends on it disappears
* `Logging` is a group, so its `deps` apply to everything inside it
