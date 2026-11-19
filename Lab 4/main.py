import gc
import math
import random
import sys
import threading
import time

try:
    import tkinter as tk
except ImportError:
    tk = None

GRID_W = 40
GRID_H = 40
CELL_MIN, CELL_MAX, CELL_DEFAULT = 8, 30, 20
MARGIN_L, MARGIN_B, MARGIN_T, MARGIN_R = 45, 35, 30, 25

LINE_COLOR = (0, 0, 255)
BG_COLOR = (255, 255, 255)


def round_half_up(v):
    return int(math.floor(v + 0.5))


def bresenham_line(x0, y0, x1, y1):
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        points.append([x0, y0])
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy

    return points


def bresenham_circle(xc, yc, r):
    points = set()
    r = abs(r)
    x = 0
    y = r
    d = 3 - 2 * r

    def add_symm_points(xc, yc, x, y):
        points.add((xc + x, yc + y))
        points.add((xc - x, yc + y))
        points.add((xc + x, yc - y))
        points.add((xc - x, yc - y))
        points.add((xc + y, yc + x))
        points.add((xc - y, yc + x))
        points.add((xc + y, yc - x))
        points.add((xc - y, yc - x))

    add_symm_points(xc, yc, x, y)

    while x < y:
        if d > 0:
            d = d + 4 * (x - y) + 10
            y -= 1
        else:
            d = d + 4 * x + 6
        x += 1
        add_symm_points(xc, yc, x, y)

    return list(points)


def step_by_step_line(x0, y0, x1, y1):
    points = []

    if x0 == x1:
        step = 1 if y1 >= y0 else -1
        for y in range(y0, y1 + step, step):
            points.append([x0, y])
        return points

    dx = x1 - x0
    dy = y1 - y0
    if abs(dy) > abs(dx):
        k = dx / dy
        step = 1 if y1 >= y0 else -1
        for y in range(y0, y1 + step, step):
            x = round_half_up(x0 + k * (y - y0))
            points.append([x, y])
    else:
        k = dy / dx
        step = 1 if x1 >= x0 else -1
        for x in range(x0, x1 + step, step):
            y = round_half_up(y0 + k * (x - x0))
            points.append([x, y])

    return points


def dda_line(x0, y0, x1, y1):
    points = []

    dx = x1 - x0
    dy = y1 - y0

    steps = max(abs(dx), abs(dy))
    if steps == 0:
        return [[x0, y0]]

    x_increment = dx / steps
    y_increment = dy / steps
    x = x0
    y = y0

    for step in range(steps + 1):
        points.append([round_half_up(x), round_half_up(y)])
        x += x_increment
        y += y_increment

    return points


def castle_pitteway(x0, y0, x1, y1):
    points = []
    dx = x1 - x0
    dy = y1 - y0
    flip_x = False
    flip_y = False
    swap_xy = False

    if dx < 0:
        dx = -dx
        flip_x = True
    if dy < 0:
        dy = -dy
        flip_y = True
    if dy > dx:
        dx, dy = dy, dx
        swap_xy = True

    if dx == 0 and dy == 0:
        return [[x0, y0]]

    if dy == 0:
        code = "S" * dx
    elif dx == dy:
        code = "D" * dy
    else:
        m1 = "S"
        m2 = "D"
        x = dx - dy
        y = dy

        while x != y:
            if x > y:
                m2 = m1 + m2[::-1]
                x = x - y
            else:
                m1 = m2 + m1[::-1]
                y = y - x
        code = m1 + m2[::-1]
        repeats = dx // len(code)
        code = code * repeats

    cx, cy = 0, 0
    points.append([cx, cy])
    for step in code:
        if step == 'S':
            cx += 1
        elif step == 'D':
            cx += 1
            cy += 1
        points.append([cx, cy])

    final_points = []
    for px, py in points:
        if swap_xy:
            px, py = py, px
        if flip_x:
            px = -px
        if flip_y:
            py = -py

        final_points.append([px + x0, py + y0])

    return final_points


def wu_line(x0, y0, x1, y1, w=GRID_W, h=GRID_H):
    points = []

    def fpart(v): return v - math.floor(v)
    def rfpart(v): return 1 - fpart(v)

    def plot(x, y, c):
        x, y = int(x), int(y)
        if c > 0 and 0 <= x < w and 0 <= y < h:
            points.append([x, y, c])

    if x0 == x1 and y0 == y1:
        plot(x0, y0, 1.0)
        return points

    steep = abs(y1 - y0) > abs(x1 - x0)

    if steep:
        x0, y0 = y0, x0
        x1, y1 = y1, x1

    if x0 > x1:
        x0, x1 = x1, x0
        y0, y1 = y1, y0

    dx = x1 - x0
    dy = y1 - y0
    gradient = dy / dx

    xpxl1 = round_half_up(x0)
    yend = y0 + gradient * (xpxl1 - x0)
    ypxl1 = math.floor(yend)
    if steep:
        plot(ypxl1, xpxl1, rfpart(yend))
        plot(ypxl1 + 1, xpxl1, fpart(yend))
    else:
        plot(xpxl1, ypxl1, rfpart(yend))
        plot(xpxl1, ypxl1 + 1, fpart(yend))

    intery = yend + gradient

    xpxl2 = round_half_up(x1)
    yend = y1 + gradient * (xpxl2 - x1)
    ypxl2 = math.floor(yend)
    if steep:
        plot(ypxl2, xpxl2, rfpart(yend))
        plot(ypxl2 + 1, xpxl2, fpart(yend))
    else:
        plot(xpxl2, ypxl2, rfpart(yend))
        plot(xpxl2, ypxl2 + 1, fpart(yend))

    for x in range(xpxl1 + 1, xpxl2):
        iy = math.floor(intery)
        if steep:
            plot(iy, x, rfpart(intery))
            plot(iy + 1, x, fpart(intery))
        else:
            plot(x, iy, rfpart(intery))
            plot(x, iy + 1, fpart(intery))
        intery += gradient

    return points


def cross(u, v):
    return u[0] * v[1] - u[1] * v[0]


def in_arc(u, v, p):
    c = cross(u, v)
    if c == 0 and u[0] * v[0] + u[1] * v[1] > 0:
        return True
    if c >= 0:
        return cross(u, p) >= 0 and cross(p, v) >= 0
    return not (cross(v, p) > 0 and cross(p, u) > 0)


