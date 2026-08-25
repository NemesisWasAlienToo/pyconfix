import time
from pyconfix import pyconfix, ConfigOption


### A self-contained sub-config, living in its own file. It is runnable on its
### own AND can be pulled into a bigger config with include() (see example.py).
def create_database_module():
    module = pyconfix()
    # The type is deduced from the value, so name + default is enough.
    module.add_options(
        ConfigOption('DB_HOST', 'localhost'),
        ConfigOption('DB_PORT', 5432),
    )

    @module.action_option(dependencies=lambda x: x.DB_HOST)
    def migrate(x):
        print(f"Migrating database at {x.DB_HOST}:{x.DB_PORT}...")
        time.sleep(1)
        return True

    return module


### Run this module on its own: `python database_module.py`
if __name__ == "__main__":
    create_database_module().run()
