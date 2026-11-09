"""Tohumdan (seed) low-poly ortaçağ köyü → GLB (+ .blend, + Godot için yol JSON'u, + Workbench önizlemesi).

Çalıştırma (arka planda, pencere açmadan):
  nice -n 10 /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup \
      --python make_village.py -- --seed 1 --out village_seed1.glb [--preview önizleme.png]

Ne üretir:
  - 70×70 m arazi (hafif tepeler, tohuma bağlı) + kıvrılan toprak yol → TEK nesne (iki malzeme)
  - 24–36 ev: gövde (5 duvar rengi) + çatı (beşik/kırma × 4 renk) + bazılarında baca
  - ağaçlar (çam / yuvarlak, gövde+taç tek mesh), kayalar (2 biçim)
Paylaşılan mesh (örnekleme / instancing): aynı türden her ev/ağaç/kaya AYNI mesh verisini kullanır,
yalnız konum/dönme/ölçek farklıdır. glTF'te bu, birden çok düğümün aynı mesh'i göstermesi demektir;
dosya küçük kalır, Godot da her mesh'i bir kez yükler.

Eksenler: Blender Z yukarı. glTF dışa aktarımı Y yukarı yapar: Godot (x, y, z) = Blender (x, z, -y).
"""
import json
import math
import random
import sys
import time
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

T0 = time.perf_counter()
R = math.radians
HALF = 35.0          # arazi yarı genişliği (m)
GRID = 44            # arazi ızgarası (44×44 kare, 1,6 m)


def argv():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    cfg = {"seed": 1, "out": "village.glb", "preview": None, "no_instancing": False}
    for i, k in enumerate(a):
        if k == "--seed":
            cfg["seed"] = int(a[i + 1])
        if k == "--out":
            cfg["out"] = a[i + 1]
        if k == "--preview":
            cfg["preview"] = a[i + 1]
        if k == "--no-instancing":       # yalnız karşılaştırma: her nesneye kendi mesh kopyası
            cfg["no_instancing"] = True
    return cfg


CFG = argv()
RNG = random.Random(CFG["seed"])


# ── malzemeler (renkler DOĞRUSAL / linear: glTF baseColorFactor doğrusaldır) ──────────
def srgb2lin(c):
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


MAT = {}


def mat(name, srgb, rough=0.9):
    rgb = srgb2lin(srgb)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*rgb, 1.0)
    p.inputs["Roughness"].default_value = rough
    m.diffuse_color = (*rgb, 1.0)          # Workbench önizlemesi için
    MAT[name] = m
    return m


WALLS = {"wall_white": (0.93, 0.89, 0.80), "wall_ochre": (0.86, 0.70, 0.45),
         "wall_rose": (0.88, 0.70, 0.64), "wall_stone": (0.70, 0.68, 0.64),
         "wall_blue": (0.70, 0.78, 0.84)}
ROOFS = {"roof_terra": (0.66, 0.27, 0.16), "roof_slate": (0.27, 0.29, 0.33),
         "roof_thatch": (0.74, 0.60, 0.32), "roof_brown": (0.40, 0.25, 0.17)}
for n, c in WALLS.items():
    mat(n, c)
for n, c in ROOFS.items():
    mat(n, c)
mat("wood", (0.30, 0.19, 0.11))
mat("window", (0.16, 0.20, 0.28), 0.4)
mat("grass", (0.36, 0.55, 0.24), 1.0)
mat("dirt", (0.58, 0.45, 0.30), 1.0)
mat("rock", (0.52, 0.52, 0.50), 0.95)
mat("leaf", (0.24, 0.48, 0.20))
mat("pine", (0.15, 0.35, 0.20))
mat("trunk", (0.36, 0.24, 0.15))
mat("chimney", (0.50, 0.40, 0.36))