def pitteway_ellipse(xc, yc, a, b):
    a2, b2 = a * a, b * b
    pts = set()

    def add4(x, y):
        pts.update({(xc + x, yc + y), (xc - x, yc + y),
                    (xc + x, yc - y), (xc - x, yc - y)})

    x, y = 0, b
    dx, dy = 0, 2 * a2 * b
    d = 4 * b2 - 4 * a2 * b + a2
    while a2 * (2 * y - 1) > 2 * b2 * (x + 1):
        add4(x, y)
        x += 1
        dx += 2 * b2
        if d < 0:
            d += 4 * (dx + b2)
        else:
            y -= 1
            dy -= 2 * a2
            d += 4 * (dx - dy + b2)
    d = b2 * (2 * x + 1) ** 2 + 4 * a2 * (y - 1) ** 2 - 4 * a2 * b2   # 4 * d2
    x_end = -1
    while y >= 0:
        add4(x, y)
        if y == 0:
            x_end = x
        y -= 1
        dy -= 2 * a2
        if d > 0:
            d += 4 * (a2 - dy)
        else:
            x += 1
            dx += 2 * b2
            d += 4 * (dx - dy + a2)
    for xx in range(x_end + 1, a + 1):
        add4(xx, 0)
    return list(pts)


def intensity_to_hex(intensity):
    intensity = max(0.0, min(1.0, intensity))
    r = int(BG_COLOR[0] + (LINE_COLOR[0] - BG_COLOR[0]) * intensity)
    g = int(BG_COLOR[1] + (LINE_COLOR[1] - BG_COLOR[1]) * intensity)
    b = int(BG_COLOR[2] + (LINE_COLOR[2] - BG_COLOR[2]) * intensity)
    return f"#{r:02x}{g:02x}{b:02x}"


class VirtualGrid:

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.cells = [[0.0] * w for _ in range(h)]

    def clear(self):
        for row in self.cells:
            for x in range(self.w):
                row[x] = 0.0

    def set_pixel(self, x, y, intensity=1.0):
        if 0 <= x < self.w and 0 <= y < self.h and intensity > self.cells[y][x]:
            self.cells[y][x] = intensity

    def get(self, x, y):
        return self.cells[y][x]

    def filled(self):
        for y in range(self.h):
            row = self.cells[y]
            for x in range(self.w):
                if row[x] > 0:
                    yield x, y, row[x]


def rasterize(mode, start, end, grid, arc=None):
    x0, y0 = start
    x1, y1 = end
    if mode == "wu_line":
        for x, y, c in wu_line(x0, y0, x1, y1, grid.w, grid.h):
            grid.set_pixel(x, y, c)
        return
    if mode == "bresenham_line":
        points = bresenham_line(x0, y0, x1, y1)
    elif mode == "dda_line":
        points = dda_line(x0, y0, x1, y1)
    elif mode == "step_by_step_line":
        points = step_by_step_line(x0, y0, x1, y1)
    elif mode == "castle_pitteway":
        points = castle_pitteway(x0, y0, x1, y1)
    elif mode == "pitteway_ellipse":
        a, b = abs(x1 - x0), abs(y1 - y0)
        if a == 0 or b == 0:
            points = bresenham_line(x0 - a, y0 - b, x0 + a, y0 + b)
        else:
            points = pitteway_ellipse(x0, y0, a, b)
        if arc:
            u = (arc[0] - x0, arc[1] - y0)
            v = (arc[2] - x0, arc[3] - y0)
            points = [p for p in points if in_arc(u, v, (p[0] - x0, p[1] - y0))]
    else:
        points = bresenham_circle(x0, y0, int(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5))
    for p in points:
        grid.set_pixel(p[0], p[1], 1.0)


def _table(headers, rows):
    rows = [[str(c) for c in r] for r in rows]
    widths = [max(len(str(h)), *(len(r[i]) for r in rows)) if rows else len(str(h))
              for i, h in enumerate(headers)]
    def line(cells):
        return " | ".join(c.rjust(w) for c, w in zip(cells, widths))
    return [line([str(h) for h in headers]), "-+-".join("-" * w for w in widths)] + [line(r) for r in rows]


def trace_step_by_step(x0, y0, x1, y1):
    out = [f"Пошаговый алгоритм: ({x0},{y0}) -> ({x1},{y1})"]
    dx, dy = x1 - x0, y1 - y0
    out.append(f"dx = {dx}, dy = {dy}")
    if x0 == x1:
        out.append("dx = 0: вертикаль, x постоянен, y меняется на 1 за шаг")
        pts = step_by_step_line(x0, y0, x1, y1)
        return out + ["Точки: " + " ".join(f"({p[0]},{p[1]})" for p in pts)], [tuple(p) for p in pts]
    if abs(dy) > abs(dx):
        k, a0, a1, b0, mj, mn = dx / dy, y0, y1, x0, "y", "x"
    else:
        k, a0, a1, b0, mj, mn = dy / dx, x0, x1, y0, "x", "y"
    out.append(f"|d{mn}| {'>' if mj == 'y' else '<='} |d{mj}|, ведущая ось {mj}; "
               f"k = d{mn}/d{mj} = {k:.6f}")
    step = 1 if a1 >= a0 else -1
    rows, pts = [], []
    for i, a in enumerate(range(a0, a1 + step, step)):
        exact = b0 + k * (a - a0)
        b = round_half_up(exact)
        p = (a, b) if mj == "x" else (b, a)
        pts.append(p)
        rows.append([i, a, f"{exact:.4f}", b, f"({p[0]},{p[1]})"])
    out += _table(["i", mj, f"{mn} = {mn}0 + k*({mj}-{mj}0)", f"{mn} = floor(.+0.5)", "пиксель"], rows)
    return out, pts


def trace_dda(x0, y0, x1, y1):
    out = [f"ЦДА: ({x0},{y0}) -> ({x1},{y1})"]
    dx, dy = x1 - x0, y1 - y0
    steps = max(abs(dx), abs(dy))
    out.append(f"dx = {dx}, dy = {dy}, steps = max(|dx|,|dy|) = {steps}")
    if steps == 0:
        return out + ["Точка: одна клетка"], [(x0, y0)]
    xi, yi = dx / steps, dy / steps
    out.append(f"x_inc = dx/steps = {xi:.6f}, y_inc = dy/steps = {yi:.6f}")
    x, y = x0, y0
    rows, pts = [], []
    for i in range(steps + 1):
        px, py = round_half_up(x), round_half_up(y)
        pts.append((px, py))
        rows.append([i, f"{x:.4f}", f"{y:.4f}", f"({px},{py})"])
        x += xi
        y += yi
    return out + _table(["i", "x", "y", "пиксель = (floor(x+0.5), floor(y+0.5))"], rows), pts


