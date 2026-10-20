import type { RdhsSnapshot } from "./types";
import { validateSnapshot } from "./validate";

import s04 from "@/data/snapshots/2026-04.json";
import s05 from "@/data/snapshots/2026-05.json";
import s06 from "@/data/snapshots/2026-06.json";
import s07 from "@/data/snapshots/2026-07.json";
import s08 from "@/data/snapshots/2026-08.json";
import s09 from "@/data/snapshots/2026-09.json";

const BUNDLED_SNAPSHOTS: RdhsSnapshot[] = [
  validateSnapshot(s04),
  validateSnapshot(s05),
  validateSnapshot(s06),
  validateSnapshot(s07),
  validateSnapshot(s08),
  validateSnapshot(s09),
];

export function loadStaticSnapshots(): RdhsSnapshot[] {
  return BUNDLED_SNAPSHOTS;
}
