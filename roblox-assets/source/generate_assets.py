"""Generate a low-poly Roblox asset pack with Blender (bpy).

Usage:
    python generate_assets.py <output_dir>

Every asset shares one palette texture (textures/palette.png). Each face's UVs
point at the centre of one colour swatch, so an asset imports into Roblox as a
single MeshPart with one texture and no SurfaceAppearance needed.
Units are metres (Blender default); 1 m is roughly 3.57 studs in Roblox.
"""
import math
import os
import random
import sys

import bpy  # must come before bmesh when running Blender as a Python module
import bmesh
from mathutils import Euler, Matrix, Vector

OUT = os.path.abspath(sys.argv[-1] if len(sys.argv) > 1 else "out")
random.seed(7)

# --- Palette ---------------------------------------------------------------

PALETTE = {
    "wood_dark": (0.36, 0.22, 0.12),
    "wood": (0.55, 0.36, 0.20),
    "wood_light": (0.74, 0.54, 0.32),
    "leaf_dark": (0.16, 0.40, 0.20),
    "leaf": (0.28, 0.58, 0.24),
    "leaf_light": (0.48, 0.72, 0.30),
    "stone_dark": (0.36, 0.36, 0.40),
    "stone": (0.54, 0.54, 0.57),
    "stone_light": (0.70, 0.70, 0.72),
    "gold": (0.98, 0.78, 0.22),
    "gold_dark": (0.80, 0.56, 0.12),
    "iron": (0.28, 0.28, 0.31),
    "steel": (0.80, 0.82, 0.86),
    "leather": (0.42, 0.21, 0.12),
    "red": (0.80, 0.20, 0.15),
    "fire_orange": (1.00, 0.48, 0.10),
    "fire_yellow": (1.00, 0.86, 0.30),
    "ember": (0.20, 0.10, 0.08),
}
NAMES = list(PALETTE)
GRID = 8
TEX = 256


def swatch_uv(color):
    i = NAMES.index(color)
    return ((i % GRID + 0.5) / GRID, (i // GRID + 0.5) / GRID)


def make_palette(path):
    cell = TEX // GRID
    px = [0.0] * (TEX * TEX * 4)
    for y in range(TEX):
        for x in range(TEX):
            i = (y // cell) * GRID + x // cell
            r, g, b = PALETTE[NAMES[i]] if i < len(NAMES) else (1, 0, 1)
            o = (y * TEX + x) * 4
            px[o:o + 4] = (r, g, b, 1.0)
    img = bpy.data.images.new("palette_tmp", TEX, TEX)
    img.pixels = px
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    return bpy.data.images.load(path)


# --- Mesh building helpers (each returns a painted bmesh part) --------------

def uv_layer(bm):
    return bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")


def finish_part(bm, color, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), jitter=0.0):
    if jitter:
        for v in bm.verts:
            v.co += Vector([random.uniform(-jitter, jitter) for _ in range(3)])
    m = Matrix.LocRotScale(Vector(loc), Euler(rot), Vector(scale))
    bmesh.ops.transform(bm, matrix=m, verts=bm.verts)
    uv = uv_layer(bm)
    u = swatch_uv(color)
    for f in bm.faces:
        f.smooth = False
        for l in f.loops:
            l[uv].uv = u
    return bm


def cube(size, color, **kw):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    return finish_part(bm, color, **kw)


def cyl(r1, r2, depth, color, seg=8, **kw):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r1, radius2=r2, depth=depth)
    return finish_part(bm, color, **kw)


def ico(radius, color, subdiv=1, **kw):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius)
    return finish_part(bm, color, **kw)


def hull(points, color, **kw):
    bm = bmesh.new()
    verts = [bm.verts.new(p) for p in points]
    res = bmesh.ops.convex_hull(bm, input=verts)
    junk = [g for g in res["geom_interior"] + res["geom_unused"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.delete(bm, geom=junk, context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_part(bm, color, **kw)


def lathe(profile, color, seg=12, **kw):
    """Revolve a list of (radius, z) points around Z."""
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        if r == 0:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(a), r * math.sin(a), z))
                          for a in (2 * math.pi * i / seg for i in range(seg))])
    for a, b in zip(rings, rings[1:]):
        for i in range(seg):
            j = (i + 1) % seg
            if len(a) == 1:
                bm.faces.new((a[0], b[i], b[j]))
            elif len(b) == 1:
                bm.faces.new((a[i], a[j], b[0]))
            else:
                bm.faces.new((a[i], a[j], b[j], b[i]))
    if len(rings[0]) > 1:
        bm.faces.new(list(reversed(rings[0])))
    if len(rings[-1]) > 1:
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_part(bm, color, **kw)


