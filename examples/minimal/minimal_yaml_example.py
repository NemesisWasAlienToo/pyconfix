from pyconfix import pyconfix

if __name__ == "__main__":
    pyconfix().load_schema(["schema.yaml"]).apply_config().run()