def trace_bresenham_line(x0, y0, x1, y1):
    out = [f"Брезенхем (линия): ({x0},{y0}) -> ({x1},{y1})"]
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    out.append(f"dx = |x1-x0| = {dx}, dy = |y1-y0| = {dy}, sx = {sx}, sy = {sy}, err0 = dx - dy = {err}")
    out.append("Шаг: e2 = 2*err; если e2 > -dy: err -= dy, x += sx; если e2 < dx: err += dx, y += sy")
    x, y = x0, y0
    rows, pts = [], []
    i = 0
    while True:
        pts.append((x, y))
        e2 = 2 * err
        if x == x1 and y == y1:
            rows.append([i, x, y, err, e2, "-", "-", "конец"])
            break
        c1, c2 = e2 > -dy, e2 < dx
        cur = (x, y, err)
        nxt = []
        if c1:
            err -= dy
            x += sx
            nxt.append(f"x{sx:+d}")
        if c2:
            err += dx
            y += sy
            nxt.append(f"y{sy:+d}")
        rows.append([i, cur[0], cur[1], cur[2], e2,
                     f"{e2} > {-dy}: {'да' if c1 else 'нет'}",
                     f"{e2} < {dx}: {'да' if c2 else 'нет'}", ", ".join(nxt)])
        i += 1
    return out + _table(["i", "x", "y", "err", "e2", "e2 > -dy", "e2 < dx", "сдвиг"], rows), pts


def trace_bresenham_circle(xc, yc, r):
    r = abs(r)
    out = [f"Брезенхем (окружность): центр ({xc},{yc}), r = {r}"]
    x, y = 0, r
    d = 3 - 2 * r
    out.append(f"Старт: (x, y) = (0, r) = (0,{r}), d0 = 3 - 2r = {d}")
    out.append("Если d > 0: d += 4(x-y)+10, y -= 1; иначе d += 4x+6; затем x += 1. "
               "Каждая точка (x,y) даёт 8 симметричных: (xc±x, yc±y), (xc±y, yc±x)")
    rows, pts = [], set()

    def add(x, y):
        pts.update({(xc + x, yc + y), (xc - x, yc + y), (xc + x, yc - y), (xc - x, yc - y),
                    (xc + y, yc + x), (xc - y, yc + x), (xc + y, yc - x), (xc - y, yc - x)})

    add(x, y)
    i = 0
    while x < y:
        if d > 0:
            nd, ny, br = d + 4 * (x - y) + 10, y - 1, f"d > 0: y -> {y - 1}, d + 4({x}-{y}) + 10"
        else:
            nd, ny, br = d + 4 * x + 6, y, f"d <= 0: d + 4*{x} + 6"
        rows.append([i, x, y, d, br, nd])
        d, y, x = nd, ny, x + 1
        add(x, y)
        i += 1
    rows.append([i, x, y, d, "x >= y: конец (1-й октант готов)", "-"])
    return out + _table(["i", "x", "y", "d", "ветвь", "новое d"], rows), sorted(pts)


def trace_castle_pitteway(x0, y0, x1, y1):
    out = [f"Кастл-Питвей (линия): ({x0},{y0}) -> ({x1},{y1})"]
    dx, dy = x1 - x0, y1 - y0
    flip_x = flip_y = swap_xy = False
    if dx < 0:
        dx, flip_x = -dx, True
    if dy < 0:
        dy, flip_y = -dy, True
    if dy > dx:
        dx, dy, swap_xy = dy, dx, True
    out.append(f"Приведение к 1-му октанту: dx = {dx}, dy = {dy} (отражение по x: {flip_x}, "
               f"по y: {flip_y}, обмен осей: {swap_xy})")
    if dx == 0 and dy == 0:
        return out + ["Точка"], [(x0, y0)]
    if dy == 0:
        code = "S" * dx
        out.append(f"dy = 0: код = S*{dx}")
    elif dx == dy:
        code = "D" * dy
        out.append(f"dx = dy: код = D*{dy}")
    else:
        m1, m2 = "S", "D"
        x, y = dx - dy, dy
        out.append("S = шаг по x, D = диагональный шаг. Алгоритм Евклида над парой (x, y) = (dx-dy, dy):")
        rows = [["-", x, y, m1, m2, "старт: m1 = S, m2 = D"]]
        i = 1
        while x != y:
            if x > y:
                m2 = m1 + m2[::-1]
                x -= y
                act = "x > y: m2 = m1 + reverse(m2), x -= y"
            else:
                m1 = m2 + m1[::-1]
                y -= x
                act = "x < y: m1 = m2 + reverse(m1), y -= x"
            rows.append([i, x, y, m1, m2, act])
            i += 1
        out += _table(["i", "x", "y", "m1", "m2", "действие"], rows)
        code = m1 + m2[::-1]
        repeats = dx // len(code)
        out.append(f"Базовый период = m1 + reverse(m2) = {code} (длина {len(code)}), "
                   f"повторов dx // длина = {repeats}")
        code = code * repeats
    out.append(f"Полный код ({len(code)} шагов): {code}")
    cx = cy = 0
    path = [(0, 0)]
    for s in code:
        cx += 1
        if s == "D":
            cy += 1
        path.append((cx, cy))
    pts = []
    for px, py in path:
        if swap_xy:
            px, py = py, px
        if flip_x:
            px = -px
        if flip_y:
            py = -py
        pts.append((px + x0, py + y0))
    out.append("Точки: " + " ".join(f"({p[0]},{p[1]})" for p in pts))
    return out, pts


