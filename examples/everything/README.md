# Everything

All the features in one config. Look at the other examples first.

```sh
python example.py
python example.py --cli --run build --value --trace -o NEW_MODULE_TRI_STATE_FROM_PYTHON=DISABLED
```

* `example.py` builds the config and parses the command line
* `schem.json` is the main schema, with `extra_schem.json` and `extra_schem.yaml` included
* `database_module.py` is a config that also runs on its own: `python database_module.py`
* `custom_save` writes the settings to `output_defconfig`
