"""Rough airflow estimate for the disc valve in suction (exhaust) use.

Pure python, no Blender. Models the valve as:
  room -> annular inlet between disc edge and bore (both walls rounded or
  sharp) -> fins -> sudden expansion into the full collar bore -> duct.

Loss coefficients come from Idelchik-type inlet correlations (rounded /
sharp inlet vs r/D_h) and the sudden-expansion formula. Treat absolute
numbers as +-30 %; the *relative* comparison between parameter sets is
what this is for.

  python3 airflow.py params.json                 # estimate for this design
  python3 airflow.py params.json --sweep         # + what the big knobs do
  python3 airflow.py a.json --compare b.json     # two designs side by side
"""
import argparse
import json
import math

RHO_AIR = 1.2          # kg/m3
DP_REF = 50.0          # Pa across the valve for the m3/h figure

# inlet loss K (ref. throat velocity) vs edge radius / hydraulic diameter,
# Idelchik "Handbook of Hydraulic Resistance", diagram 3-4 (rounded inlet)
_K_ROUND = [(0.00, 0.50), (0.01, 0.44), (0.02, 0.37), (0.03, 0.31),
            (0.04, 0.26), (0.05, 0.22), (0.06, 0.20), (0.08, 0.15),
            (0.12, 0.09), (0.16, 0.06), (0.20, 0.03)]


def k_inlet(r_over_dh):
    x = max(0.0, r_over_dh)
    for (x0, k0), (x1, k1) in zip(_K_ROUND, _K_ROUND[1:]):
        if x <= x1:
            return k0 + (k1 - k0) * (x - x0) / (x1 - x0)
    return _K_ROUND[-1][1]


def load(path):
    p = {k: v for k, v in json.load(open(path)).items() if not k.startswith("_")}
    p.setdefault("disc", True)
    p.setdefault("inlet_lip_r", 0.0)
    p.setdefault("disc_edge_r", 0.0)
    return p


def estimate(p):
    r_ci = p["collar_od"] / 2 - p["collar_wall"]
    a_duct = math.pi * r_ci ** 2
    if not p["disc"]:
        # open ring: plain rounded tube inlet, no blockage, no expansion
        k = k_inlet(0.85 * p["inlet_lip_r"] / (2 * r_ci))
        v_duct = math.sqrt(2 * DP_REF / (RHO_AIR * k))
        return {
            "A_duct_cm2": a_duct / 100, "A_throat_cm2": a_duct / 100,
            "fin_block_cm2": 0.0, "A_curtain_cm2": float("nan"),
            "D_h_mm": 2 * r_ci, "K_bore_edge": k, "K_disc_edge": float("nan"),
            "K_expansion": 0.0, "K_duct": k,
            "Q_m3h_at_50Pa": v_duct * a_duct * 1e-6 * 3600,
            "dP_Pa_at_60m3h": 0.5 * RHO_AIR * (60 / 3600 / (a_duct * 1e-6)) ** 2 * k,
        }
    R = p["disc_d"] / 2
    n = int(p["spokes"])
    a_ann = math.pi * (r_ci ** 2 - R ** 2)
    fin_block = n * p["fin_t"] * max(0.0, r_ci - R)
    a_t = a_ann - fin_block
    a_curtain = 2 * math.pi * R * p["standoff"] - n * p["post_d"] * p["standoff"]
    d_h = 2 * (r_ci - R)

    # effective edge radius: the printable 45deg-chamfer+arc counts ~0.85 of a
    # full round; a plain 45deg chamfer of depth c behaves like r ~ 0.5 c.
    r_out = 0.85 * p["inlet_lip_r"]
    r_in = 0.85 * p["disc_edge_r"] if p["disc_edge_r"] > 0 else 0.5 * p["disc_chamfer"]
    k_out, k_in = k_inlet(r_out / d_h), k_inlet(r_in / d_h)
    k_inlet_avg = 0.5 * (k_out + k_in)          # annulus: two walls
    k_exp = (1.0 - a_t / a_duct) ** 2           # sudden expansion to full bore
    k_throat = k_inlet_avg + k_exp
    k_duct = k_throat * (a_duct / a_t) ** 2     # referenced to duct velocity

    v_duct = math.sqrt(2 * DP_REF / (RHO_AIR * k_duct))
    q = v_duct * a_duct * 1e-6 * 3600
    return {
        "A_duct_cm2": a_duct / 100, "A_throat_cm2": a_t / 100,
        "fin_block_cm2": fin_block / 100, "A_curtain_cm2": a_curtain / 100,
        "D_h_mm": d_h, "K_bore_edge": k_out, "K_disc_edge": k_in,
        "K_expansion": k_exp, "K_duct": k_duct,
        "Q_m3h_at_50Pa": q,
        "dP_Pa_at_60m3h": 0.5 * RHO_AIR * (60 / 3600 / (a_duct * 1e-6)) ** 2 * k_duct,
    }