def trace_wu(x0, y0, x1, y1, w=GRID_W, h=GRID_H):
    out = [f"Алгоритм Ву: ({x0},{y0}) -> ({x1},{y1})"]
    if x0 == x1 and y0 == y1:
        return out + ["Точка: одна клетка с интенсивностью 1"], [(x0, y0, 1.0)]
    steep = abs(y1 - y0) > abs(x1 - x0)
    if steep:
        x0, y0, x1, y1 = y0, x0, y1, x1
    if x0 > x1:
        x0, x1, y0, y1 = x1, x0, y1, y0
    gradient = (y1 - y0) / (x1 - x0)
    out.append(f"steep = {steep} ({'оси x и y поменяны местами' if steep else 'ведущая ось x'}); "
               f"после упорядочивания ({x0},{y0}) -> ({x1},{y1}), gradient = dy/dx = {gradient:.6f}")
    out.append("В каждом столбце точная координата линии y делит яркость между двумя пикселями: "
               "верхний получает 1 - frac(y), нижний frac(y); frac(y) = y - floor(y)")
    rows, pts = [], []

    def real(a, b):
        return (b, a) if steep else (a, b)

    def emit(label, a, yv):
        fl = math.floor(yv)
        fr = yv - fl
        p1, p2 = real(a, fl), real(a, fl + 1)
        rows.append([label, a, f"{yv:.4f}", fl, f"{1 - fr:.4f}", f"{fr:.4f}", f"{p1} / {p2}"])
        for p, c in ((p1, 1 - fr), (p2, fr)):
            if c > 0 and 0 <= p[0] < w and 0 <= p[1] < h:
                pts.append((p[0], p[1], c))

    xpxl1 = round_half_up(x0)
    yend = y0 + gradient * (xpxl1 - x0)
    emit("нач.", xpxl1, yend)
    intery = yend + gradient
    xpxl2 = round_half_up(x1)
    yend2 = y1 + gradient * (xpxl2 - x1)
    for x in range(xpxl1 + 1, xpxl2):
        emit(str(x - xpxl1), x, intery)
        intery += gradient
    emit("кон.", xpxl2, yend2)
    out += _table(["i", "x'", "y точное", "floor(y)", "I верх", "I низ", "пиксели (верх / низ)"], rows)
    return out, pts


def trace_ellipse(xc, yc, a, b):
    a2, b2 = a * a, b * b
    out = [f"Эллипс Питвея: центр ({xc},{yc}), a = {a}, b = {b}"]
    pts = set()

    def add4(x, y):
        pts.update({(xc + x, yc + y), (xc - x, yc + y), (xc + x, yc - y), (xc - x, yc - y)})

    x, y = 0, b
    dx, dy = 0, 2 * a2 * b
    d = 4 * b2 - 4 * a2 * b + a2
    out.append(f"a² = {a2}, b² = {b2}; область 1 (ведущая ось X, пока a²(y-1/2) > b²(x+1)): "
               f"4*d1_0 = 4b² - 4a²b + a² = {d}")
    rows = []
    while a2 * (2 * y - 1) > 2 * b2 * (x + 1):
        add4(x, y)
        ndx = dx + 2 * b2
        if d < 0:
            nd, ny, ndy, br = d + 4 * (ndx + b2), y, dy, "d < 0: y не меняется"
        else:
            ndy = dy - 2 * a2
            nd, ny, br = d + 4 * (ndx - ndy + b2), y - 1, "d >= 0: y -> y-1"
        rows.append([1, x, y, d, br, nd])
        x, y, dx, dy, d = x + 1, ny, ndx, ndy, nd
    d = b2 * (2 * x + 1) ** 2 + 4 * a2 * (y - 1) ** 2 - 4 * a2 * b2
    out.append(f"Переход во 2-ю область в ({x},{y}): 4*d2_0 = {d}")
    x_end = -1
    while y >= 0:
        add4(x, y)
        if y == 0:
            x_end = x
        ndy = dy - 2 * a2
        if d > 0:
            nd, nx, ndx, br = d + 4 * (a2 - ndy), x, dx, "d > 0: x не меняется"
        else:
            ndx = dx + 2 * b2
            nd, nx, br = d + 4 * (ndx - ndy + a2), x + 1, "d <= 0: x -> x+1"
        rows.append([2, x, y, d, br, nd])
        x, y, dx, dy, d = nx, y - 1, ndx, ndy, nd
    if x_end < a:
        out_tail = f"Очень плоский эллипс: строка y = 0 дорисована от x = {x_end + 1} до x = {a}"
        for xx in range(x_end + 1, a + 1):
            add4(xx, 0)
    else:
        out_tail = None
    res = out + _table(["обл.", "x", "y", "4*d", "ветвь", "новое 4*d"], rows)
    return (res + [out_tail] if out_tail else res), sorted(pts)


TRACE_MODES = ("step_by_step_line", "dda_line", "bresenham_line", "bresenham_circle",
               "castle_pitteway", "wu_line", "pitteway_ellipse")


def make_trace(mode, start, end):
    x0, y0 = start
    x1, y1 = end
    if mode == "step_by_step_line":
        lines, pts = trace_step_by_step(x0, y0, x1, y1)
    elif mode == "dda_line":
        lines, pts = trace_dda(x0, y0, x1, y1)
    elif mode == "bresenham_line":
        lines, pts = trace_bresenham_line(x0, y0, x1, y1)
    elif mode == "castle_pitteway":
        lines, pts = trace_castle_pitteway(x0, y0, x1, y1)
    elif mode == "wu_line":
        lines, pts = trace_wu(x0, y0, x1, y1)
    elif mode == "pitteway_ellipse":
        a, b = abs(x1 - x0), abs(y1 - y0)
        if a == 0 or b == 0:
            return "Для эллипса обе полуоси должны быть > 0.", []
        lines, pts = trace_ellipse(x0, y0, a, b)
    else:
        lines, pts = trace_bresenham_circle(x0, y0, int(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5))
    return "\n".join(lines), pts


BENCH_SIZE = 1024


def octant(dx, dy):
    return (4 if dx < 0 else 0) + (2 if dy < 0 else 0) + (1 if abs(dy) > abs(dx) else 0)


