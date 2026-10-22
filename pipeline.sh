#!/usr/bin/env bash
# Disc valve: params.json -> Blender model -> STL -> checks -> G-code
#
#   ./pipeline.sh              build + validate + slice (if a slicer is found)
#   ./pipeline.sh --render     also render preview PNGs
#   PRINTER_INI=my.ini ./pipeline.sh   use your PrusaSlicer printer/filament profile
#
# Blender: uses the `blender` binary if present, else `python3` with the bpy module.
set -euo pipefail
cd "$(dirname "$0")"
OUT=${OUT:-out}
RENDER=""; [[ "${1:-}" == "--render" ]] && RENDER="--render"

echo "== 1/3 build model"
if command -v blender >/dev/null; then
  blender -b --factory-startup -P build_valve.py -- --params params.json --out "$OUT" $RENDER
elif [[ -x /Applications/Blender.app/Contents/MacOS/Blender ]]; then
  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P build_valve.py -- --params params.json --out "$OUT" $RENDER
else
  python3 build_valve.py --params params.json --out "$OUT" $RENDER
fi

echo "== 2/3 validate STLs"
python3 validate.py "$OUT" params.json
echo "-- airflow estimate (suction)"
python3 airflow.py params.json

echo "== 3/3 slice"
SLICER=""
for c in prusa-slicer PrusaSlicer superslicer /Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer; do
  command -v "$c" >/dev/null 2>&1 && { SLICER=$c; break; }
  [[ -x "$c" ]] && { SLICER=$c; break; }
done
if [[ -z "$SLICER" ]]; then
  echo "No PrusaSlicer CLI found - open $(ls "$OUT"/*.stl | tr '\n' ' ')in your slicer"
  echo "(Orca/Bambu: no supports, front faces stay on the bed)."
  exit 0
fi
LOADS=(); [[ -n "${PRINTER_INI:-}" ]] && LOADS+=(--load "$PRINTER_INI")
LOADS+=(--load slicer/petg_0.2mm.ini)
for stl in "$OUT"/frame.stl "$OUT"/disc.stl; do
  [[ -f "$stl" ]] || continue
  "$SLICER" --export-gcode "${LOADS[@]}" --output "${stl%.stl}.gcode" "$stl"
done
echo "G-code: $(ls "$OUT"/*.gcode | tr '\n' ' ')"
