"""Generate the scenery SVGs of the start page: the fir rows, the cottage and the horizon.

Run from anywhere:  python tools/generate_scenery.py

Writes static/scenery/*.svg (masks for the fir rows) and templates/scenery/*.svg (inlined into
index.html). Every part uses a fixed random seed, so the output only changes when this script does.
"""

import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def poly(points):
    return "M" + " L".join(f"{f(x)} {f(y)}" for x, y in points) + "Z"


# ---------------------------------------------------------------- tall firs

def fir_path(cx, top, bottom, base_w, rng, tier_gap=46):
    """A slender fir: clean, drooping branch tiers, then a sturdy trunk with flared roots."""
    crown_bottom = top + (bottom - top) * 0.78
    height = crown_bottom - top
    tiers = max(7, int(height / tier_gap))
    spacing = height / tiers
    trunk_w = max(8, base_w * 0.11)
    cmds = {1: [], -1: []}
    for side in (1, -1):
        c = cmds[side]
        for i in range(tiers):
            t = (i + 1) / tiers
            y_tip = top + t * height
            w_tip = max(4, base_w / 2 * (t ** 0.95) * rng.uniform(0.86, 1.08))
            if i > 2 and rng.random() < 0.15:
                w_tip *= rng.uniform(0.62, 0.8)  # now and then a shorter, broken-off branch
            y_notch = y_tip - spacing * rng.uniform(0.6, 0.8)
            w_notch = w_tip * rng.uniform(0.4, 0.56)  # always inside the tip, so the top stays clean
            droop = spacing * rng.uniform(0.06, 0.22) * t
            # in to the notch (underside of the tier above), then a curved branch out to the drooping tip
            c.append(("L", (cx + side * w_notch, y_notch)))
            ctrl = (cx + side * (w_notch + (w_tip - w_notch) * 0.55), y_notch + (y_tip - y_notch) * 0.25)
            c.append(("Q", ctrl, (cx + side * w_tip, y_tip + droop)))
            c.append(("L", (cx + side * (w_tip - 5), y_tip + droop + 2)))
        # trunk with flared roots
        c.append(("L", (cx + side * trunk_w, crown_bottom - 4)))
        c.append(("L", (cx + side * trunk_w * 1.08, bottom - 40)))
        c.append(("Q", (cx + side * trunk_w * 1.25, bottom - 10), (cx + side * trunk_w * 2.2, bottom)))

    def render(cmd):
        if cmd[0] == "L":
            return f"L{f(cmd[1][0])} {f(cmd[1][1])}"
        return f"Q{f(cmd[1][0])} {f(cmd[1][1])} {f(cmd[2][0])} {f(cmd[2][1])}"

    # Right side top to bottom, then the left side bottom to top (reversing curves keeps their control points)
    right = "".join(render(c) for c in cmds[1])
    left_pts = []
    prev = (cx, top)
    for c in cmds[-1]:
        end = c[1] if c[0] == "L" else c[2]
        left_pts.append((c, prev))
        prev = end
    left = ""
    for c, start in reversed(left_pts):
        if c[0] == "L":
            left += f"L{f(start[0])} {f(start[1])}"
        else:
            left += f"Q{f(c[1][0])} {f(c[1][1])} {f(start[0])} {f(start[1])}"
    last_left = cmds[-1][-1][2]
    return f"M{f(cx)} {f(top)}" + right + f"L{f(last_left[0])} {f(last_left[1])}" + left + "Z"


def fir_tile(name, width, height, firs, seed):
    rng = random.Random(seed)
    paths = []
    for cx, top, base_w in firs:
        # Repeat firs that cross the tile edge on the other side, so the tile repeats seamlessly
        offsets = [0]
        if cx - base_w / 2 < 0:
            offsets.append(width)
        if cx + base_w / 2 > width:
            offsets.append(-width)
        state = rng.getstate()
        for offset in offsets:
            rng.setstate(state)
            paths.append(f'<path d="{fir_path(cx + offset, top, height, base_w, rng)}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}">' + "".join(paths) + "</svg>\n")
    with open(f"{ROOT}/static/scenery/{name}", "w", encoding="utf-8") as file:
        file.write(svg)


# Same on-screen spacing as the mid row (the CSS draws far firs at 80 % of their height), but shifted
# by half a gap, so every far fir stands between two closer ones
fir_tile("firs-far.svg", 1375, 1600, [(454, 90, 290), (908, 0, 310), (1361, 150, 270)], 1)
fir_tile("firs-mid.svg", 1100, 1600, [(170, 80, 300), (560, 0, 330), (910, 170, 280)], 2)
fir_tile("fir-edge.svg", 600, 1600, [(300, 0, 540)], 3)


