"""
Parametric disc valve (ventilation diffuser) - Blender build script.

Builds two printable parts from params.json:
  frame : flange + duct collar + 3 internal fins with pin bosses
  disc  : front disc + stiffening rim + 3 standoff posts with pins

Coordinate system (assembled): Z = 0 is the flange front face (wall side),
+Z points into the duct. Both parts are already in print orientation
after a pure Z-translation (front faces down on the bed, no supports).

Run either way:
  blender -b -P build_valve.py -- --params params.json --out out
  python3 build_valve.py --params params.json --out out      (pip install bpy)
"""
import argparse
import json
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix


# ----------------------------------------------------------------- args
def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="params.json")
    ap.add_argument("--out", default="out")
    ap.add_argument("--render", action="store_true", help="render preview PNGs")
    return ap.parse_args(argv)


DEFAULTS = {
    "disc": True,         # False = open bellmouth ring: no disc, no fins, one part
    "inlet_lip_r": 0.0,   # rounding of the flange bore edge (airflow), <= flange_t
    "disc_edge_r": 0.0,   # rounding of the disc front edge (airflow), <= disc_t; 0 = chamfer
}


def load_params(path):
    with open(path) as f:
        raw = json.load(f)
    p = dict(DEFAULTS)
    p.update({k: v for k, v in raw.items() if not k.startswith("_")})
    return p


# ------------------------------------------------------------- helpers
def new_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def rounded_corner(rho, n=8):
    """Convex corner rounding that prints face-down without support.

    A pure quarter circle starts horizontal (an unprintable overhang), so the
    lower part is a 45 deg chamfer that runs tangentially into an arc of
    radius `rho`. Local coords: corner at (0, 0), face A along +u (the face
    on the bed), face B along +v. Points run from face A to face B.
    """
    k = 1.0 - math.sqrt(0.5)
    pts = [(2 * k * rho, 0.0)]
    for i in range(n + 1):
        t = 5 * math.pi / 4 - (math.pi / 4) * i / n
        pts.append((rho + rho * math.cos(t), rho + rho * math.sin(t)))
    return pts


def revolve(name, profile, segs):
    """Revolve a closed (r, z) polygon around the Z axis."""
    bm = bmesh.new()
    clean = [profile[0]]
    for pt in profile[1:]:
        if abs(pt[0] - clean[-1][0]) > 1e-6 or abs(pt[1] - clean[-1][1]) > 1e-6:
            clean.append(pt)
    verts = [bm.verts.new((r, 0.0, z)) for r, z in clean]
    edges = [bm.edges.new((verts[i], verts[(i + 1) % len(verts)]))
             for i in range(len(verts))]
    bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(0, 0, 1),
                   angle=2 * math.pi, steps=segs, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    return new_obj(name, bm)


def cylinder(name, r, z0, z1, x=0.0, y=0.0, segs=64):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs,
                          radius1=r, radius2=r, depth=z1 - z0,
                          matrix=Matrix.Translation((x, y, (z0 + z1) / 2)))
    return new_obj(name, bm)


def radial_prism(name, poly_rz, thickness, angle):
    """Extrude an (r, z) polygon tangentially and rotate it to `angle`."""
    bm = bmesh.new()
    h = thickness / 2
    front = [bm.verts.new((r, -h, z)) for r, z in poly_rz]
    back = [bm.verts.new((r, h, z)) for r, z in poly_rz]
    n = len(poly_rz)
    bm.faces.new(front[::-1])
    bm.faces.new(back)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((front[i], front[j], back[j], back[i]))
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0),
                     matrix=Matrix.Rotation(angle, 3, "Z"))
    return new_obj(name, bm)


def boolean(target, tool, op):
    mod = target.modifiers.new("bool", "BOOLEAN")
    mod.operation = op
    mod.solver = "EXACT"
    mod.object = tool
    dg = bpy.context.evaluated_depsgraph_get()
    ev = target.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    target.modifiers.clear()
    old = target.data
    target.data = me
    bpy.data.meshes.remove(old)
    bpy.data.objects.remove(tool, do_unlink=True)


def spoke_angles(p):
    n = int(p["spokes"])
    return [math.pi / 2 + k * 2 * math.pi / n for k in range(n)]


