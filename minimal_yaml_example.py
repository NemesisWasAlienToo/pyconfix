from pyconfix import pyconfix

if __name__ == "__main__":
    pyconfix().load_schema(["extra_schem.yaml"]).apply_config().run()
