import argparse
import os
import sys
from ._version import __version__ as VERSION
from .option import ConfigOptionType
from .runner import pyconfix

def run_action(config, name, show_value, show_trace):
    """Run the action ``name`` and return whether it succeeded."""
    option = config.get_option(name)
    if option is None or option.option_type != ConfigOptionType.ACTION:
        print(f"'{name}' is not a task", file=sys.stderr)
        return False
    value, trace = config.get(name)()
    if show_value:
        print(f"Value: {value}")
    if show_trace:
        print(f"Trace: {trace}")
    # A disabled action never starts, so its trace is empty.
    if not trace:
        print(f"Task '{name}' is disabled", file=sys.stderr)
        return False
    if value is False:
        print(f"Task '{name}' failed", file=sys.stderr)
        return False
    return True

def parse_args():
    parser = argparse.ArgumentParser(description="Pyconfix configuration runner")
    parser.add_argument(
        "schema_files",
        metavar="FILE",
        nargs="*",
        help="Schema file(s). Can provide multiple files; defaults to pyconfixfile.json, then pyconfixfile.yaml"
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
        "-r", "--run",
        metavar="ACTION",
        help="Runs an action"
    )
    parser.add_argument(
        "-v", "--value",
        action="store_true",
        help="Print the action's return value (used with --run)"
    )
    parser.add_argument(
        "-t", "--trace",
        action="store_true",
        help="Print the action execution trace (used with --run)"
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
        "--version",
        action="version",
        version=f"pyconfix {VERSION}",
        help="Show program's version number and exit"
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
        elif value.removeprefix('-').isdigit():
            options_dict[key] = int(value)
        else:
            options_dict[key] = value
    args.option = options_dict
    return args

def main():
    args = parse_args()

    if args.print and args.dump:
        print("Incompatible flag combination: --print, --dump")
        exit(1)

    output_file = "pyconfix_output_config.json"

    # 1. Build the config and load the schema explicitly.
    config = pyconfix()
    config.load_schema(schema_files=args.schema_files or None)

    # 2. Apply saved selections: the cached output file (if present), then any
    #    -l files and -o key=value overrides.
    if os.path.exists(output_file):
        config.apply_config(config_files=[output_file])
    config.apply_config(config_files=args.load or [], overlay=args.option)

    # 3. Either run the interactive TUI or answer the headless query.
    if args.cli or args.print or args.dump or args.run:
        succeeded = not args.run or run_action(config, args.run, args.value, args.trace)
        if args.print:
            print(f"{args.print}: {config.get(args.print)}")
        elif args.dump:
            print(config.dump())
        elif not args.run:
            # Pure CLI mode (no query/run): persist the applied configuration.
            config.save(output_file)
        if not succeeded:
            sys.exit(1)
    else:
        config.run(output_file=output_file, show_disabled=args.show_disabled)

if __name__ == "__main__":
    main()
