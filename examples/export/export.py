# Write settings as a C header. Run: python export.py
from pyconfix import pyconfix


def write_header(values):
    with open("output_config.h", "w") as f:
        for name, value in values.items():
            f.write(f"#define {name} {value}\n")


if __name__ == "__main__":
    config = pyconfix().load_schema().apply_config()
    # Pass the same function to run() to save from the menu.
    config.save(save_func=write_header)
