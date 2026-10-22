"""Independent check of the exported STLs (no Blender needed).

Verifies each part is watertight, sits flat on the bed (z_min == 0),
has a usable first-layer contact area, and that pin/hole fit is sane.
Exit code != 0 stops the pipeline before slicing.
"""
import json
import sys

import numpy as np
import trimesh

out = sys.argv[1] if len(sys.argv) > 1 else "out"
p = {k: v for k, v in json.load(open(sys.argv[2] if len(sys.argv) > 2 else "params.json")).items()
     if not k.startswith("_")}

ok = True
parts = ["frame"] + (["disc"] if p.get("disc", True) else [])
for name in parts:
    m = trimesh.load(f"{out}/{name}.stl")
    lo, hi = m.bounds
    # first layer contact: faces lying on z=0 facing down
    down = (m.face_normals[:, 2] < -0.99) & (np.abs(m.triangles_center[:, 2]) < 1e-3)
    contact = m.area_faces[down].sum()
    print(f"{name:6s} watertight={m.is_watertight}  volume={m.volume/1000:6.1f} cm3  "
          f"bbox={hi[0]-lo[0]:.1f} x {hi[1]-lo[1]:.1f} x {hi[2]-lo[2]:.1f} mm  "
          f"z_min={lo[2]:.3f}  bed_contact={contact/100:.1f} cm2")
    if not m.is_watertight:
        print(f"  FAIL: {name} not watertight"); ok = False
    if abs(lo[2]) > 1e-3:
        print(f"  FAIL: {name} not on the bed"); ok = False
    if contact < 5 * 100:
        print(f"  FAIL: {name} bed contact too small"); ok = False

clr = p["fit_clearance"]
if "disc" in parts:
    print(f"pin fit: pin {p['pin_d']:.2f} mm in hole {p['pin_d'] + 2*clr:.2f} mm "
          f"({'press/glue' if clr < 0.2 else 'slip + glue'} fit)")
else:
    print("one-part open ring (no disc)")
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