# ---------------------------------------------------------------- cottage scene

rng = random.Random(7)
out = []
add = out.append


def bezier(p0, p1, p2, t):
    return ((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0],
            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1])


def stone(x, y, w, h):
    r = min(w, h) * 0.38
    pts = [(x + r, y), (x + w - r, y), (x + w, y + r), (x + w, y + h - r),
           (x + w - r, y + h), (x + r, y + h), (x, y + h - r), (x, y + r)]
    return poly([(px + rng.uniform(-1.3, 1.3), py + rng.uniform(-1.3, 1.3)) for px, py in pts])


STONE_COLORS = ["#3d3558", "#372f50", "#433a5f", "#332b4a", "#3a3352"]


def stone_rows(x0, x1, y0, y1, row_h=(14, 18), stone_w=(16, 32), gap=2.6):
    y = y0
    row = 0
    while y < y1:
        h = rng.uniform(*row_h)
        x = x0 - (rng.uniform(0, stone_w[1]) if row % 2 else 0)
        while x < x1:
            w = rng.uniform(*stone_w)
            add(f'<path d="{stone(x, y, w - gap, h - gap)}" fill="{rng.choice(STONE_COLORS)}"/>')
            x += w
        y += h
        row += 1


# The gnarled old tree, left of the cottage
segments = []


def branch(x, y, angle, length, width, depth):
    px, py, a = x, y, angle
    for i in range(3):
        a += rng.uniform(-0.38, 0.38)
        nx, ny = px + math.cos(a) * length / 3, py - math.sin(a) * length / 3
        segments.append((px, py, nx, ny, width * (1 - 0.22 * (i + 1) / 3)))
        px, py = nx, ny
    if depth == 0 or width < 1.6:
        return
    count = rng.choice([2, 2, 3])
    for k in range(count):
        spread = (k - (count - 1) / 2) * 0.55
        branch(px, py, a + spread + rng.uniform(-0.45, 0.45),
               length * rng.uniform(0.62, 0.8), width * rng.uniform(0.55, 0.7), depth - 1)


branch(770, 478, math.pi / 2 + 0.12, 190, 36, 5)
for angle, length, width in [(math.pi + 0.25, 46, 16), (-0.2, 40, 14), (math.pi + 0.6, 30, 10), (0.35, 26, 9)]:
    x1, y1 = 770 + math.cos(angle) * length, 470 - math.sin(angle) * length
    segments.append((770, 462, x1, y1, width))

# Shrink the tree around its base until the whole crown fits below TREE_TOP (no cut-off branches)
TREE_TOP = 115
crown_top = min(min(y1, y2) - w / 2 for x1, y1, x2, y2, w in segments)
if crown_top < TREE_TOP:
    s = (470 - TREE_TOP) / (470 - crown_top)
    segments = [(770 + (x1 - 770) * s, 470 - (470 - y1) * s, 770 + (x2 - 770) * s, 470 - (470 - y2) * s, w * s)
                for x1, y1, x2, y2, w in segments]

add('<g class="gnarled-tree">')
for x1, y1, x2, y2, w in segments:
    add(f'<path d="M{f(x1)} {f(y1)} L{f(x2)} {f(y2)}" stroke-width="{f(w)}"/>')
add("</g>")

# Glowing mushrooms between the roots
add('<g class="mushrooms">')
for x, y, color in [(728, 470, "#8ff0ff"), (741, 473, "#c9a6ff"), (800, 472, "#8ff0ff"), (812, 469, "#8ff0ff"),
                    (1112, 458, "#c9a6ff"), (1124, 461, "#8ff0ff")]:
    add(f'<circle cx="{x}" cy="{y - 9}" r="11" fill="{color}" class="mushroom-glow"/>')
    add(f'<rect x="{x - 1.5}" y="{y - 8}" width="3" height="8" rx="1" fill="#d6d0f0"/>')
    add(f'<path d="M{x - 6} {y - 7.5} Q{x} {y - 15} {x + 6} {y - 7.5} Z" fill="{color}"/>')
add("</g>")

