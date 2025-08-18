from pyconfix import pyconfix, ConfigOption
import argparse
import time

### This function saves the current configurations in a defconfig-like format.
### Custom save functions can be used to export the settings in any format.
def custom_save(json_data, _):
    with open("output_defconfig", 'w') as f:
        for key, value in json_data.items():
            if value == None or (isinstance(value, bool) and value == False):
                continue
            if isinstance(value, str):
                f.write(f"CONFIG_{key}=\"{value}\"\n")
            else:
                f.write(f"CONFIG_{key}={value if value != True else 'y'}\n")

### This function creates the config object making it accessible for use
### by external tools like conan and CMake.
def create_config():
    config = pyconfix(schem_files=["schem.json"], save_func=custom_save, expanded=True, show_disabled=True)

    ### Actions can be added using a decorator
    @config.action_option(
        requires=lambda x: x.LOG_LEVEL, 
        dependencies="ENABLE_FEATURE_A",
    )
    def build(x):
        print("Building...")
        time.sleep(2)
        return True
    
    # First define a group
    deployment_group = config.group_option("deployment", dependencies="ENABLE_FEATURE_A")

    # Then use the group's action_option decorator
    @deployment_group.action_option(
        requires=lambda x: x.build(),
        dependencies="ENABLE_FEATURE_A"
    )
    def deploy(x):
        print("Deploying...")
        time.sleep(2)
        return True
    
    @config.action_option(
        requires=lambda x: x.deploy(),
    )
    def test(x):
        print("Testing...")
        time.sleep(2)
        return True
    
    ### Config options can also be added by calling extend on the config's options
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
    ])

    return config

if __name__ == "__main__":
    #################################################
    ################ Parse arguments ################
    #################################################
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
        "-p", "--print",
        metavar="OPTION",
        help="Prints the value of an option"
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

    #################################################
    ############ Create prconfix instance ###########
    #################################################
    config = create_config()
    
    #################################################
    ############## Run prconfix examlpe #############
    #################################################
    ### Config can load files, overlays and run in either TUI or CLI mode
    config.run(config_file=args.load, overlay=options_dict, graphical=not args.cli, output_diff=args.diff)

    ### Option values can be accessed as attributes.
    ### Actions can then be run by calling them as methods.
    ### Options can also be retrieved using the get method.
    if args.cli:
        if args.run:
            value, trace = config.get(args.run)()
            print(f"Value: {value}")
            print(f"Trace: {trace}")
        if args.print:
            print(f"{args.print}: {config.get(args.print)}")
