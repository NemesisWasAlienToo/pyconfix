from pyconfix import pyconfix, ConfigOption, ConfigOptionType
import apt

_APT_CACHE = apt.Cache()

def is_apt_package_installed(package_name):
    return _APT_CACHE[package_name].is_installed


def main():
    config = pyconfix(schem_files=[])
    config.add_options(
        ConfigOption(name="dependencies", option_type=ConfigOptionType.GROUP, options=[
            ConfigOption(name="pkg-config", option_type=ConfigOptionType.EXTERNAL, default=lambda: is_apt_package_installed("pkg-config")),
            ConfigOption(name="fuse", option_type=ConfigOptionType.EXTERNAL, default=lambda: is_apt_package_installed("fuse")),
        ]),
    )

    config.run()

if __name__ == "__main__":
    main()