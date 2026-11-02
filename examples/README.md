# Examples

Each folder works on its own. Go into a folder and run the command.

| Folder                         | Shows                              | Run                       |
| ------------------------------ | ---------------------------------- | ------------------------- |
| [minimal](minimal)             | The smallest setup                 | `pyconfix`                |
| [options](options)             | Every kind of setting              | `pyconfix`                |
| [dependencies](dependencies)   | Options that depend on others      | `pyconfix`                |
| [tasks](tasks)                 | Shell tasks that run other tasks   | `pyconfix --run DEPLOY`   |
| [aliases](aliases)             | Reusable enums and tasks           | `pyconfix --run GOODBYE`  |
| [checks](checks)               | Checks that run at load            | `pyconfix`                |
| [include](include)             | Splitting a config across files    | `pyconfix`                |
| [python](python)               | Everything from Python             | `python menu.py`          |
| [export](export)               | Saving as a C header               | `python export.py`        |
| [everything](everything)       | All features together              | `python example.py`       |

The YAML examples need `pip install pyconfix[yaml]`.

Start with `minimal`. Leave `everything` for last.