# ── arazi ve yol (tohuma bağlı fonksiyonlar) ───────────────────────────────────────────
P = [RNG.uniform(0, 6.283) for _ in range(6)]
PATH_A, PATH_B = RNG.uniform(5, 9), RNG.uniform(2, 4)
PATH_F1, PATH_F2 = RNG.uniform(0.07, 0.11), RNG.uniform(0.17, 0.25)
PATH_TILT = RNG.uniform(-0.25, 0.25)


def height(x, y):
    return (1.1 * math.sin(x * 0.085 + P[0]) * math.cos(y * 0.07 + P[1])
            + 0.45 * math.sin(x * 0.19 + y * 0.13 + P[2])
            + 0.25 * math.cos(y * 0.23 - x * 0.05 + P[3]))


def path_center(x):
    y = PATH_A * math.sin(x * PATH_F1 + P[4]) + PATH_B * math.sin(x * PATH_F2 + P[5]) + PATH_TILT * x
    return Vector((x, y))


PATH_PTS = [path_center(-31 + 0.5 * i) for i in range(125)]   # x: -31 … +31, 0,5 m aralık


def dist_to_path(p):
    return min((p - q).length for q in PATH_PTS)


def new_obj(name, bm, mats, parent=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(MAT[m])
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if parent:
        ob.parent = parent
    return ob


def build_ground():
    """Arazi + yol TEK nesnede birleşik (ikisi de hiç tekrar etmiyor, örneklemeye gerek yok)."""
    bm = bmesh.new()
    step = 2 * HALF / GRID
    vs = [[bm.verts.new((-HALF + i * step, -HALF + j * step, height(-HALF + i * step, -HALF + j * step)))
           for i in range(GRID + 1)] for j in range(GRID + 1)]
    for j in range(GRID):
        for i in range(GRID):
            f = bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
            f.material_index = 0
    # yol şeridi: arazinin 7 cm üstünde, 2,6 m geniş
    w = 1.3
    prev = None
    for k, c in enumerate(PATH_PTS):
        a = PATH_PTS[max(k - 1, 0)]
        b = PATH_PTS[min(k + 1, len(PATH_PTS) - 1)]
        t = (b - a).normalized()
        n = Vector((-t.y, t.x))
        l, r = c + n * w, c - n * w
        vl = bm.verts.new((l.x, l.y, height(l.x, l.y) + 0.07))
        vr = bm.verts.new((r.x, r.y, height(r.x, r.y) + 0.07))
        if prev:
            f = bm.faces.new((prev[1], prev[0], vl, vr))
            f.material_index = 1
        prev = (vl, vr)
    bm.normal_update()
    return new_obj("Ground_and_Path", bm, ["grass", "dirt"])


def box(bm, x0, x1, y0, y1, z0, z1, mi):
    r = bmesh.ops.create_cube(bm, size=1.0)
    for v in r["verts"]:
        v.co = Vector((x0 if v.co.x < 0 else x1, y0 if v.co.y < 0 else y1, z0 if v.co.z < 0 else z1))
    for f in {f for v in r["verts"] for f in v.link_faces}:
        f.material_index = mi


# Ev ölçüsü (yerel): gövde x ∈ [-2, 2], y ∈ [-1.75, 1.75], ön yüz -Y; duvar üstü z = 2.0
def house_body_mesh(wall):
    bm = bmesh.new()
    box(bm, -2, 2, -1.75, 1.75, -0.9, 2.0, 0)                 # duvar (araziye 0,9 m gömülü: yamaçta havada kalmasın)
    box(bm, -0.45, 0.45, -1.82, -1.7, 0.0, 1.75, 1)           # kapı
    for x in (-1.35, 1.35):
        box(bm, x - 0.32, x + 0.32, -1.80, -1.7, 0.95, 1.55, 2)  # ön pencereler
    for y in (-0.6, 0.6):
        box(bm, 1.7, 2.06, y - 0.3, y + 0.3, 0.95, 1.5, 2)   # yan pencere (sağ)
        box(bm, -2.06, -1.7, y - 0.3, y + 0.3, 0.95, 1.5, 2) # yan pencere (sol)
    me = bpy.data.meshes.new(f"house_{wall}")
    bm.to_mesh(me)
    bm.free()
    for m in (wall, "wood", "window"):
        me.materials.append(MAT[m])
    return me


def roof_mesh(kind, roof):
    bm = bmesh.new()
    ox, oy, z0, zr = 2.35, 2.1, 2.0, 3.55
    rx = ox if kind == "gable" else 1.0            # mahya ucu: beşikte uçta, kırmada içeride
    b = [bm.verts.new(p) for p in ((-ox, -oy, z0), (ox, -oy, z0), (ox, oy, z0), (-ox, oy, z0))]
    r0, r1 = bm.verts.new((-rx, 0, zr)), bm.verts.new((rx, 0, zr))
    bm.faces.new((b[0], b[1], r1, r0))            # ön eğim
    bm.faces.new((b[2], b[3], r0, r1))            # arka eğim
    bm.faces.new((b[1], b[2], r1))                # sağ (beşik: alın üçgeni)
    bm.faces.new((b[3], b[0], r0))                # sol
    bm.faces.new((b[3], b[2], b[1], b[0]))        # alt
    bm.normal_update()
    me = bpy.data.meshes.new(f"roof_{kind}_{roof}")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MAT[roof])
    return me