# --------------------------------------------------------------- parts
def build_frame(p):
    segs = int(p["segments"])
    R_f = p["flange_od"] / 2
    r_co = p["collar_od"] / 2
    r_ci = r_co - p["collar_wall"]
    ch, lip_d, lip_t, ft = (p["flange_chamfer"], p["flange_lip_depth"],
                            p["flange_lip_t"], p["flange_t"])
    li, H = p["collar_lead_in"], p["collar_h"]
    lip = p["inlet_lip_r"]

    # bore inlet edge: rounded (bellmouth-ish) lip carved out of the flange
    # plate, from (r_ci + ~0.59*lip, 0) on the front face up to (r_ci, lip)
    # on the bore wall. Limited to flange_t so the 2 mm collar wall stays.
    inlet = ([(r_ci + u, v) for u, v in rounded_corner(lip)] if lip > 0
             else [(r_ci, 0.0)])
    profile = [
        (R_f - ch, 0.0),
        (R_f, ch),
        (R_f, lip_d),
        (R_f - lip_t, lip_d),
        (R_f - lip_t, ft),
        (r_co, ft),
        (r_co, H - li),
        (r_co - li * 0.6, H),
        (r_ci, H),
    ] + inlet[::-1]
    frame = revolve("frame", profile, segs)
    if not p["disc"]:
        return frame

    pr, bd, bh = p["post_r"], p["boss_d"], p["boss_h"]
    hole_r = p["pin_d"] / 2 + p["fit_clearance"]
    for i, a in enumerate(spoke_angles(p)):
        # root: starts outboard of the lip on the front face, then slants
        # back into the collar wall (stays inside collar_od above flange_t)
        root_r, root_z = r_ci + lip + 0.5, min(lip + 0.5, p["fin_h_wall"])
        fin_poly = [(pr, 0.0), (root_r, 0.0), (r_ci + 0.8, root_z),
                    (r_ci + 0.8, p["fin_h_wall"]), (pr, bh)]
        boolean(frame, radial_prism(f"fin{i}", fin_poly, p["fin_t"], a), "UNION")
        x, y = pr * math.cos(a), pr * math.sin(a)
        boolean(frame, cylinder(f"boss{i}", bd / 2, 0.0, bh, x, y), "UNION")
        boolean(frame, cylinder(f"hole{i}", hole_r, -1.0, bh - 1.5, x, y, 32),
                "DIFFERENCE")
    return frame


def build_disc(p):
    segs = int(p["segments"])
    R = p["disc_d"] / 2
    zb = -p["standoff"]
    zf = zb - p["disc_t"]
    ch, rh, rw = p["disc_chamfer"], p["disc_rim_h"], p["disc_rim_w"]
    er = p["disc_edge_r"]
    if er > 0:   # rounded front edge (airflow): 45 deg chamfer into an arc
        edge = [(R - u, zf + v) for u, v in rounded_corner(er)]
        if er < p["disc_t"] - 1e-6:
            edge.append((R, zb))
    else:        # plain chamfer
        edge = [(R - ch, zf), (R, zf + ch)]
    profile = [(0.0, zf)] + edge + [
        (R, zb + rh),
        (R - rw, zb + rh),
        (R - rw, zb),
        (0.0, zb),
    ]
    disc = revolve("disc", profile, segs)

    pr = p["post_r"]
    for i, a in enumerate(spoke_angles(p)):
        x, y = pr * math.cos(a), pr * math.sin(a)
        boolean(disc, cylinder(f"post{i}", p["post_d"] / 2, zb - 0.5, 0.0, x, y),
                "UNION")
        boolean(disc, cylinder(f"pin{i}", p["pin_d"] / 2, -0.5, p["pin_len"], x, y, 32),
                "UNION")
    return disc


