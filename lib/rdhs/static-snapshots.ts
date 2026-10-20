import type { RdhsSnapshot } from "./types";
import { validateSnapshot } from "./validate";

import s_2026_04 from "@/data/snapshots/2026-04.json";
import s_2026_05 from "@/data/snapshots/2026-05.json";
import s_2026_06 from "@/data/snapshots/2026-06.json";
import s_2026_07 from "@/data/snapshots/2026-07.json";
import s_2026_08 from "@/data/snapshots/2026-08.json";
import s_2026_09 from "@/data/snapshots/2026-09.json";
import s_2026_10 from "@/data/snapshots/2026-10.json";

const BUNDLED_SNAPSHOTS: RdhsSnapshot[] = [
  validateSnapshot(s_2026_04),
  validateSnapshot(s_2026_05),
  validateSnapshot(s_2026_06),
  validateSnapshot(s_2026_07),
  validateSnapshot(s_2026_08),
  validateSnapshot(s_2026_09),
  validateSnapshot(s_2026_10),
];

export function loadStaticSnapshots(): RdhsSnapshot[] {
  return BUNDLED_SNAPSHOTS;
}