def chimney_mesh():
    bm = bmesh.new()
    box(bm, -0.25, 0.25, -0.25, 0.25, 2.2, 4.2, 0)
    me = bpy.data.meshes.new("chimney")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MAT["chimney"])
    return me


def tree_mesh(kind):
    bm = bmesh.new()
    box(bm, -0.18, 0.18, -0.18, 0.18, -0.3, 1.6, 0)
    if kind == "pine":
        for z, r, h in ((1.0, 1.5, 2.0), (2.2, 1.15, 1.8), (3.3, 0.8, 1.5)):
            res = bmesh.ops.create_cone(bm, cap_ends=True, segments=7, radius1=r, radius2=0.0, depth=h)
            bmesh.ops.translate(bm, verts=res["verts"], vec=(0, 0, z + h / 2))
            for f in {f for v in res["verts"] if v.is_valid for f in v.link_faces}:
                f.material_index = 1
        name, mats = "tree_pine", ["trunk", "pine"]
    else:
        res = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.5)
        bmesh.ops.scale(bm, verts=res["verts"], vec=(1, 1, 0.9))
        bmesh.ops.translate(bm, verts=res["verts"], vec=(0, 0, 2.7))
        for f in {f for v in res["verts"] for f in v.link_faces}:
            f.material_index = 1
        name, mats = "tree_round", ["trunk", "leaf"]
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(MAT[m])
    return me


def rock_mesh(i):
    bm = bmesh.new()
    res = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.8)
    rr = random.Random(100 + i)        # kaya biçimi sabit; köy tohumundan bağımsız
    for v in res["verts"]:
        v.co *= rr.uniform(0.75, 1.15)
    bmesh.ops.scale(bm, verts=res["verts"], vec=(1.2, 1.0, 0.6))
    me = bpy.data.meshes.new(f"rock_{i}")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MAT["rock"])
    return me


def place(name, me, x, y, z, rot, scale, parent=None):
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (x, y, z)
    ob.rotation_euler = (0, 0, rot)
    ob.scale = scale
    if parent:
        ob.parent = parent
    return ob