def half_cyl(radius, length, zscale, color, seg=12, **kw):
    """Upper half of a cylinder lying along X (chest lid shape), flat side down."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=radius, radius2=radius, depth=length)
    bmesh.ops.rotate(bm, matrix=Matrix.Rotation(math.pi / 2, 3, "Y"), verts=bm.verts)
    bmesh.ops.scale(bm, vec=(1, 1, zscale), verts=bm.verts)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, 0), plane_no=(0, 0, 1), clear_inner=True)
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_part(bm, color, **kw)


# --- Object assembly ---------------------------------------------------------

MATERIAL = None


def make_object(name, parts, origin="bottom"):
    """Merge parts into one mesh object. origin: 'bottom', 'center' or an (x, y, z) point."""
    bm = bmesh.new()
    uv_layer(bm)
    for p in parts:
        me = bpy.data.meshes.new("tmp")
        p.to_mesh(me)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        p.free()
    lo = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
    hi = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
    if origin == "bottom":
        pivot = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    elif origin == "center":
        pivot = (lo + hi) / 2
    else:
        pivot = Vector(origin)
    bmesh.ops.translate(bm, vec=-pivot, verts=bm.verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATERIAL)
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def tri_count(objs):
    return sum(len(p.vertices) - 2 for o in objs for p in o.data.polygons)


# --- Assets -------------------------------------------------------------------

def pine_tree():
    parts = [cyl(0.16, 0.12, 0.9, "wood_dark", seg=7, loc=(0, 0, 0.45))]
    for z, r, c in ((0.9, 1.05, "leaf_dark"), (1.55, 0.82, "leaf"), (2.15, 0.58, "leaf_light")):
        parts.append(cyl(r, 0.0, 1.25, c, seg=8, loc=(0, 0, z + 0.62),
                         rot=(0, 0, random.uniform(0, 1)), jitter=0.05))
    return [make_object("PineTree", parts)]


def oak_tree():
    parts = [cyl(0.26, 0.16, 1.5, "wood", seg=7, loc=(0, 0, 0.75)),
             cyl(0.08, 0.05, 0.7, "wood", seg=5, loc=(0.25, 0, 1.4), rot=(0, 0.8, 0))]
    for loc, r, c in (((0, 0, 2.1), 0.95, "leaf"), ((0.65, 0.2, 1.75), 0.65, "leaf_dark"),
                      ((-0.55, -0.25, 1.85), 0.7, "leaf_light"), ((0.1, -0.5, 2.4), 0.55, "leaf")):
        parts.append(ico(r, c, loc=loc, jitter=0.1))
    return [make_object("OakTree", parts)]


def rocks():
    parts = [ico(0.75, "stone", loc=(0, 0, 0.35), scale=(1.3, 1.0, 0.75), jitter=0.12),
             ico(0.4, "stone_dark", loc=(0.95, 0.35, 0.18), scale=(1.1, 1.0, 0.8), jitter=0.07),
             ico(0.25, "stone_light", loc=(-0.85, -0.45, 0.1), jitter=0.05)]
    return [make_object("Rocks", parts)]


def treasure_chest():
    base = [cube((1.0, 0.62, 0.5), "wood", loc=(0, 0, 0.25)),
            cube((1.02, 0.64, 0.06), "iron", loc=(0, 0, 0.03))]
    lid = [half_cyl(0.31, 1.0, 0.65, "wood", loc=(0, 0, 0.5))]
    for x in (-0.36, 0.36):
        base.append(cube((0.08, 0.66, 0.52), "gold_dark", loc=(x, 0, 0.25)))
        lid.append(half_cyl(0.33, 0.08, 0.68, "gold_dark", loc=(x, 0, 0.5)))
    lid.append(cube((0.14, 0.06, 0.16), "gold", loc=(0, -0.33, 0.52)))
    lid.append(cube((0.04, 0.07, 0.05), "iron", loc=(0, -0.36, 0.5)))
    b = make_object("TreasureChest_Base", base)
    # Lid pivot sits on the back hinge line so it can be rotated open.
    l = make_object("TreasureChest_Lid", lid, origin=(0, 0.31, 0.5))
    l.location = (0, 0.31, 0.5)
    return [b, l]


def coin():
    parts = [cyl(0.35, 0.35, 0.08, "gold", seg=16, rot=(math.pi / 2, 0, 0)),
             cyl(0.26, 0.26, 0.1, "gold_dark", seg=16, rot=(math.pi / 2, 0, 0))]
    star = []
    for i in range(10):
        a = math.pi / 2 + i * math.pi / 5
        r = 0.18 if i % 2 == 0 else 0.08
        star.append((r * math.cos(a), r * math.sin(a)))
    # Raised star on both faces: thin prisms built from star triangles.
    for side in (-1, 1):
        for i in range(10):
            p0, p1 = star[i], star[(i + 1) % 10]
            pts = [(0, 0), p0, p1]
            y0, y1 = side * 0.05, side * 0.075
            parts.append(hull([(x, y0, z) for x, z in pts] + [(x, y1, z) for x, z in pts], "gold"))
    return [make_object("Coin", parts, origin="center")]


def crate():
    s = 1.0
    parts = [cube((s * 0.96, s * 0.96, s * 0.96), "wood_light", loc=(0, 0, s / 2))]
    t, h = 0.09, s / 2
    for x in (-1, 1):
        for y in (-1, 1):
            parts.append(cube((t, t, s), "wood_dark", loc=(x * (h - t / 2), y * (h - t / 2), h)))
    for z in (t / 2, s - t / 2):
        for y in (-1, 1):
            parts.append(cube((s, t, t), "wood_dark", loc=(0, y * (h - t / 2), z)))
        for x in (-1, 1):
            parts.append(cube((t, s, t), "wood_dark", loc=(x * (h - t / 2), 0, z)))
    diag = math.sqrt(2) * (s - 2 * t)
    for y in (-1, 1):
        parts.append(cube((diag, 0.04, 0.1), "wood", loc=(0, y * (h - 0.01), h), rot=(0, math.pi / 4, 0)))
    for x in (-1, 1):
        parts.append(cube((0.04, diag, 0.1), "wood", loc=(x * (h - 0.01), 0, h), rot=(-math.pi / 4, 0, 0)))
    return [make_object("Crate", parts)]


def sword():
    w, d = 0.065, 0.018
    blade = [(x, y, z) for z in (0.0, 0.85) for x, y in ((w, 0), (-w, 0), (0, d), (0, -d))] + [(0, 0, 1.02)]
    parts = [hull(blade, "steel", loc=(0, 0, 0.05)),
             hull([(0.003, s * 0.02, z) for s in (-1, 1) for z in (0.06, 0.9)] +
                  [(-0.003, s * 0.02, z) for s in (-1, 1) for z in (0.06, 0.9)], "stone_light"),
             cube((0.34, 0.07, 0.06), "gold_dark", loc=(0, 0, 0.03)),
             ico(0.035, "red", loc=(0, 0, 0.03), scale=(1, 1.4, 1)),
             cyl(0.03, 0.028, 0.26, "leather", seg=8, loc=(0, 0, -0.13)),
             ico(0.05, "gold", loc=(0, 0, -0.29))]
    # Origin at the middle of the grip: matches a Roblox Tool's Handle grip point.
    return [make_object("Sword", parts, origin=(0, 0, -0.13))]


def fence():
    parts = []
    for x in (-1.0, 1.0):
        p = 0.07
        pts = [(sx * p, sy * p, z) for sx in (-1, 1) for sy in (-1, 1) for z in (0.0, 1.0)] + [(0, 0, 1.15)]
        parts.append(hull(pts, "wood_dark", loc=(x, 0, 0)))
    for z in (0.35, 0.75):
        parts.append(cube((2.1, 0.05, 0.16), "wood", loc=(0, 0, z), rot=(0, random.uniform(-0.02, 0.02), 0)))
    return [make_object("FenceSegment", parts)]


def barrel():
    prof = [(0.36 * (1 + 0.14 * math.sin(math.pi * z)), z * 1.0) for z in (0, 0.2, 0.4, 0.6, 0.8, 1.0)]
    parts = [lathe(prof, "wood", seg=12)]
    for z in (0.12, 0.88):
        r = 0.36 * (1 + 0.14 * math.sin(math.pi * z)) + 0.012
        parts.append(lathe([(r, z - 0.04), (r, z + 0.04)], "iron", seg=12))
    parts.append(lathe([(0.32, 0.99), (0.32, 1.01)], "wood_dark", seg=12))
    return [make_object("Barrel", parts)]


def campfire():
    parts = []
    for i in range(9):
        a = i * 2 * math.pi / 9
        parts.append(ico(0.13, random.choice(["stone", "stone_dark", "stone_light"]),
                         loc=(0.55 * math.cos(a), 0.55 * math.sin(a), 0.06), scale=(1.2, 1, 0.7), jitter=0.03))
    for i in range(5):
        a = i * 2 * math.pi / 5 + 0.3
        parts.append(cyl(0.06, 0.05, 0.75, "wood", seg=6, loc=(0.18 * math.cos(a), 0.18 * math.sin(a), 0.25),
                         rot=(0, -0.95, a)))
    parts.append(cyl(0.3, 0.3, 0.03, "ember", seg=10, loc=(0, 0, 0.015)))
    parts.append(cyl(0.22, 0.0, 0.6, "fire_orange", seg=6, loc=(0, 0, 0.35), jitter=0.03))
    for i in range(3):
        a = i * 2 * math.pi / 3
        parts.append(cyl(0.11, 0.0, 0.38, "fire_orange", seg=5,
                         loc=(0.12 * math.cos(a), 0.12 * math.sin(a), 0.22), jitter=0.02))
    parts.append(cyl(0.12, 0.0, 0.4, "fire_yellow", seg=5, loc=(0, 0, 0.3), rot=(0, 0, 0.5)))
    return [make_object("Campfire", parts)]


ASSETS = [pine_tree, oak_tree, rocks, treasure_chest, coin, crate, sword, fence, barrel, campfire]


# --- Export & render --------------------------------------------------------

def select_only(objs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def export(name, objs):
    select_only(objs)
    bpy.ops.export_scene.fbx(filepath=f"{OUT}/fbx/{name}.fbx", use_selection=True,
                             path_mode="COPY", embed_textures=True, mesh_smooth_type="FACE",
                             add_leaf_bones=False, bake_anim=False)
    bpy.ops.export_scene.gltf(filepath=f"{OUT}/glb/{name}.glb", export_format="GLB", use_selection=True)


def bounds(objs):
    bpy.context.view_layer.update()  # refresh matrix_world after moving objects
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def setup_render():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 48
    try:
        sc.cycles.use_denoising = True
    except Exception:
        pass
    sc.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.62, 0.78, 0.95, 1)
    bg.inputs["Strength"].default_value = 0.6
    sc.world = world
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 3.5
    sun.angle = 0.15
    so = bpy.data.objects.new("Sun", sun)
    so.rotation_euler = (math.radians(50), 0, math.radians(35))
    sc.collection.objects.link(so)
    gm = bpy.data.materials.new("Ground")
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.32, 0.55, 0.25, 1)
    bpy.ops.mesh.primitive_plane_add(size=200)
    bpy.context.object.data.materials.append(gm)
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    return cam


def frame(cam, objs, direction=(1.0, -1.35, 0.75), pad=1.15):
    lo, hi = bounds(objs)
    center = (lo + hi) / 2
    radius = (hi - lo).length / 2
    d = Vector(direction).normalized()
    fov = cam.data.angle
    cam.location = center + d * (radius * pad / math.sin(fov / 2))
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()


def render(path, x, y):
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = x, y
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for sub in ("fbx", "glb", "textures", "previews"):
        os.makedirs(f"{OUT}/{sub}", exist_ok=True)

    global MATERIAL
    img = make_palette(f"{OUT}/textures/palette.png")
    MATERIAL = bpy.data.materials.new("Palette")
    MATERIAL.use_nodes = True
    nt = MATERIAL.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.85
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Closest"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

    built = []
    for fn in ASSETS:
        objs = fn()
        name = objs[0].name.split("_")[0]
        export(name, objs)
        lo, hi = bounds(objs)
        size = hi - lo
        print(f"ASSET {name}: {tri_count(objs)} tris, {size.x:.2f} x {size.y:.2f} x {size.z:.2f} m "
              f"(~{size.z / 0.28:.1f} studs tall)")
        built.append((name, objs))

    cam = setup_render()
    for name, objs in built:
        if name == "Coin":  # origin is centred, so lift it off the ground for previews
            for o in objs:
                o.location.z = 0.6

    # Thumbnails: hide all but one asset at a time.
    for name, objs in built:
        for _, other in built:
            for o in other:
                o.hide_render = other is not objs
        frame(cam, objs)
        render(f"{OUT}/previews/{name}.png", 512, 512)

    # Showcase: lay everything out in a row with the coin floating.
    for _, objs in built:
        for o in objs:
            o.hide_render = False
    x = 0.0
    for name, objs in built:
        lo, hi = bounds(objs)
        w = hi.x - lo.x
        shift = Vector((x - lo.x, 0.0, 0.0))
        for o in objs:
            o.location += shift
        x += w + 0.6
    frame(cam, [o for _, objs in built for o in objs], direction=(0.0, -1.0, 0.32), pad=0.98)
    render(f"{OUT}/previews/showcase.png", 1600, 700)

    bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/source/roblox_assets.blend")


main()
