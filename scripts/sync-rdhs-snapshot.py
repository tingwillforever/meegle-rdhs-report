#!/usr/bin/env python3

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.rdhs_snapshot_sync import main


raise SystemExit(main())