def table(cols):
    keys = list(cols[0][1].keys())
    w = max(len(k) for k in keys) + 2
    print(" " * w + "".join(f"{name:>14s}" for name, _ in cols))
    for k in keys:
        print(f"{k:<{w}s}" + "".join(f"{d[k]:14.2f}" for _, d in cols))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("params")
    ap.add_argument("--compare", help="second params.json")
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args()
    p = load(a.params)
    cols = [("design", estimate(p))]
    if a.compare:
        cols.append(("compare", estimate(load(a.compare))))
    else:
        sharp = dict(p, inlet_lip_r=0.0, disc_edge_r=0.0)
        cols.append(("sharp edges", estimate(sharp)))
    table(cols)

    e = cols[0][1]
    if not p["disc"]:
        print("\nopen ring, no disc: throat = full bore, only the inlet edge counts.")
    if p["disc"]:
      print(f"\nthroat = annulus between disc and bore ({e['A_throat_cm2']:.0f} cm2, "
          f"{100 * e['A_throat_cm2'] / e['A_duct_cm2']:.0f} % of the duct).")
    s_free = e["A_throat_cm2"] * 100 / (math.pi * p["disc_d"])   # mm: curtain == throat
    if e["A_curtain_cm2"] < e["A_throat_cm2"]:
        print(f"side gap under the disc ({e['A_curtain_cm2']:.0f} cm2) is smaller than the "
              f"throat: air from straight ahead is throttled. standoff >= {s_free:.0f} mm "
              f"would remove that (disc sticks out further).")

    if a.sweep:
        print("\n-- knobs (model, +- 30 %) --")
        rows = []
        p = dict(p, disc=True)
        for so in (8, 10, 12, 15, 20):
            rows.append((f"standoff {so}", estimate(dict(p, standoff=so))))
        for dd in (70, 74, 78, 82):
            rows.append((f"disc_d {dd}", estimate(dict(p, disc_d=dd))))
        for ft in (3, 4, 5):
            rows.append((f"lip/flange_t {ft}", estimate(dict(p, flange_t=ft, inlet_lip_r=ft))))
        for name, d in rows:
            print(f"{name:18s} throat {d['A_throat_cm2']:5.1f} cm2  curtain {d['A_curtain_cm2']:5.1f} cm2  "
                  f"K_duct {d['K_duct']:5.2f}  Q@50Pa {d['Q_m3h_at_50Pa']:5.0f} m3/h  "
                  f"dP@60m3h {d['dP_Pa_at_60m3h']:4.1f} Pa")
        rows.append(("no disc, lip 3", estimate(dict(p, disc=False, flange_t=3, inlet_lip_r=3))))
        rows.append(("no disc, lip 6", estimate(dict(p, disc=False, flange_t=6, inlet_lip_r=6))))
        for name, d in rows[-2:]:
            print(f"{name:18s} throat {d['A_throat_cm2']:5.1f} cm2                     "
                  f"K_duct {d['K_duct']:5.2f}  Q@50Pa {d['Q_m3h_at_50Pa']:5.0f} m3/h  "
                  f"dP@60m3h {d['dP_Pa_at_60m3h']:4.1f} Pa")
        print("(standoff only changes the side gap - the model does not count it in K)")


if __name__ == "__main__":
    main()
