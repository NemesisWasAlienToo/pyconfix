from pyconfix import pyconfix

if __name__ == "__main__":
    config = pyconfix(schem_files=["schem.json"])
    config.run()
