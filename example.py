from pyconfix import pyconfix, ConfigOption

import argparse
import time

def build(x):
    print("Building...")
    time.sleep(2)
    return True

def deploy(stdscr):
    print("Deploying...")
    time.sleep(2)
    return True

def custom_save(json_data, _):
    with open("output_defconfig", 'w') as f:
        for key, value in json_data.items():
            if value == None or (isinstance(value, bool) and value == False):
                continue
            if isinstance(value, str):
                f.write(f"CONFIG_{key}=\"{value}\"\n")
            else:
                f.write(f"CONFIG_{key}={value if value != True else 'y'}\n")

def main():
    load_file:str = None
    graphical_mode = True
    parser = argparse.ArgumentParser(description="Pyconfix configuration runner")
    parser.add_argument(
        "-l", "--load",
        metavar="FILE",
        help="Load a configuration file"
    )
    parser.add_argument(
        "-r", "--run",
        metavar="ACTION",
        help="Runs an action"
    )
    parser.add_argument(
        "-c", "--cli",
        action="store_true",
        help="Run in CLI mode instead of graphical mode"
    )
    parser.add_argument(
        "-d", "--diff",
        action="store_true",
        help="Save the setting as diff instead of a full config"
    )
    parser.add_argument(
        "-o", "--option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Pass key=value pairs. Can be used multiple times."
    )
    args = parser.parse_args()
    options_dict = {}
    for item in args.option:
        if "=" not in item:
            parser.error(f"Invalid format for option '{item}'. Expected KEY=VALUE.")
        key, value = item.split("=", 1)
        options_dict[key] = value
    for key, value in options_dict.items():
        if value.lower() in ["true", "false"]:
            options_dict[key] = value.lower() == "true"
        elif value.isdigit():
            options_dict[key] = int(value)
        else:
            options_dict[key] = value

    graphical_mode = not args.cli
    load_file = args.load if args.load else None
    
    config = pyconfix(schem_files=["schem.json"], save_func=custom_save, expanded=True, show_disabled=True)

    config.options.extend([
        ConfigOption(
            name='OS',
            option_type='string',
            default="UNIX",
            external=True
        ),
        ConfigOption(
                name='PYTHON_EVALUATED',
                option_type='string',
                default="UNIX",
                dependencies=lambda x: x.ENABLE_FEATURE_A
        ),
        ConfigOption(
                name='build',
                option_type="action",
                description="Compiles the code",
                dependencies="ENABLE_FEATURE_A",
                default=build,
                requires=lambda x: x.LOG_LEVEL
        ),
        ConfigOption(
                name='deploy',
                option_type="action",
                description="Deploys the code",
                dependencies="ENABLE_FEATURE_A",
                default=deploy,
                requires=lambda x: x.build(),
        ),
    ])
    
    config.run(config_file=load_file, graphical=graphical_mode, as_diff=args.diff, overlay=options_dict)

    if not graphical_mode:
        if args.run:
            print(f"{args.run}: {config.get(args.run)()}")

if __name__ == "__main__":
    main()
