import argparse
from pyconfix import pyconfix

def parse_args():
    parser = argparse.ArgumentParser(description="Pyconfix configuration runner")
    parser.add_argument(
        "schem_files",
        metavar="FILE",
        nargs="*",
        help="Schem file(s). Can provide multiple files; defaults to 'pyconfixfile.json'"
    )
    parser.add_argument(
        "-l", "--load",
        metavar="FILE",
        action="append",
        help="Load configuration files"
    )
    parser.add_argument(
        "-p", "--print",
        metavar="OPTION",
        help="Prints the value of an option"
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in CLI mode instead of graphical mode"
    )
    parser.add_argument(
        "-c", "--cache",
        action="store_true",
        help="Specifies the output file where the current configuration will be saved"
    )
    parser.add_argument(
        "--dump",
        action="store_true",
        help="Dumps the current configuration to output"
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
    args = parse_args()

    constructorArgs = {}
    if args.schem_files and len(args.schem_files) > 0:
        constructorArgs['schem_files'] = args.schem_files
    if args.expanded:
        constructorArgs['expanded'] = args.expanded
    if args.show_disabled:
        constructorArgs['show_disabled'] = args.show_disabled
    if args.cache:
        constructorArgs['output_file'] = args.cache
    config = pyconfix(**constructorArgs)

    runArgs = {}
    if args.load:
        runArgs['config_files'] = args.load
    if args.option:
        runArgs['overlay'] = args.option
    if args.cli or args.print or args.dump:
        runArgs['graphical'] = False
    config.run(**runArgs)

    if args.print and args.dump:
        print("Incompatible flag combination: --print, --dump")
        exit(1)

    if args.print:
            print(f"{args.print}: {config.get(args.print)}")
    elif args.dump:
        print(config.dump())

if __name__ == "__main__":
    main()