# ---------------------------------------------------------------- checks
def mesh_report(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    nonman = sum(1 for e in bm.edges if not e.is_manifold)
    vol = bm.calc_volume(signed=True)
    zs = [v.co.z for v in bm.verts]
    xs = [v.co.x for v in bm.verts]
    bm.free()
    return {"non_manifold_edges": nonman, "volume_cm3": round(vol / 1000, 2),
            "size_xy": round(max(xs) - min(xs), 2),
            "z_min": round(min(zs), 2), "z_max": round(max(zs), 2)}


def design_checks(p):
    errs = []
    r_ci = p["collar_od"] / 2 - p["collar_wall"]
    if p["inlet_lip_r"] > p["flange_t"] + 1e-9:
        errs.append("inlet_lip_r larger than flange_t (would cut the collar wall)")
    if p["inlet_lip_r"] > 0 and r_ci + p["inlet_lip_r"] + 3.0 > p["flange_od"] / 2 - p["flange_lip_t"]:
        errs.append("inlet lip leaves no flat flange face against the ceiling")
    if not p["disc"]:
        return errs
    if p["disc_d"] / 2 >= p["flange_od"] / 2:
        errs.append("disc larger than flange")
    if p["post_r"] + p["post_d"] / 2 > p["disc_d"] / 2 - p["disc_rim_w"]:
        errs.append("posts would stick out past the disc rim")
    if p["post_r"] + p["boss_d"] / 2 >= r_ci:
        errs.append("boss collides with collar wall")
    if p["pin_len"] > p["boss_h"] - 1.5 - 0.3:
        errs.append("pin longer than the blind hole")
    if p["disc_rim_h"] >= p["standoff"]:
        errs.append("disc rim touches flange plane")
    if p["disc_edge_r"] > p["disc_t"] + 1e-9:
        errs.append("disc_edge_r larger than disc_t")
    return errs


# ------------------------------------------------------------------ main
def render(objs, path, cam_loc, target=(0, 0, 0)):
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = 24
    scn.render.resolution_x, scn.render.resolution_y = 1000, 800
    scn.render.film_transparent = False
    world = bpy.data.worlds.get("W") or bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.92, 0.92, 0.94, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    scn.world = world

    mat = bpy.data.materials.get("plastic") or bpy.data.materials.new("plastic")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.86, 0.82, 0.70, 1)
    bsdf.inputs["Roughness"].default_value = 0.45
    for ob in bpy.context.scene.objects:
        if ob.type == "MESH":
            ob.hide_render = ob not in objs
            ob.data.materials.clear()
            ob.data.materials.append(mat)

    cam = bpy.data.objects.get("Cam")
    if cam is None:
        cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
        scn.collection.objects.link(cam)
        sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
        sun.data.energy = 3.0
        sun.rotation_euler = (math.radians(40), math.radians(-20), math.radians(30))
        scn.collection.objects.link(sun)
    cam.data.lens = 50
    cam.data.clip_end = 5000
    cam.location = cam_loc
    d = (cam.location - __import__("mathutils").Vector(target))
    cam.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    scn.camera = cam
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    a = parse_args()
    p = load_params(a.params)
    os.makedirs(a.out, exist_ok=True)

    errs = design_checks(p)
    if errs:
        print("DESIGN CHECK FAILED:\n  - " + "\n  - ".join(errs))
        sys.exit(2)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.unit_settings.system = "METRIC"
    scn.unit_settings.scale_length = 0.001
    scn.unit_settings.length_unit = "MILLIMETERS"

    frame = build_frame(p)
    disc = build_disc(p) if p["disc"] else None
    parts = [frame] + ([disc] if disc else [])
    if not disc:   # no stale disc.stl next to a one-part build
        for f in ("disc.stl", "disc.gcode"):
            if os.path.exists(os.path.join(a.out, f)):
                os.remove(os.path.join(a.out, f))

    report = {ob.name: mesh_report(ob) for ob in parts}
    for k, r in report.items():
        print(f"[{k}] {r}")
        if r["non_manifold_edges"]:
            print(f"ERROR: {k} is not manifold")
            sys.exit(3)

    # --- STL export in print orientation (front faces on the bed)
    lift = p["standoff"] + p["disc_t"]
    for ob, dz in zip(parts, (0.0, lift)):
        ob.location = (0, 0, dz)
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.wm.stl_export(filepath=os.path.join(a.out, f"{ob.name}.stl"),
                              export_selected_objects=True, apply_modifiers=True,
                              global_scale=1.0, ascii_format=False)

    if a.render:
        # assembled view (looking at the visible side, from the room)
        for ob in parts:
            ob.location = (0, 0, 0)
        render(parts, os.path.join(a.out, "preview_assembled.png"),
               (190, -260, -220), (0, 0, 0))
        # back side (duct side)
        render(parts, os.path.join(a.out, "preview_back.png"),
               (150, -220, 260), (0, 0, 10))
        # print plate: parts side by side, as sliced
        if disc:
            frame.location = (-95, 0, 0)
            disc.location = (85, 0, lift)
        render(parts, os.path.join(a.out, "preview_print_plate.png"),
               (0, -430, 340), (-5, 0, 8))
        for ob in parts:
            ob.location = (0, 0, 0)

    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(os.path.join(a.out, "disc_valve.blend")))
    with open(os.path.join(a.out, "build_report.json"), "w") as f:
        json.dump({"params": p, "meshes": report}, f, indent=2)
    print("OK ->", os.path.abspath(a.out))


if __name__ == "__main__":
    main()