# Woodpile against the left wall
add('<g class="woodpile">')
for row, (count, y) in enumerate([(4, 445), (3, 432), (2, 419)]):
    for i in range(count):
        x = 842 + row * 7 + i * 14
        add(f'<circle cx="{x}" cy="{y}" r="7" fill="#2a1c14" stroke="#4a3020" stroke-width="1.5"/>')
        add(f'<circle cx="{x}" cy="{y}" r="3" fill="none" stroke="#3a2618" stroke-width="1"/>')
add("</g>")

# Chimney (drawn before the roof, which covers its base)
add('<clipPath id="chimney-clip"><path d="M1030 280 L1057 278 L1061 205 L1036 202 Z"/></clipPath>')
add('<path d="M1030 280 L1057 278 L1061 205 L1036 202 Z" fill="#1a1629"/>')
add('<g clip-path="url(#chimney-clip)">')
stone_rows(1025, 1066, 200, 282, row_h=(10, 13), stone_w=(10, 16), gap=2)
add("</g>")
add('<path d="M1031 205 L1066 200 L1067 207 L1032 211 Z" fill="#2a2440"/>')

# Front gable wall made of stones
WALL = "M880 456 Q876 396 884 338 L978 222 L1070 334 Q1077 396 1074 458 Z"
add(f'<clipPath id="wall-clip"><path d="{WALL}"/></clipPath>')
add(f'<path d="{WALL}" fill="#1a1629"/>')
add('<g clip-path="url(#wall-clip)">')
stone_rows(866, 1090, 218, 460)
# Warm light from the windows and door on the stones
add('<ellipse cx="976" cy="405" rx="120" ry="80" fill="url(#hearth-light)"/>')
# Shadow under the roof edge
add('<path d="M872 346 Q926 276 979 216 Q1033 272 1082 342" fill="none" stroke="#0c0a18" stroke-width="16" opacity="0.65"/>')
add("</g>")

# Thatched roof: thick, sagging, with a bumpy edge
outer_left = [bezier((846, 354), (902, 262), (980, 180), i / 40) for i in range(41)]
outer_right = [bezier((980, 180), (1054, 258), (1108, 350), i / 40) for i in range(1, 41)]
outer = []
for i, (x, y) in enumerate(outer_left + outer_right):
    bump = 2.6 * math.sin(i * 1.7) + rng.uniform(-1, 1)
    outer.append((x, y - bump))
inner_right = [bezier((1083, 343), (1034, 272), (979, 215), i / 30) for i in range(31)]
inner_left = [bezier((979, 215), (927, 276), (871, 347), i / 30) for i in range(1, 31)]
roof = (poly(outer + [(1112, 358), (1096, 362)] + inner_right + inner_left + [(858, 364), (842, 360)]))
add(f'<path d="{roof}" fill="url(#roof-shade)"/>')
add('<g class="thatch">')
for _ in range(170):
    left = rng.random() < 0.5
    t = rng.uniform(0.03, 0.97)
    if left:
        ox, oy = bezier((846, 354), (902, 262), (980, 180), t)
        ix, iy = bezier((871, 347), (927, 276), (979, 215), t)
    else:
        ox, oy = bezier((1108, 350), (1054, 258), (980, 180), t)
        ix, iy = bezier((1083, 343), (1034, 272), (979, 215), t)
    depth = rng.uniform(0.1, 0.85)
    x, y = ox + (ix - ox) * depth, oy + (iy - oy) * depth
    dx, dy = (-1 if left else 1) * 0.62, 0.78  # down the slope
    length = rng.uniform(7, 15)
    add(f'<path d="M{f(x)} {f(y)} l{f(dx * length)} {f(dy * length)}"/>')
