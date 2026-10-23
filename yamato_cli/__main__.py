"""JSON command-line interface."""
import argparse
import json
import sys

from .client import YamatoClient, YamatoError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Experimental read-only Yamato parcel search")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds, default 20")
    commands = parser.add_subparsers(dest="command", required=True)
    track = commands.add_parser("track", help="Search only tracking numbers you are authorized to access")
    track.add_argument("numbers", nargs="+")
    for command in ("detail", "slots"):
        command_parser = commands.add_parser(command, help="Read parcel details" if command == "detail" else "Read server-returned delivery options")
        command_parser.add_argument("number")
    commands.add_parser("probe", help="Submit an empty shipment list, without querying a parcel")
    args = parser.parse_args(argv)
    try:
        with YamatoClient(timeout=args.timeout) as client:
            if args.command == "probe":
                result = client.probe()
            elif args.command == "track":
                result = client.track(args.numbers)
            else:
                result = getattr(client, args.command)(args.number)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except YamatoError as exc:
        print(json.dumps({"error": exc.details}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