def build_village():
    body = {w: house_body_mesh(w) for w in WALLS}
    roofs = {(k, r): roof_mesh(k, r) for k in ("gable", "hip") for r in ROOFS}
    chim = chimney_mesh()
    trees = {k: tree_mesh(k) for k in ("pine", "round")}
    rocks = [rock_mesh(i) for i in range(2)]

    root = bpy.data.objects.new("Village", None)
    bpy.context.scene.collection.objects.link(root)

    target = RNG.randint(24, 36)
    houses = []                         # (merkez, yarıçap)
    tries = 0
    while len(houses) < target and tries < 4000:
        tries += 1
        x = RNG.uniform(-26, 26)
        c = path_center(x)
        k = PATH_PTS.index(min(PATH_PTS, key=lambda q: abs(q.x - x)))
        t = (PATH_PTS[min(k + 1, 124)] - PATH_PTS[max(k - 1, 0)]).normalized()
        n = Vector((-t.y, t.x)) * RNG.choice((-1, 1))
        off = RNG.uniform(4.8, 8.5) if RNG.random() < 0.7 else RNG.uniform(10.5, 17)
        p = c + n * off
        sx, sy, sz = RNG.uniform(0.8, 1.3), RNG.uniform(0.8, 1.2), RNG.uniform(0.9, 1.25)
        rad = 2.4 * max(sx, sy)
        if abs(p.x) > HALF - 4 or abs(p.y) > HALF - 4:
            continue
        if dist_to_path(p) < rad + 1.6:
            continue
        if any((p - q).length < rad + qr + 0.9 for q, qr in houses):
            continue
        d = c - p
        rot = math.atan2(d.x, -d.y) + RNG.uniform(-0.12, 0.12)   # ön yüz (-Y) yola baksın
        z = min(height(p.x + dx, p.y + dy) for dx in (-2, 2) for dy in (-2, 2))
        i = len(houses)
        wall = RNG.choice(list(WALLS))
        h = place(f"house_{i:02d}", body[wall], p.x, p.y, z, rot, (sx, sy, sz), root)
        kind = "gable" if RNG.random() < 0.6 else "hip"
        place(f"house_{i:02d}_roof", roofs[(kind, RNG.choice(list(ROOFS)))], 0, 0, 0, 0, (1, 1, 1), h)
        if RNG.random() < 0.45:
            place(f"house_{i:02d}_chimney", chim, RNG.choice((-1.2, 1.2)), 0.9, 0, 0, (1, 1, 1), h)
        houses.append((p, rad))

    def free_spot(rad, lo=3.0):
        for _ in range(300):
            p = Vector((RNG.uniform(-HALF + 2, HALF - 2), RNG.uniform(-HALF + 2, HALF - 2)))
            if dist_to_path(p) < lo + rad:
                continue
            if any((p - q).length < qr + rad + 0.6 for q, qr in houses):
                continue
            return p
        return None

    n_tree = RNG.randint(14, 22)
    n_rock = RNG.randint(6, 10)
    placed_t = placed_r = 0
    for i in range(n_tree):
        p = free_spot(1.6)
        if p is None:
            continue
        kind = "pine" if RNG.random() < 0.5 else "round"
        s = RNG.uniform(0.8, 1.35)
        place(f"tree_{i:02d}", trees[kind], p.x, p.y, height(p.x, p.y), RNG.uniform(0, 6.28), (s, s, s), root)
        houses.append((p, 1.6 * s))
        placed_t += 1
    for i in range(n_rock):
        p = free_spot(1.0, 2.2)
        if p is None:
            continue
        s = RNG.uniform(0.6, 1.4)
        place(f"rock_{i:02d}", rocks[i % 2], p.x, p.y, height(p.x, p.y) - 0.1, RNG.uniform(0, 6.28),
              (s, s, s), root)
        houses.append((p, 1.0 * s))
        placed_r += 1
    return target, sum(1 for o in bpy.data.objects if o.name.startswith("house_") and o.name.count("_") == 1), \
        placed_t, placed_r, tries


def tri_count():
    total = 0
    uniq = 0
    for me in bpy.data.meshes:
        me.calc_loop_triangles()
        uniq += len(me.loop_triangles)
    for ob in bpy.data.objects:
        if ob.type == "MESH":
            total += len(ob.data.loop_triangles)
    return total, uniq