add("</g>")
for x, y, rx, ry in [(925, 268, 14, 5), (1050, 290, 18, 6), (968, 196, 8, 4)]:
    add(f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="#2f4a45" opacity="0.5" transform="rotate({rng.uniform(-40, 40):.0f} {x} {y})"/>')
# A little crescent moon on top of the roof
add('<path d="M980 181 L983 160" stroke="#2a2440" stroke-width="2.5"/>')
add('<path d="M988 146 A9 9 0 1 0 988 162 A6.5 6.5 0 1 1 988 146 Z" fill="#e3b866" class="roof-moon"/>')

# Round attic window
add('<circle cx="978" cy="292" r="19" fill="url(#window-glow)" class="flicker"/>')
add('<circle cx="978" cy="292" r="12" fill="#ffc56e" stroke="#2a2440" stroke-width="3"/>')
add('<path d="M978 280 V304 M966 292 H990" stroke="#2a2440" stroke-width="2"/>')

# Left window with crooked shutters
add('<rect x="892" y="350" width="52" height="58" rx="10" fill="url(#window-glow)" class="flicker"/>')
add('<path d="M902 398 V372 Q902 358 918 358 Q934 358 934 372 V398 Z" fill="#ffc56e" stroke="#2a2440" stroke-width="3"/>')
add('<path d="M918 358 V398 M902 380 H934" stroke="#2a2440" stroke-width="2.2"/>')
add('<path d="M897 398 H939 L941 404 H895 Z" fill="#4a4166"/>')
add('<path d="M888 360 L899 358 L899 400 L887 402 Z" fill="#2a1c14" transform="rotate(-4 893 380)"/>')
add('<path d="M890 370 h8 M890 380 h8 M890 390 h8" stroke="#3d2a1c" stroke-width="1.5" transform="rotate(-4 893 380)"/>')
add('<path d="M937 362 L948 364 L948 404 L937 402 Z" fill="#2a1c14" transform="rotate(9 937 362)"/>')
add('<path d="M939 374 h8 M939 384 h8 M939 394 h8" stroke="#3d2a1c" stroke-width="1.5" transform="rotate(9 937 362)"/>')

# Right window with a flower box
add('<rect x="1014" y="356" width="44" height="50" rx="10" fill="url(#window-glow)" class="flicker"/>')
add('<path d="M1023 398 V378 Q1023 366 1036 366 Q1049 366 1049 378 V398 Z" fill="#ffc56e" stroke="#2a2440" stroke-width="3"/>')
add('<path d="M1036 366 V398 M1023 384 H1049" stroke="#2a2440" stroke-width="2"/>')
add('<path d="M1018 398 H1054 L1052 408 H1020 Z" fill="#3a2618"/>')
for i in range(9):
    x = 1021 + i * 3.8 + rng.uniform(-1, 1)
    add(f'<circle cx="{f(x)}" cy="{f(396 - rng.uniform(0, 4))}" r="2.2" fill="{rng.choice(["#e88aa8", "#f2c46d", "#c9a6ff"])}"/>')

# Arched door, slightly ajar, in a ring of stones
add('<g class="door-arch">')
for i in range(9):
    a0, a1 = math.pi * i / 9, math.pi * (i + 1) / 9
    r0, r1 = 23, 33
    pts = [(976 + math.cos(a) * r, 404 - math.sin(a) * r) for a, r in [(a0, r0), (a0, r1), (a1, r1), (a1, r0)]]
    add(f'<path d="{poly(pts)}" fill="{rng.choice(["#4a4166", "#453c60", "#4f466c"])}" stroke="#1a1629" stroke-width="1.5"/>')
add("</g>")
add('<path d="M955 456 V404 Q955 381 976 381 Q997 381 997 404 V456 Z" fill="#3a2416"/>')
add('<path d="M963 456 V388 M971 456 V382 M980 456 V382 M989 456 V388" stroke="#2a1a10" stroke-width="1.5"/>')
add('<path d="M955 398 H982 M955 436 H982" stroke="#1c120c" stroke-width="3"/>')
add('<circle cx="990" cy="424" r="2.5" fill="#e3b866"/>')
add('<path d="M993 456 V404 Q995 393 997 404 V456 Z" fill="#ffb54f" class="flicker"/>')
add('<ellipse cx="976" cy="459" rx="32" ry="5" fill="#4a4166"/>')

# Lantern on a bracket next to the door
add('<path d="M1004 370 H1015 V376" stroke="#2a2440" stroke-width="2.5" fill="none"/>')
add('<circle cx="1015" cy="386" r="16" fill="url(#window-glow)" class="flicker"/>')
add('<path d="M1010 377 H1020 L1021 393 H1009 Z" fill="#ffd27a" stroke="#2a2440" stroke-width="2"/>')

# Bushes at the foot of the walls
add('<g class="bushes">')
for x, y, r in [(872, 452, 12), (884, 448, 10), (1070, 450, 13), (1084, 455, 11), (1060, 456, 9)]:
    add(f'<circle cx="{x}" cy="{y}" r="{r}"/>')
add("</g>")

# Warm light pool and stepping stones leading away from the door
add('<ellipse cx="972" cy="470" rx="190" ry="32" fill="url(#hearth-light)"/>')
for x, y, rx in [(962, 472, 17), (938, 484, 19), (908, 496, 21), (872, 508, 23)]:
    add(f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{f(rx * 0.26)}" fill="#2e2844" stroke="#ffb54f" stroke-opacity="0.25"/>')

cottage = "\n".join(out)

# Ground with grass tufts along its edge
ground_top = [bezier((0, 478), (500, 456), (1200, 460), i / 200) for i in range(201)]
tufts = []
for x, y in ground_top[::2]:
    h = rng.uniform(3, 10)
    tufts.append(f"M{f(x - 2.5)} {f(y + 1)} L{f(x + rng.uniform(-2, 2))} {f(y - h)} L{f(x + 2.5)} {f(y + 1)}Z")
ground = poly(ground_top + [(1200, 520), (0, 520)])

scene = f'''<svg class="hut-scene" viewBox="0 0 1200 520" preserveAspectRatio="xMaxYMax slice" aria-hidden="true">
    <defs>
        <radialGradient id="hearth-light">
            <stop offset="0" stop-color="#ffb547" stop-opacity="0.4"/>
            <stop offset="1" stop-color="#ffb547" stop-opacity="0"/>
        </radialGradient>
        <radialGradient id="window-glow">
            <stop offset="0" stop-color="#ffb547" stop-opacity="0.9"/>
            <stop offset="1" stop-color="#ffb547" stop-opacity="0"/>
        </radialGradient>
        <linearGradient id="roof-shade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#2b2244"/>
            <stop offset="1" stop-color="#191330"/>
        </linearGradient>
        <!-- A fixed region: the puffs drift far beyond their starting point -->
        <filter id="steam-blur" filterUnits="userSpaceOnUse" x="980" y="0" width="160" height="240">
            <feGaussianBlur stdDeviation="4"/>
        </filter>
        <filter id="soft-glow" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="5"/>
        </filter>
    </defs>

    <!-- Steam rising from the chimney -->
    <g class="steam" filter="url(#steam-blur)">
        <circle cx="1049" cy="196" r="8"/>
        <circle cx="1049" cy="196" r="10"/>
        <circle cx="1049" cy="196" r="9"/>
        <circle cx="1049" cy="196" r="11"/>
    </g>

    <!-- The cottage, the old tree and everything around them (generated) -->
{cottage}

    <!-- The forest floor -->
    <path class="ground" d="{ground}"/>
    <path class="ground" d="{''.join(tufts)}"/>
</svg>
'''

with open(f"{ROOT}/templates/scenery/hut.svg", "w", encoding="utf-8") as file:
    file.write(scene)



# ---------------------------------------------------------------- the horizon with a distant city

rng = random.Random(11)
out = []
add = out.append


def ridge(y_base, amp, step, jag):
    """A mountain ridge across the whole width as a list of points."""
    pts, x = [], 0
    while x <= 1600:
        y = y_base - amp * (0.55 + 0.45 * math.sin(x / 170 + y_base)) - rng.uniform(0, jag)
        pts.append((x, y))
        x += rng.uniform(step * 0.6, step * 1.4)
    pts.append((1600, y_base - amp * 0.5))
    return pts


far = ridge(205, 70, 60, 26)
add(f'<path class="mountains-far" d="{poly(far + [(1600, 300), (0, 300)])}"/>')
near = ridge(250, 30, 90, 8)
add(f'<path class="hills" d="{poly(near + [(1600, 300), (0, 300)])}"/>')

# The city: a glow rising into the sky, two rows of many small buildings, towers with blinking lights
CITY_LEFT, CITY_RIGHT, CITY_BASE = 860, 1440, 252

add('<rect class="city-dome" x="780" y="60" width="740" height="200" mask="url(#dome-fade)"/>')


def skyline(row, height_range, width_range, lit_chance, color_class, window_classes):
    shapes, lights = [], []
    x = CITY_LEFT + rng.uniform(0, 6)
    while x < CITY_RIGHT:
        w = rng.uniform(*width_range)
        # taller in the centre of the city, lower towards the outskirts
        centre = 1 - abs((x - (CITY_LEFT + CITY_RIGHT) / 2) / ((CITY_RIGHT - CITY_LEFT) / 2)) ** 1.6
        h = rng.uniform(*height_range) * (0.35 + 0.9 * centre)
        top = CITY_BASE - h
        shapes.append(f"M{f(x)} {CITY_BASE + 6} L{f(x)} {f(top)} L{f(x + w)} {f(top)} L{f(x + w)} {CITY_BASE + 6}Z")
        if rng.random() < 0.18 and w > 4:  # pointed or stepped roof
            if rng.random() < 0.5:
                shapes.append(f"M{f(x)} {f(top)} L{f(x + w / 2)} {f(top - w * 0.8)} L{f(x + w)} {f(top)}Z")
            else:
                shapes.append(f"M{f(x + w * 0.25)} {f(top)} L{f(x + w * 0.25)} {f(top - 4)} L{f(x + w * 0.75)} {f(top - 4)} L{f(x + w * 0.75)} {f(top)}Z")
        wy = top + 2
        while wy < CITY_BASE - 2:
            wx = x + 1
            while wx < x + w - 1.5:
                if rng.random() < lit_chance:
                    lights.append((wx, wy, rng.choice(window_classes)))
                wx += 2.4
            wy += 3.1
        x += w + rng.uniform(0, 1.2)
    add(f'<path class="{color_class}" d="{"".join(shapes)}"/>')
    add(f'<g class="city-windows city-windows-{row}">')
    for i, (wx, wy, cls) in enumerate(lights):
        extra = " flicker-slow" if i % 23 == 0 else ""
        add(f'<rect class="{cls}{extra}" x="{f(wx)}" y="{f(wy)}" width="1.1" height="1.5"/>')
    add("</g>")


skyline("back", (14, 58), (4, 10), 0.16, "city-back", ["warm", "warm", "cool"])

# Landmarks: a TV tower, a cathedral with two spires and two high-rises with aircraft warning lights
add('<path class="city-back" d="'
    'M1004.5 252 L1005.7 178 L1007.3 178 L1008.5 252Z M1002.5 184 A4 3.6 0 0 1 1010.5 184 A4 3.6 0 0 1 1002.5 184Z M1006 178 L1006.5 162 L1007 178Z'
    'M1186 252 L1186 214 L1222 214 L1222 252Z M1188 214 L1188 182 L1191.5 168 L1195 182 L1195 214Z M1213 214 L1213 182 L1216.5 168 L1220 182 L1220 214Z'
    'M1080 252 L1080 176 L1092 176 L1092 252Z M1268 252 L1268 186 L1278 186 L1278 252Z"/>')
for x, y in [(1006.5, 161), (1086, 175), (1273, 185)]:
    add(f'<circle class="warning-light" cx="{x}" cy="{y}" r="1.3"/>')

skyline("front", (6, 30), (3, 8), 0.24, "city-front", ["warm", "warm", "warm", "cool"])

# The hill the city stands on, in front of the building bases
add(f'<path class="hills" d="M{CITY_LEFT - 60} 256 Q{(CITY_LEFT + CITY_RIGHT) / 2} 238 {CITY_RIGHT + 60} 256 L{CITY_RIGHT + 60} 300 L{CITY_LEFT - 60} 300Z"/>')

# A few lonely farmhouse lights on the hills
for hx, hy in [(240, 262), (520, 255), (700, 266), (1420, 258)]:
    add(f'<circle class="farm-light" cx="{hx}" cy="{hy}" r="1.6"/>')

horizon = "\n    ".join(out)
with open(f"{ROOT}/templates/scenery/horizon.svg", "w", encoding="utf-8") as file:
    file.write(f"""<svg class="horizon" viewBox="0 0 1600 300" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
    <defs>
        <linearGradient id="city-light" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0" stop-color="#ffb47a" stop-opacity="0.42"/>
            <stop offset="0.35" stop-color="#ff9cb4" stop-opacity="0.16"/>
            <stop offset="1" stop-color="#b48cff" stop-opacity="0"/>
        </linearGradient>
        <linearGradient id="dome-sides" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stop-color="#000"/>
            <stop offset="0.15" stop-color="#262626"/>
            <stop offset="0.3" stop-color="#8c8c8c"/>
            <stop offset="0.45" stop-color="#fff"/>
            <stop offset="0.55" stop-color="#fff"/>
            <stop offset="0.7" stop-color="#8c8c8c"/>
            <stop offset="0.85" stop-color="#262626"/>
            <stop offset="1" stop-color="#000"/>
        </linearGradient>
        <mask id="dome-fade" maskUnits="userSpaceOnUse" x="780" y="60" width="740" height="200">
            <rect x="780" y="60" width="740" height="200" fill="url(#dome-sides)"/>
        </mask>
    </defs>
    {horizon}
</svg>
""")
print("Scenery written to static/scenery/ and templates/scenery/")
