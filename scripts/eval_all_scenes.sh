#!/usr/bin/env bash
# Run tracker (if needed) + CLEAR MOT / failure mining on every normalized scene.
# Works on macOS bash 3.2+ (and zsh when invoked as bash via env).
#
# Usage:
#   ./scripts/eval_all_scenes.sh           # skip tracker if tracks.jsonl exists
#   ./scripts/eval_all_scenes.sh --force   # re-run tracker (needed after config change)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FORCE=0
for arg in "$@"; do
  case "$arg" in
    --force|-f) FORCE=1 ;;
    -h|--help)
      echo "Usage: $0 [--force]"
      exit 0
      ;;
    *)
      echo "unknown arg: $arg (try --force)" >&2
      exit 1
      ;;
  esac
done

NORMALIZED_ROOT="${NORMALIZED_ROOT:-data/normalized}"
TRACKS_OUT_ROOT="${TRACKS_OUT_ROOT:-data/tracks}"
TRACKER_BIN="${TRACKER_BIN:-core/build/trackbench_run}"
CONFIG="${CONFIG:-core/config/default.json}"
PYTHON="${PYTHON:-python3}"

if [[ ! -x "$TRACKER_BIN" ]]; then
  echo "tracker binary missing: $TRACKER_BIN" >&2
  echo "Build with: make core" >&2
  exit 1
fi

if [[ ! -d "$NORMALIZED_ROOT" ]]; then
  echo "normalized root missing: $NORMALIZED_ROOT" >&2
  exit 1
fi

mkdir -p "$TRACKS_OUT_ROOT"

shopt -s nullglob
scene_dirs=("$NORMALIZED_ROOT"/*/)
shopt -u nullglob

if [[ ${#scene_dirs[@]} -eq 0 ]]; then
  echo "no scenes under $NORMALIZED_ROOT" >&2
  exit 1
fi

for scene_dir in "${scene_dirs[@]}"; do
  scene_dir="${scene_dir%/}"
  scene="$(basename "$scene_dir")"
  dets="$scene_dir/detections.jsonl"
  gt="$scene_dir/gt.jsonl"
  tracks="$scene_dir/tracks.jsonl"
  meta="$scene_dir/scene_meta.json"
  eval_out="$TRACKS_OUT_ROOT/${scene}_eval.json"

  if [[ ! -f "$dets" || ! -f "$gt" ]]; then
    echo "skip $scene (missing detections.jsonl or gt.jsonl)" >&2
    continue
  fi

  if [[ "$FORCE" -eq 1 || ! -f "$tracks" ]]; then
    echo "==> tracking $scene"
    "$TRACKER_BIN" \
      --dets "$dets" \
      --config "$CONFIG" \
      --out "$tracks" \
      --timing "$scene_dir/timing.json"
    # Keep TRACKS_ROOT copy in sync for the triage API (if used).
    cp -f "$tracks" "$TRACKS_OUT_ROOT/${scene}.jsonl"
  else
    echo "==> tracks exist for $scene (skip tracker; pass --force to retrack)"
  fi

  echo "==> eval --mine $scene -> $eval_out"
  stdout_tmp="$(mktemp "${TMPDIR:-/tmp}/trackbench_eval.XXXXXX")"
  metrics_tmp="$(mktemp "${TMPDIR:-/tmp}/trackbench_metrics.XXXXXX")"

  if [[ -f "$meta" ]]; then
    PYTHONPATH=. "$PYTHON" -m eval.run_eval \
      --gt "$gt" \
      --tracks "$tracks" \
      --scene-meta "$meta" \
      --scene-id "$scene" \
      --mine \
      --out "$metrics_tmp" \
      >"$stdout_tmp"
  else
    PYTHONPATH=. "$PYTHON" -m eval.run_eval \
      --gt "$gt" \
      --tracks "$tracks" \
      --scene-id "$scene" \
      --mine \
      --out "$metrics_tmp" \
      >"$stdout_tmp"
  fi

  "$PYTHON" - "$metrics_tmp" "$stdout_tmp" "$eval_out" "$scene" <<'PY'
import json
import sys
from pathlib import Path

metrics_path, stdout_path, out_path, scene = sys.argv[1:5]
metrics = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
text = Path(stdout_path).read_text(encoding="utf-8")
decoder = json.JSONDecoder()
idx = 0
objs = []
while idx < len(text):
    while idx < len(text) and text[idx].isspace():
        idx += 1
    if idx >= len(text):
        break
    obj, end = decoder.raw_decode(text, idx)
    objs.append(obj)
    idx = end
mine = next((o for o in objs if isinstance(o, dict) and "n_failures" in o), {})
payload = {
    "scene": scene,
    "mota": metrics.get("mota"),
    "ids": metrics.get("ids"),
    "fp": metrics.get("fp"),
    "fn": metrics.get("fn"),
    "frag": metrics.get("frag"),
    "motp": metrics.get("motp"),
    "n_failures": mine.get("n_failures", 0),
    "metrics": metrics,
    "clusters": mine.get("clusters", []),
}
Path(out_path).parent.mkdir(parents=True, exist_ok=True)
Path(out_path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps({"scene": scene, "mota": payload["mota"], "ids": payload["ids"], "n_failures": payload["n_failures"]}))
PY
  rm -f "$stdout_tmp" "$metrics_tmp"
done

echo ""
echo "=== summary ==="
"$PYTHON" - "$TRACKS_OUT_ROOT" <<'PY'
import json, sys
from pathlib import Path

root = Path(sys.argv[1])
rows = []
for p in sorted(root.glob("*_eval.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    rows.append((d.get("scene", p.stem), d.get("mota"), d.get("ids"), d.get("n_failures")))
print(f"{'scene':<24} {'mota':>8} {'ids':>6} {'n_failures':>10}")
for scene, mota, ids, n_fail in rows:
    mota_s = f"{mota:.4f}" if isinstance(mota, (int, float)) else str(mota)
    print(f"{scene:<24} {mota_s:>8} {str(ids):>6} {str(n_fail):>10}")
if rows:
    total_ids = sum(int(r[2] or 0) for r in rows)
    total_fail = sum(int(r[3] or 0) for r in rows)
    print(f"{'TOTAL':<24} {'':>8} {total_ids:>6} {total_fail:>10}")
PY
