# Disc valve – parametric replacement

Two variants from the same `params.json`, switched with `"disc"`:

| `disc` | Parts | What you get |
|--------|-------|--------------|
| `false` (default) | `frame.stl` only | **open bellmouth ring** – 6 mm flange with a 6 mm rounded inlet lip, no disc, no fins. One print, nothing to assemble. Best airflow and quietest. |
| `true` | `frame.stl` + `disc.stl` | **disc valve look** – flange + 115 mm ring + 3 fins with pin sockets, and a disc with 3 Ø3 pins. Push the pins into the sockets, drop of CA glue or leave dry. |

All parts print visible-face-down, no supports.

## Pipeline

```
params.json ──► build_valve.py (Blender) ──► frame.stl / disc.stl / disc_valve.blend
                                         └─► validate.py (watertight, on bed, contact area)
                                         └─► airflow.py  (suction loss estimate)
                                                         └─► PrusaSlicer CLI ──► .gcode
```

```bash
pip install bpy trimesh --break-system-packages   # or use your Blender install
./pipeline.sh --render                            # build + check + previews (+ slice)
PRINTER_INI=~/my_printer.ini ./pipeline.sh        # slice with your printer profile
```

Change a dimension → edit `params.json` → rerun. Design checks stop the build if
parts would collide (posts outside disc, boss hitting the collar, pin too long…).

## Airflow (suction / exhaust)

`python3 airflow.py params.json` prints a loss estimate (Idelchik-type inlet
correlations + sudden expansion, ±30 % absolute, good for comparing variants).
K is the loss coefficient referenced to duct velocity:

| Design | K | ΔP at 60 m³/h | ΔP at 150 m³/h |
|--------|---|---------------|----------------|
| original: disc Ø78, sharp edges | 2.95 | 5.2 Pa | 33 Pa |
| disc Ø78, rounded edges | 1.75 | 3.1 Pa | 19 Pa |
| disc Ø70, rounded | 1.08 | 1.9 Pa | 12 Pa |
| open ring, 3 mm lip | 0.35 | 0.6 Pa | 3.9 Pa |
| **open ring, 6 mm lip (default)** | **0.24** | **0.4 Pa** | **2.6 Pa** |

The disc is the restriction: it halves the free area (Ø78 in the Ø111 bore
→ ~48 cm²) and forces a sudden expansion behind it. Without it only the inlet
edge counts, and 6 mm of rounding gets that close to a proper bellmouth.
Note that a bathroom fan works against 50–100 Pa of duct resistance, so at
normal flows the valve itself is a small share; the gain is largest at high
flows, with a weak fan, and in noise (throat velocity halves).

For the disc variant the throat is the annulus between disc and bore, not
the `standoff` gap. Both inlet edges are rounded in a way that still prints
face-down without support (45° chamfer running tangentially into an arc):

| Param | Default | What it does |
|-------|---------|--------------|
| `inlet_lip_r` | 6.0 (= `flange_t`) | rounded lip on the bore edge of the flange. Max = `flange_t`, more would cut the 2 mm collar wall. 0 = sharp. |
| `disc_edge_r` | 2.6 (= `disc_t`) | disc variant: rounded front edge instead of the 0.8 mm chamfer. 0 = chamfer. |

`python3 airflow.py params.json --sweep` shows what the knobs do. With a disc,
only `disc_d` changes the throat (Ø70 → +27 % flow, but you see more of the
duct); `standoff` only throttles air coming from straight ahead and the gap
under the disc equals the throat area at ~20 mm.

Going back to the disc look: set `"disc": true`. The 6 mm flange and lip are
fine for both; with `"flange_t": 3` set `inlet_lip_r` to 3 and
`flange_lip_depth` to 6, `collar_h` to 30.

## Dimensions to verify (calipers)

Only `collar_od = 115` is measured. Estimated from photos:
`flange_od` (154), `collar_h` (33 = 27 mm of collar beyond the 6 mm plate, same
reach as the original 30/3 – check the socket depth), and for the disc variant
`disc_d` (78) and `standoff` (10).

## Material
PETG (default profile, `slicer/petg_0.2mm.ini`). ASA if near a cooker hood or sun.
If the ring is loose in the ceiling socket, wrap one turn of thin foam tape
or reduce clearance by raising `collar_od` 0.2–0.3 mm.
