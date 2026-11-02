# The same features, with no schema file. Run: python menu.py
from pyconfix import pyconfix, ConfigOption


def create_config():
    config = pyconfix()
    config.config_name = "Python"
    config.add_options(
        ConfigOption("TARGET", choices=["linux", "windows"]),
        ConfigOption("OPTIMIZE", True),
        ConfigOption("THREADS", 4, dependencies="OPTIMIZE"),
    )

    # Python tasks can read option values through x.
    @config.action_option()
    def build(x):
        print(f"Building for {x.TARGET}")
        return True

    @config.action_option(needs="build()", dependencies="TARGET == linux")
    def deploy(x):
        print("Deploying...")
        return True

    return config


if __name__ == "__main__":
    create_config().run()