def gen_segments(n, size, lmin, lmax, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        length = rng.randint(lmin, lmax)
        ang = rng.uniform(0.0, 2.0 * math.pi)
        dx = round_half_up(length * math.cos(ang))
        dy = round_half_up(length * math.sin(ang))
        x0 = rng.randint(max(0, -dx), min(size - 1, size - 1 - dx))
        y0 = rng.randint(max(0, -dy), min(size - 1, size - 1 - dy))
        out.append((x0, y0, x0 + dx, y0 + dy))
    return out


def gen_circles(n, size, rmin, rmax, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        r = rng.randint(rmin, rmax)
        out.append((rng.randint(r, size - 1 - r), rng.randint(r, size - 1 - r), r))
    return out


def _line_algos(size):
    return [
        ("Step by step", step_by_step_line, False),
        ("DDA", dda_line, False),
        ("Bresenham", bresenham_line, False),
        ("Castle-Pitteway", castle_pitteway, False),
        ("Wu", lambda x0, y0, x1, y1: wu_line(x0, y0, x1, y1, size, size), True),
    ]


def _circle_algos():
    return [
        ("Bresenham (circle)", bresenham_circle, False),
        ("Pitteway ellipse a=b", lambda xc, yc, r: pitteway_ellipse(xc, yc, r, r), False),
    ]


def timed_pass(func, items, size, is_wu, checkpoints):
    grid = bytearray(size * size)
    perf = time.perf_counter
    algo = fill = 0.0
    cps = []
    mi = 0
    gc.collect()
    gc.disable()
    try:
        for i, item in enumerate(items, 1):
            t0 = perf()
            pts = func(*item)
            t1 = perf()
            if is_wu:
                for x, y, c in pts:
                    grid[y * size + x] = int(c * 255)
            else:
                for p in pts:
                    grid[p[1] * size + p[0]] = 255
            t2 = perf()
            algo += t1 - t0
            fill += t2 - t1
            if mi < len(checkpoints) and i == checkpoints[mi]:
                cps.append(algo + fill)
                mi += 1
    finally:
        gc.enable()
    return algo, fill, cps


def _mean(xs):
    return sum(xs) / len(xs)


def _repeat(func, items, size, is_wu, checkpoints, repeats):
    runs = [timed_pass(func, items, size, is_wu, checkpoints) for _ in range(repeats)]
    return (_mean([r[0] for r in runs]), _mean([r[1] for r in runs]),
            [_mean(col) for col in zip(*[r[2] for r in runs])])


def run_benchmark(n_lines, n_circles, repeats, size=BENCH_SIZE, progress=None):
    say = progress or (lambda msg: None)
    lengths = [10, 25, 50, 100, 200, 400]
    radii = [10, 25, 50, 100, 200, 400]
    lines = _line_algos(size)
    circles = _circle_algos()
    n_len = max(200, n_lines // 20)
    n_rad = max(100, n_circles // 20)
    res = {"n_lines": n_lines, "n_circles": n_circles, "repeats": repeats, "size": size,
           "lengths": lengths, "radii": radii, "n_len": n_len, "n_rad": n_rad,
           "lines_count": {}, "lines_length": {}, "circles_count": {}, "circles_radius": {}}

    say("Прогрев...")
    warm_l = gen_segments(300, size, 10, 100, 0)
    warm_c = gen_circles(100, size, 1, 50, 0)
    for _, f, w in lines:
        timed_pass(f, warm_l, size, w, [])
    for _, f, w in circles:
        timed_pass(f, warm_c, size, w, [])

    segs = gen_segments(n_lines, size, 10, 300, 1)
    hist = [0] * 8
    for x0, y0, x1, y1 in segs:
        hist[octant(x1 - x0, y1 - y0)] += 1
    res["octants"] = hist
    cps = [n_lines * k // 10 for k in range(1, 11)]
    for name, f, w in lines:
        say(f"{n_lines} отрезков: {name}")
        a, fl, c = _repeat(f, segs, size, w, cps, repeats)
        res["lines_count"][name] = {"x": cps, "total": c, "algo": a, "fill": fl}
    for L in lengths:
        segs_l = gen_segments(n_len, size, L, L, 2)
        for name, f, w in lines:
            say(f"Отрезки длины {L}: {name}")
            a, fl, _ = _repeat(f, segs_l, size, w, [], repeats)
            res["lines_length"].setdefault(name, []).append(a + fl)

    circ = gen_circles(n_circles, size, 1, 200, 3)
    cps = [n_circles * k // 10 for k in range(1, 11)]
    for name, f, w in circles:
        say(f"{n_circles} окружностей: {name}")
        a, fl, c = _repeat(f, circ, size, w, cps, repeats)
        res["circles_count"][name] = {"x": cps, "total": c, "algo": a, "fill": fl}
    for r in radii:
        circ_r = gen_circles(n_rad, size, r, r, 4)
        for name, f, w in circles:
            say(f"Окружности радиуса {r}: {name}")
            a, fl, _ = _repeat(f, circ_r, size, w, [], repeats)
            res["circles_radius"].setdefault(name, []).append(a + fl)
    say("Готово")
    return res


def format_report(res):
    out = [f"Виртуальный растр {res['size']}x{res['size']}, повторов на точку: {res['repeats']}",
           "Отрезков по октантам (индекс = 4*[dx<0] + 2*[dy<0] + [|dy|>|dx|]): "
           + ", ".join(str(v) for v in res["octants"]), ""]

    def table(title, data, base):
        out.append(title)
        out.append(f"{'Алгоритм':<24}{'алгоритм, с':>13}{'запись, с':>12}{'итого, с':>11}{'к ' + base.split()[0]:>14}")
        ref = None
        if base in data:
            ref = data[base]["algo"] + data[base]["fill"]
        for name, d in data.items():
            tot = d["algo"] + d["fill"]
            rel = f"{tot / ref:.2f}x" if ref else "-"
            out.append(f"{name:<24}{d['algo']:>13.3f}{d['fill']:>12.3f}{tot:>11.3f}{rel:>14}")
        out.append("")

    table(f"{res['n_lines']} отрезков, длина 10..300:", res["lines_count"], "Bresenham")
    table(f"{res['n_circles']} окружностей, радиус 1..200:", res["circles_count"], "Bresenham (circle)")
    out.append(f"Время от длины ({res['n_len']} отрезков каждой длины), с:")
    out.append(f"{'длина':<24}" + "".join(f"{L:>9}" for L in res["lengths"]))
    for name, ts in res["lines_length"].items():
        out.append(f"{name:<24}" + "".join(f"{t:>9.3f}" for t in ts))
    out.append("")
    out.append(f"Время от радиуса ({res['n_rad']} окружностей каждого радиуса), с:")
    out.append(f"{'радиус':<24}" + "".join(f"{r:>9}" for r in res["radii"]))
    for name, ts in res["circles_radius"].items():
        out.append(f"{name:<24}" + "".join(f"{t:>9.3f}" for t in ts))
    return "\n".join(out)


def make_figure(res, figsize=(14, 7.5)):
    from matplotlib.figure import Figure
    fig = Figure(figsize=figsize)
    ax = fig.subplots(2, 3)

    def curves(a, data, title, xlabel):
        for name, d in data.items():
            a.plot(d["x"], d["total"], marker="o", markersize=3, label=name)
        a.set_title(title)
        a.set_xlabel(xlabel)
        a.set_ylabel("Время, с")
        a.grid(True, alpha=0.3)
        a.legend(fontsize=8)

    def vs_size(a, xs, data, title, xlabel):
        for name, ts in data.items():
            a.plot(xs, ts, marker="o", markersize=3, label=name)
        a.set_title(title)
        a.set_xlabel(xlabel)
        a.set_ylabel("Время, с")
        a.grid(True, alpha=0.3)
        a.legend(fontsize=8)

    def stacked(a, data, title):
        names = list(data)
        algo = [data[n]["algo"] for n in names]
        fill = [data[n]["fill"] for n in names]
        a.bar(range(len(names)), algo, label="Алгоритм")
        a.bar(range(len(names)), fill, bottom=algo, label="Запись в растр")
        a.set_xticks(range(len(names)))
        a.set_xticklabels(names, rotation=20, ha="right", fontsize=8)
        a.set_title(title)
        a.set_ylabel("Время, с")
        a.legend(fontsize=8)

    curves(ax[0][0], res["lines_count"], "Отрезки: время от количества", "Количество отрезков")
    vs_size(ax[0][1], res["lengths"], res["lines_length"],
            f"Отрезки: время от длины ({res['n_len']} шт.)", "Длина отрезка, пикс.")
    stacked(ax[0][2], res["lines_count"], f"Отрезки ({res['n_lines']} шт.): состав времени")
    curves(ax[1][0], res["circles_count"], "Окружности: время от количества", "Количество окружностей")
    vs_size(ax[1][1], res["radii"], res["circles_radius"],
            f"Окружности: время от радиуса ({res['n_rad']} шт.)", "Радиус, пикс.")
    stacked(ax[1][2], res["circles_count"], f"Окружности ({res['n_circles']} шт.): состав времени")
    fig.tight_layout()
    return fig


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Demonstration")
        self.start_pt = None
        self.end_pt = None
        self.cell = CELL_DEFAULT
        self.grid = VirtualGrid(GRID_W, GRID_H)
        self.show_vals = tk.BooleanVar(value=True)
        self.show_hint = tk.BooleanVar(value=False)
        self.algo_var = tk.StringVar(value="bresenham_line")

        control_frame = tk.Frame(root, pady=5)
        control_frame.pack()

        algorithms = [
            ("Bresenham (line)", "bresenham_line"),
            ("DDA", "dda_line"),
            ("Step by Step", "step_by_step_line"),
            ("Bresenham (circle)", "bresenham_circle"),
            ("Castle-pitteway", "castle_pitteway"),
            ("Wu", "wu_line"),
            ("Castle-pitteway (ellipse/arc)", "pitteway_ellipse"),
        ]
        for text, algorithm in algorithms:
            tk.Radiobutton(control_frame, text=text, variable=self.algo_var,
                           value=algorithm, command=self.redraw).pack(side=tk.LEFT, padx=5)

        tk.Button(control_frame, text="Clear",
                  command=self.clear).pack(side=tk.LEFT, padx=10)

        zoom_frame = tk.Frame(root)
        zoom_frame.pack()
        tk.Label(zoom_frame, text="Масштаб (размер клетки, px):").pack(side=tk.LEFT)
        self.zoom = tk.Scale(zoom_frame, from_=CELL_MIN, to=CELL_MAX, orient=tk.HORIZONTAL,
                             length=250, command=self.on_zoom)
        self.zoom.set(CELL_DEFAULT)
        self.zoom.pack(side=tk.LEFT)

        coord_frame = tk.Frame(root)
        coord_frame.pack(pady=3)
        self.entries = {}
        for key in ("x0", "y0", "x1", "y1"):
            tk.Label(coord_frame, text=key + ":").pack(side=tk.LEFT)
            e = tk.Entry(coord_frame, width=4)
            e.pack(side=tk.LEFT, padx=(0, 8))
            e.bind("<Return>", lambda ev: self.apply_coords())
            self.entries[key] = e
        tk.Button(coord_frame, text="Построить",
                  command=self.apply_coords).pack(side=tk.LEFT)

        arc_frame = tk.Frame(root)
        arc_frame.pack(pady=3)
        tk.Label(arc_frame, text="Дуга эллипса (необязательно, против часовой): "
                                 "начало направления").pack(side=tk.LEFT)
        for key, label in (("ax", "x"), ("ay", "y")):
            tk.Label(arc_frame, text=label + ":").pack(side=tk.LEFT)
            e = tk.Entry(arc_frame, width=4)
            e.pack(side=tk.LEFT, padx=(0, 6))
            e.bind("<Return>", lambda ev: self.apply_coords())
            self.entries[key] = e
        tk.Label(arc_frame, text="  конец направления").pack(side=tk.LEFT)
        for key, label in (("bx", "x"), ("by", "y")):
            tk.Label(arc_frame, text=label + ":").pack(side=tk.LEFT)
            e = tk.Entry(arc_frame, width=4)
            e.pack(side=tk.LEFT, padx=(0, 6))
            e.bind("<Return>", lambda ev: self.apply_coords())
            self.entries[key] = e

        opt_frame = tk.Frame(root)
        opt_frame.pack(pady=3)
        tk.Button(opt_frame, text="Вычисления (шаги алгоритма)",
                  command=self.show_trace).pack(side=tk.LEFT, padx=5)
        tk.Checkbutton(opt_frame, text="Числа интенсивности (Ву)", variable=self.show_vals,
                       command=self.redraw).pack(side=tk.LEFT, padx=5)
        tk.Checkbutton(opt_frame, text="Идеальная линия (красная подсказка)", variable=self.show_hint,
                       command=self.redraw).pack(side=tk.LEFT, padx=5)

        bench_frame = tk.Frame(root)
        bench_frame.pack(pady=3)
        tk.Button(bench_frame, text="Бенчмарк (быстрый: 10 000 / 5 000)",
                  command=lambda: self.start_benchmark(True)).pack(side=tk.LEFT, padx=5)
        tk.Button(bench_frame, text="Бенчмарк (полный: 100 000 / 50 000)",
                  command=lambda: self.start_benchmark(False)).pack(side=tk.LEFT, padx=5)
        self.bench_thread = None
        self.bench_msg = ""
        self.bench_result = None
        self.bench_error = None
        self.bench_win = None
        self.bench_label = None

        canvas_frame = tk.Frame(root)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.canvas = tk.Canvas(canvas_frame, width=760, height=620, bg="white")
        xbar = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        ybar = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.status = tk.Label(root, text="", anchor="w")
        self.status.pack(fill=tk.X, padx=10)
        self.note = tk.Label(root, text="", anchor="w", justify=tk.LEFT, fg="#0b6b2d", wraplength=900)
        self.note.pack(fill=tk.X, padx=10)
        tk.Label(root, anchor="w", justify=tk.LEFT, fg="#444444",
                 text="Пиксель (x, y) — клетка сетки, подпись оси стоит по центру клетки. "
                      "(0, 0) — левая нижняя клетка, ось Y направлена вверх.\n"
                      "Центр пикселя (x, y) имеет вещественные координаты (x + 0.5, y + 0.5). "
                      "Ctrl + колесо мыши — масштаб.").pack(fill=tk.X, padx=10, pady=(0, 5))

        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Control-MouseWheel>", self.on_wheel)

        self.redraw()

    def px_x(self, gx):
        return MARGIN_L + gx * self.cell

    def px_y(self, gy):
        return MARGIN_T + (GRID_H - gy) * self.cell

    def cell_center(self, gx, gy):
        return self.px_x(gx) + self.cell / 2, self.px_y(gy) - self.cell / 2

    def to_grid(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        gx = int((cx - MARGIN_L) // self.cell)
        gy = GRID_H - 1 - int((cy - MARGIN_T) // self.cell)
        gx = max(0, min(GRID_W - 1, gx))
        gy = max(0, min(GRID_H - 1, gy))
        return gx, gy

    def draw_grid(self):
        top, bottom = self.px_y(GRID_H), self.px_y(0)
        left, right = self.px_x(0), self.px_x(GRID_W)

        for i in range(GRID_W + 1):
            x = self.px_x(i)
            self.canvas.create_line(x, top, x, bottom, fill="#cccccc")
        for j in range(GRID_H + 1):
            y = self.px_y(j)
            self.canvas.create_line(left, y, right, y, fill="#cccccc")

        self.canvas.create_line(left, bottom, right + 12, bottom, width=2, arrow=tk.LAST)
        self.canvas.create_line(left, bottom, left, top - 12, width=2, arrow=tk.LAST)
        self.canvas.create_text(right + 14, bottom + 14, text="X", font=("Arial", 10, "bold"))
        self.canvas.create_text(left - 14, top - 14, text="Y", font=("Arial", 10, "bold"))

        step = max(1, math.ceil(24 / self.cell))
        for i in range(0, GRID_W, step):
            x, _ = self.cell_center(i, 0)
            self.canvas.create_text(x, bottom + 12, text=str(i), font=("Arial", 8))
        for j in range(0, GRID_H, step):
            _, y = self.cell_center(0, j)
            self.canvas.create_text(left - 14, y, text=str(j), font=("Arial", 8))

        self.canvas.configure(scrollregion=(0, 0, right + MARGIN_R, bottom + MARGIN_B))

    def fill_pixel(self, px, py, color="blue"):
        if not (0 <= px < GRID_W and 0 <= py < GRID_H):
            return
        self.canvas.create_rectangle(self.px_x(px), self.px_y(py + 1),
                                     self.px_x(px + 1), self.px_y(py),
                                     fill=color, outline="")

    def on_zoom(self, value):
        self.cell = int(float(value))
        self.redraw()

    def apply_coords(self):
        try:
            x0, y0, x1, y1 = (int(self.entries[k].get()) for k in ("x0", "y0", "x1", "y1"))
        except ValueError:
            self.status.config(text="Введите целые числа во все четыре поля")
            return
        if not (0 <= x0 < GRID_W and 0 <= x1 < GRID_W and 0 <= y0 < GRID_H and 0 <= y1 < GRID_H):
            self.status.config(text=f"Допустимо: x от 0 до {GRID_W - 1}, y от 0 до {GRID_H - 1}")
            return
        _, err = self.read_arc((x0, y0))
        if err:
            self.status.config(text=err)
            return
        self.start_pt = (x0, y0)
        self.end_pt = (x1, y1)
        self.redraw()

    def read_arc(self, center):
        raw = [self.entries[k].get().strip() for k in ("ax", "ay", "bx", "by")]
        if not any(raw):
            return None, None
        try:
            vals = tuple(int(s) for s in raw)
        except ValueError:
            return None, "Дуга: введите четыре целых числа или оставьте все поля пустыми"
        if center is not None and (vals[:2] == tuple(center) or vals[2:] == tuple(center)):
            return None, "Дуга: точки направления не должны совпадать с центром"
        return vals, None

    def sync_entries(self):
        vals = (self.start_pt or ("", "")) + (self.end_pt or ("", ""))
        for key, v in zip(("x0", "y0", "x1", "y1"), vals):
            self.entries[key].delete(0, tk.END)
            self.entries[key].insert(0, str(v))

    def start_benchmark(self, quick):
        if self.bench_thread is not None and self.bench_thread.is_alive():
            return
        args = (10000, 5000, 3) if quick else (100000, 50000, 1)
        self.bench_msg = "Запуск..."
        self.bench_result = None
        self.bench_error = None

        def work():
            try:
                self.bench_result = run_benchmark(*args, progress=self.set_bench_msg)
            except Exception as e:
                self.bench_error = repr(e)

        self.bench_win = tk.Toplevel(self.root)
        self.bench_win.title("Бенчмарк")
        self.bench_label = tk.Label(self.bench_win, text=self.bench_msg, width=60, pady=20)
        self.bench_label.pack()
        self.bench_thread = threading.Thread(target=work, daemon=True)
        self.bench_thread.start()
        self.root.after(300, self.poll_benchmark)

    def set_bench_msg(self, msg):
        self.bench_msg = msg

    def poll_benchmark(self):
        try:
            if self.bench_thread.is_alive():
                self.bench_label.config(text=self.bench_msg)
                self.root.after(300, self.poll_benchmark)
                return
            if self.bench_error:
                self.bench_label.config(text="Ошибка: " + self.bench_error)
                return
            self.show_benchmark(self.bench_result)
        except tk.TclError:
            pass

    def show_benchmark(self, res):
        report = format_report(res)
        with open("benchmark.txt", "w", encoding="utf-8") as f:
            f.write(report)
        self.bench_label.destroy()
        win = self.bench_win
        text = tk.Text(win, height=22, width=110, font=("Courier New", 9))
        text.insert("1.0", report + "\n\nСохранено: benchmark.txt, benchmark.png")
        text.pack(fill=tk.X, padx=5, pady=5)
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            fig = make_figure(res, figsize=(12, 6))
            fig.savefig("benchmark.png", dpi=110)
            canvas = FigureCanvasTkAgg(fig, master=win)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        except ImportError:
            tk.Label(win, text="matplotlib не установлен: графики недоступны").pack()

    def on_wheel(self, event):
        new = self.cell + (1 if event.delta > 0 else -1)
        self.zoom.set(max(CELL_MIN, min(CELL_MAX, new)))

    def on_motion(self, event):
        gx, gy = self.to_grid(event)
        self.status.config(text=f"Курсор: клетка ({gx}, {gy})   "
                                f"Начало: {self.start_pt}   Конец: {self.end_pt}")

    def on_mouse_down(self, event):
        self.start_pt = self.to_grid(event)
        self.end_pt = self.start_pt
        self.redraw()
        self.sync_entries()

    def on_mouse_drag(self, event):
        if self.start_pt:
            self.end_pt = self.to_grid(event)
            self.redraw()
            self.sync_entries()

    def clear(self):
        self.start_pt = None
        self.end_pt = None
        for key in ("ax", "ay", "bx", "by"):
            self.entries[key].delete(0, tk.END)
        self.redraw()
        self.sync_entries()

    NOTES = {
        "bresenham_line": "Брезенхем: только целые числа. Ошибка err накапливается; шаг по ведущей оси "
                          "делается всегда, по другой оси - когда ошибка перевалила порог (e2 > -dy, e2 < dx).",
        "dda_line": "ЦДА: за steps = max(|dx|,|dy|) шагов к вещественным (x, y) прибавляются "
                    "приращения dx/steps и dy/steps, пиксель = округление.",
        "step_by_step_line": "Пошаговый: на каждом шаге по ведущей оси y = y0 + k*(x - x0), "
                             "k = dy/dx, пиксель = округление y.",
        "bresenham_circle": "Окружность Брезенхема: центр - первая точка, радиус - расстояние до второй. "
                            "Считается 1-й октант, остальные 7 получаются симметрией.",
        "castle_pitteway": "Кастл-Питвей: линия кодируется строкой шагов S (по x) и D (по диагонали), "
                           "строка строится алгоритмом Евклида над (dx-dy, dy).",
        "wu_line": "Ву: точная координата линии делит яркость между двумя соседними пикселями "
                   "(1 - frac и frac), поэтому края получаются сглаженными. Цвет клетки = интенсивность.",
        "pitteway_ellipse": "Эллипс Питвея: центр - первая точка, полуоси a, b - из угла описанного "
                            "прямоугольника. Опционально дуга по направлениям из полей ниже.",
    }

    def redraw(self):
        self.canvas.delete("all")
        self.note.config(text=self.NOTES.get(self.algo_var.get(), ""))
        self.grid.clear()
        if self.start_pt and self.end_pt:
            arc, _ = self.read_arc(self.start_pt)
            rasterize(self.algo_var.get(), self.start_pt, self.end_pt, self.grid, arc)
        self.paint_grid()
        self.draw_grid()
        if self.start_pt and self.end_pt and self.show_hint.get():
            self.draw_hint()

    def paint_grid(self):
        wu = self.algo_var.get() == "wu_line"
        for x, y, c in self.grid.filled():
            self.fill_pixel(x, y, intensity_to_hex(c) if wu else "blue")
            if wu and self.show_vals.get() and self.cell >= 20:
                cx, cy = self.cell_center(x, y)
                self.canvas.create_text(cx, cy, text=f"{c:.2f}", font=("Arial", 6),
                                        fill="white" if c > 0.55 else "black")

    def show_trace(self):
        if not (self.start_pt and self.end_pt):
            self.status.config(text="Сначала задайте точки (кликом или полями ввода)")
            return
        text, _ = make_trace(self.algo_var.get(), self.start_pt, self.end_pt)
        win = tk.Toplevel(self.root)
        win.title("Вычисления")
        box = tk.Text(win, width=120, height=40, font=("Courier New", 9), wrap="none")
        sb = tk.Scrollbar(win, command=box.yview)
        box.configure(yscrollcommand=sb.set)
        box.insert("1.0", text)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        box.pack(fill=tk.BOTH, expand=True)

    def draw_hint(self):
        x0, y0 = self.start_pt
        x1, y1 = self.end_pt
        cx0, cy0 = self.cell_center(x0, y0)
        cx1, cy1 = self.cell_center(x1, y1)
        mode = self.algo_var.get()
        if mode == "bresenham_circle":
            r_px = ((cx1 - cx0) ** 2 + (cy1 - cy0) ** 2) ** 0.5
            self.canvas.create_oval(cx0 - r_px, cy0 - r_px, cx0 + r_px, cy0 + r_px,
                                    outline="red", width=1, dash=(4, 4))
        elif mode == "pitteway_ellipse":
            a_px, b_px = abs(x1 - x0) * self.cell, abs(y1 - y0) * self.cell
            self.canvas.create_oval(cx0 - a_px, cy0 - b_px, cx0 + a_px, cy0 + b_px,
                                    outline="red", width=1, dash=(4, 4))
        else:
            self.canvas.create_line(cx0, cy0, cx1, cy1, fill="red", width=1, dash=(4, 4))


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--trace" in argv:
        i = argv.index("--trace")
        mode, x0, y0, x1, y1 = argv[i + 1], *map(int, argv[i + 2:i + 6])
        print(make_trace(mode, (x0, y0), (x1, y1))[0])
    elif "--bench" in argv or "--bench-quick" in argv:
        quick = "--bench-quick" in argv
        n_lines, n_circles, reps = (10000, 5000, 3) if quick else (100000, 50000, 1)
        if "--repeats" in argv:
            reps = int(argv[argv.index("--repeats") + 1])
        res = run_benchmark(n_lines, n_circles, reps, progress=print)
        report = format_report(res)
        print(report)
        with open("benchmark.txt", "w", encoding="utf-8") as f:
            f.write(report)
        make_figure(res).savefig("benchmark.png", dpi=110)
        print("Сохранено: benchmark.txt, benchmark.png")
    elif tk is None:
        print("tkinter не установлен: интерфейс недоступен. Консольные режимы: --bench, --bench-quick, --trace")
    else:
        root = tk.Tk()
        app = App(root)
        root.mainloop()
