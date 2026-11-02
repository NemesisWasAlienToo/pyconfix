from pyconfix import pyconfix

if __name__ == "__main__":
    pyconfix().load_schem(["extra_schem.yaml"]).apply_config().run()
