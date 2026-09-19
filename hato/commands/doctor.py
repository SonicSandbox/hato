# -*- coding: utf-8 -*-
"""Is the live API still what we think? A readout of every gate, measured.

    hato doctor                     key, search, rate-limit headers, files, one
                                    download, tsubasa, the track reader, unrar,
                                    py7zr, cache and config paths
    hato doctor --capture           ...and record every response as a fixture
    hato doctor --capture-dir DIR   ...into DIR instead of tests/fixtures/api/
    hato doctor --video FILE        read one video through tsubasa's track reader

⚠ It spends real, metered API calls (2 for the readout, about 10 with
--capture) against someone else's server. Run it deliberately.
"""
import json
import sys
from pathlib import Path

from hato import doctor, paths


def register(parser):
    parser.add_argument("--capture", action="store_true",
                        help="write every response into the fixtures folder")
    parser.add_argument("--capture-dir", metavar="DIR",
                        help="capture into DIR (implies --capture)")
    parser.add_argument("--video", metavar="FILE",
                        help="read one video through tsubasa's public track reader")
    parser.add_argument("--json", action="store_true", help="machine-readable output")


def _fixtures_dir():
    cfg, path = paths.project_config()
    if not cfg:
        return None
    return path.parent / cfg["test"]["harnessDir"] / "fixtures" / "api"


def run(args):
    capture_dir = None
    if args.capture_dir:
        capture_dir = Path(args.capture_dir)
    elif args.capture:
        capture_dir = _fixtures_dir()
        if capture_dir is None:
            sys.stderr.write("hato doctor: --capture writes into a source checkout's "
                             "tests/fixtures/api/, and there is none here. Use "
                             "--capture-dir DIR.\n")
            return 1
    try:
        readout = doctor.collect(capture_dir=capture_dir, video=args.video)
    except doctor.CaptureLeak as exc:
        sys.stderr.write("hato doctor: CAPTURE STOPPED -- %s\n" % exc)
        return 1
    if args.json:
        print(json.dumps(readout.as_dict(), ensure_ascii=False, sort_keys=True))
    else:
        print(doctor.render(readout))
    return readout.exit_code
