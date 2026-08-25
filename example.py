import time, argparse, sys, os
from pyconfix import pyconfix, ConfigOption, ConfigOptionType
import platform

### This function saves the current configurations in a defconfig-like format.
### Custom save functions can be used to export the settings in any format.
def custom_save(json_data):
    with open("output_defconfig", 'w') as f:
        for key, value in json_data.items():
            if value is None or (isinstance(value, bool) and value == False):
                f.write(f"# {key} is not set\n")
            elif isinstance(value, str):
                f.write(f"{key}=\"{value}\"\n")
            else:
                f.write(f"{key}={value if value != True else 'y'}\n")

### This function creates the config object making it accessible for use
### by external tools like conan and CMake.
def create_config():
    config = pyconfix()

    ### Aliases can be registered with a dedicated helper
    config.register_alias(
        name='tri-state',
        option_type=ConfigOptionType.ENUM,
        choices=["INTEGRATED", "MODULE", "DISABLED"]
    )

    ### Config options can be added using helpers or plain ConfigOption objects
    config.add_options(
        config.option_from_alias('tri-state', name='NEW_MODULE_TRI_STATE_FROM_PYTHON'),
        config.option_from_alias('string', name='STRING_FROM_ALIAS', default='Default string value'),
        ConfigOption(
            name='OS',
            option_type=ConfigOptionType.EXTERNAL,
            default=platform.system()
        ),
        ConfigOption(
            name='PYTHON_EVALUATED',
            option_type=ConfigOptionType.EXTERNAL,
            default=".".join(map(str, sys.version_info[:3]))
        ),
    )

    ### Actions can also be added using a decorator for ease
    @config.action_option(
        requires=lambda x: x.LOG_LEVEL, 
        dependencies=lambda x: x.ENABLE_FEATURE_A,
    )
    def build(x):
        print("Building...")
        time.sleep(2)
        return True
    
    # First define a group
    deployment_group_proxy = config.group_option("deployment", dependencies=lambda x: x.ENABLE_FEATURE_A)

    # Sub options can be added to the group with its add_options() method, which
    # registers their names the same way as every other add path.
    deployment_group_proxy.add_options(
        ConfigOption(
            name='SUB_OPTION',
            option_type=ConfigOptionType.BOOL,
            default=False
        )
    )

    # Then use the group's action_option decorator to add actions easier
    @deployment_group_proxy.action_option(
        requires=lambda x: x.build(),
        dependencies=lambda x: x.ENABLE_FEATURE_A
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
    
    config.load_schem(schem_files=["schem.json"])
    return config

def parse_args():
    parser = argparse.ArgumentParser(description="Pyconfix configuration runner")
    parser.add_argument(
        "-l", "--load",
        metavar="FILE",
        action="append",
        default=[],
        help="Load configuration files"
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
        "--expanded",
        action="store_true",
        help="Default state of groups"
    )
    parser.add_argument(
        "--show-disabled",
        action="store_true",
        help="Show disabled options in the interface"
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
    args.option = options_dict
    return args

def main():
    #################################################
    # Parse arguments ###############################
    #################################################
    args = parse_args()

    #################################################
    # Create pyconfix instance ######################
    #################################################
    config = create_config()

    #################################################
    # Apply configs #################################
    #################################################
    default_output_file = "pyconfix_output_config.json"
    # Load the previous save only if it exists. On the first run there is none;
    # pressing save in the TUI creates it, and later runs will load it.
    if os.path.exists(default_output_file):
        config.apply_config(config_files=[default_output_file])
    config.apply_config(config_files=args.load, overlay=args.option)
    
    #################################################
    # Run pyconfix ##################################
    #################################################
    if not args.cli:
        config.run(output_file=default_output_file, show_disabled=True, save_func=custom_save)
    else:
        ### Option values can be accessed as attributes.
        ### Actions can then be run by calling them as methods.
        ### Options can also be retrieved using the get method.
        if args.run:
            value, trace = config.get(args.run)()
            print(f"Value: {value}")
            print(f"Trace: {trace}")
        if args.print:
            print(f"{args.print}: {config.get(args.print)}")

        ### In headless mode there is no TUI save step, so persist the result
        ### explicitly. This writes the JSON output file and runs custom_save.
        config.save(default_output_file, save_func=custom_save)

if __name__ == "__main__":
    main()