def preview(path):
    sc = bpy.context.scene
    cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
    sc.collection.objects.link(cam)
    cam.location = (0, -44, 40)
    cam.rotation_euler = (Vector((0, 3, -3)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 30
    sc.camera = cam
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "MATERIAL"
    sc.display.shading.show_shadows = True
    sc.display.shading.show_cavity = True
    sc.render.resolution_x = sc.render.resolution_y = 1080
    sc.world = sc.world or bpy.data.worlds.new("W")
    sc.world.color = (0.55, 0.70, 0.88)
    # etiket: yalnız önizlemede (GLB'den SONRA ekleniyor, dışa aktarılan dosyada yok)
    cu = bpy.data.curves.new("label", "FONT")
    cu.body = f"seed {CFG['seed']}"
    cu.size = 0.09
    cu.extrude = 0.002
    lab = bpy.data.objects.new("label", cu)
    lab.data.materials.append(mat("label_dark", (0.08, 0.08, 0.10)))
    sc.collection.objects.link(lab)
    lab.parent = cam
    lab.location = (-0.54, 0.48, -1.0)
    sc.render.filepath = str(Path(path).resolve())
    bpy.ops.render.render(write_still=True)
    print("[preview]", sc.render.filepath, flush=True)


def main():
    for o in list(bpy.data.objects):            # --factory-startup sahnesindeki küp/kamera/ışık
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)
    t_build = time.perf_counter()
    build_ground()
    target, n_house, n_tree, n_rock, tries = build_village()
    t_built = time.perf_counter()
    tris, uniq = tri_count()
    n_obj = sum(1 for o in bpy.data.objects if o.type == "MESH")
    n_mesh = len(bpy.data.meshes)
    print(f"[village] seed={CFG['seed']} ev={n_house} (hedef {target}, {tries} deneme) ağaç={n_tree} "
          f"kaya={n_rock}", flush=True)
    print(f"[village] mesh nesnesi={n_obj} benzersiz mesh={n_mesh} üçgen(sahnede)={tris} "
          f"üçgen(benzersiz mesh toplamı)={uniq}", flush=True)
    print(f"[time] kurulum {t_built - t_build:.3f} sn", flush=True)

    out = Path(CFG["out"]).resolve()
    if CFG["no_instancing"]:
        for ob in bpy.data.objects:
            if ob.type == "MESH" and ob.data.users > 1:
                ob.data = ob.data.copy()
        print(f"[no-instancing] benzersiz mesh={len([m for m in bpy.data.meshes if m.users])}", flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out.with_suffix(".blend")))
    t_exp = time.perf_counter()
    bpy.ops.export_scene.gltf(
        filepath=str(out), export_format="GLB", export_yup=True, export_apply=False,
        export_animations=False, export_cameras=False, export_lights=False)
    t_exp_done = time.perf_counter()
    print(f"[gltf ok] {out} {out.stat().st_size} bayt, dışa aktarma {t_exp_done - t_exp:.3f} sn", flush=True)
    print(f"[time] betik başından GLB'ye {t_exp_done - T0:.3f} sn", flush=True)

    # Godot kamerası için yol (Godot ekseninde: x, y=yükseklik, z=-y_blender)
    meta = {"seed": CFG["seed"], "houses": n_house, "trees": n_tree, "rocks": n_rock,
            "mesh_objects": n_obj, "unique_meshes": n_mesh, "triangles": tris,
            "path": [[round(p.x, 3), round(height(p.x, p.y) + 0.07, 3), round(-p.y, 3)] for p in PATH_PTS]}
    out.with_suffix(".json").write_text(json.dumps(meta))
    if CFG["preview"]:
        Path(CFG["preview"]).parent.mkdir(parents=True, exist_ok=True)
        preview(CFG["preview"])
    print(f"[time] toplam {time.perf_counter() - T0:.3f} sn", flush=True)


main()
