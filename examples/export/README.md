# Export

Saving settings as a C header.

```sh
python export.py
```

This writes `output_config.h`:

```c
#define MAX_USERS 100
#define TIMEOUT 30
```

* `write_header` receives all the values
* Pass it to `save`, or to `run` to save from the menu
