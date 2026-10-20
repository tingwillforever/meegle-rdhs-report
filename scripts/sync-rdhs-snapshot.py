#!/usr/bin/env python3

from pathlib import Path
import subprocess
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if "--mode" in sys.argv:
    script = Path(__file__).resolve().parent / "sync-rdhs-to-pages.py"
    res = subprocess.run([sys.executable, str(script)] + sys.argv[1:])
    raise SystemExit(res.returncode)

from scripts.rdhs_snapshot_sync import main


raise SystemExit(main())
