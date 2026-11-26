import sys

try:
    import tkinter as tk
except ImportError:
    tk = None

EPS = 1e-7
GRID = 41
ORIGIN = GRID // 2
X_MIN, X_MAX = -ORIGIN, GRID - 1 - ORIGIN
Y_MIN, Y_MAX = X_MIN, X_MAX
CELL_MIN, CELL_MAX, CELL_DEFAULT = 8, 30, 20
MARGIN_L, MARGIN_B, MARGIN_T, MARGIN_R = 45, 35, 30, 25

C_SRC = "#9db4ff"
C_WIN = "#e07000"
C_VIS = "#0000ff"
C_FILL = "#bcd0ff"


def liang_barsky(x1, y1, x2, y2, win, log=None):
    xmin, ymin, xmax, ymax = win
    dx, dy = x2 - x1, y2 - y1
    p = (-dx, dx, -dy, dy)
    q = (x1 - xmin, xmax - x1, y1 - ymin, ymax - y1)
    names = ("левая", "правая", "нижняя", "верхняя")
    u1, u2 = 0.0, 1.0
    for i in range(4):
        pi, qi = p[i], q[i]
        if abs(pi) < EPS:
            if qi < -EPS:
                if log is not None:
                    log.append(f"  {names[i]}: p = 0, q = {qi:.4f} < 0 -> параллельно и снаружи, отброшен")
                return None
            if log is not None:
                log.append(f"  {names[i]}: p = 0, q = {qi:.4f} >= 0 -> параллельно, внутри полосы")
            continue
        r = qi / pi
        kind = "вход" if pi < 0 else "выход"
        if pi < 0:
            u1 = max(u1, r)
        else:
            u2 = min(u2, r)
        if log is not None:
            log.append(f"  {names[i]}: p = {pi:.4f}, q = {qi:.4f}, r = q/p = {r:.4f} ({kind})"
                       f"  -> u1 = {u1:.4f}, u2 = {u2:.4f}")
        if u1 > u2 + EPS:
            if log is not None:
                log.append("  u1 > u2 -> отрезок вне окна")
            return None
    u2 = max(u1, u2)
    return (x1 + u1 * dx, y1 + u1 * dy, x1 + u2 * dx, y1 + u2 * dy)



LEFT, RIGHT, BOTTOM, TOP = 1, 2, 4, 8


def outcode(x, y, win):
    xmin, ymin, xmax, ymax = win
    c = 0
    if x < xmin - EPS:
        c |= LEFT
    elif x > xmax + EPS:
        c |= RIGHT
    if y < ymin - EPS:
        c |= BOTTOM
    elif y > ymax + EPS:
        c |= TOP
    return c


def cohen_sutherland(x1, y1, x2, y2, win, log=None):
    xmin, ymin, xmax, ymax = win
    c1, c2 = outcode(x1, y1, win), outcode(x2, y2, win)
    dx, dy = x2 - x1, y2 - y1
    vertical, horizontal = abs(dx) < EPS, abs(dy) < EPS
    k = None if (vertical or horizontal) else dy / dx
    if log is not None:
        log.append(f"  k = {'-' if k is None else format(k, '.4f')}")
    for it in range(8):
        if log is not None:
            log.append(f"  шаг {it}: код1 = {c1:04b}, код2 = {c2:04b}")
        if not (c1 | c2):
            if log is not None:
                log.append("  оба кода 0000 -> целиком видим")
            return (x1, y1, x2, y2)
        if c1 & c2:
            if log is not None:
                log.append("  код1 & код2 != 0 -> целиком невидим")
            return None
        c = c1 or c2
        if c & TOP:
            y, x, side = ymax, (x1 if vertical else x1 + (ymax - y1) / k), "верх"
        elif c & BOTTOM:
            y, x, side = ymin, (x1 if vertical else x1 + (ymin - y1) / k), "низ"
        elif c & RIGHT:
            x, y, side = xmax, (y1 if horizontal else y1 + k * (xmax - x1)), "право"
        else:
            x, y, side = xmin, (y1 if horizontal else y1 + k * (xmin - x1)), "лево"
        if log is not None:
            log.append(f"    точка {'1' if c == c1 else '2'} -> граница {side}: ({x:.4f}, {y:.4f})")
        if c == c1:
            x1, y1, c1 = x, y, outcode(x, y, win)
        else:
            x2, y2, c2 = x, y, outcode(x, y, win)
    return None


_SNAP = 6


def _snap(p):
    return (round(p[0], _SNAP) + 0.0, round(p[1], _SNAP) + 0.0)


def _cross(ax, ay, bx, by):
    return ax * by - ay * bx


def ring_area(ring):
    s = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def point_in_even_odd(px, py, edges):
    inside = False
    for (x1, y1), (x2, y2) in edges:
        if (y1 > py) != (y2 > py):
            xi = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if xi > px:
                inside = not inside
    return inside


def _params_on_edge(p, q, a, b):
    dx, dy = q[0] - p[0], q[1] - p[1]
    ex, ey = b[0] - a[0], b[1] - a[1]
    L = (dx * dx + dy * dy) ** 0.5
    if L < EPS:
        return []
    te = EPS / L
    den = _cross(dx, dy, ex, ey)
    res = []
    apx, apy = a[0] - p[0], a[1] - p[1]
    if abs(den) <= EPS * L * max((ex * ex + ey * ey) ** 0.5, 1e-12):
        if abs(_cross(apx, apy, dx, dy)) / L <= EPS:
            for r in (a, b):
                t = ((r[0] - p[0]) * dx + (r[1] - p[1]) * dy) / (L * L)
                if te < t < 1 - te:
                    res.append(t)
        return res
    t = _cross(apx, apy, ex, ey) / den
    s = _cross(apx, apy, dx, dy) / den
    Le = (ex * ex + ey * ey) ** 0.5
    se = EPS / Le
    if -se <= s <= 1 + se and te < t < 1 - te:
        res.append(t)
    return res


def _perimeter_t(p, win):
    xmin, ymin, xmax, ymax = win
    w, h = xmax - xmin, ymax - ymin
    x, y = p
    if abs(y - ymin) <= EPS:
        return x - xmin
    if abs(x - xmax) <= EPS:
        return w + (y - ymin)
    if abs(y - ymax) <= EPS:
        return w + h + (xmax - x)
    return 2 * w + h + (ymax - y)


def weiler_atherton(rings, win):
    xmin, ymin, xmax, ymax = win
    w, h = xmax - xmin, ymax - ymin
    P = 2 * (w + h)
    corners = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
    sides = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    orig = []
    for ring in rings:
        n = len(ring)
        for i in range(n):
            p, q = ring[i], ring[(i + 1) % n]
            if abs(p[0] - q[0]) > EPS or abs(p[1] - q[1]) > EPS:
                orig.append((p, q))
    if not orig:
        return []
    ext = max(max(abs(p[0]) for e in orig for p in e),
              max(abs(p[1]) for e in orig for p in e), 1.0)
    off = 1e-6 * ext

    sub = []
    for i, (p, q) in enumerate(orig):
        ts = []
        for a, b in sides:
            ts += _params_on_edge(p, q, a, b)
        for j, (a, b) in enumerate(orig):
            if j != i:
                ts += _params_on_edge(p, q, a, b)
        ts = sorted(set([0.0, 1.0] + ts))
        pts = []
        for t in ts:
            pt = (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))
            x, y = pt
            if abs(x - xmin) <= EPS:
                x = xmin
            elif abs(x - xmax) <= EPS:
                x = xmax
            if abs(y - ymin) <= EPS:
                y = ymin
            elif abs(y - ymax) <= EPS:
                y = ymax
            pts.append(_snap((x, y)))
        for a, b in zip(pts, pts[1:]):
            if abs(a[0] - b[0]) > EPS or abs(a[1] - b[1]) > EPS:
                sub.append((a, b))

    kept = []
    for a, b in sub:
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = (dx * dx + dy * dy) ** 0.5
        nx, ny = -dy / L, dx / L
        inl = point_in_even_odd(mx + off * nx, my + off * ny, orig)
        inr = point_in_even_odd(mx - off * nx, my - off * ny, orig)
        if inl == inr:
            continue
        if inr:
            a, b = b, a
            dx, dy = -dx, -dy
        on_b = None
        if abs(my - ymin) <= EPS and xmin - EPS <= mx <= xmax + EPS:
            on_b = "b"
        elif abs(mx - xmax) <= EPS and ymin - EPS <= my <= ymax + EPS:
            on_b = "r"
        elif abs(my - ymax) <= EPS and xmin - EPS <= mx <= xmax + EPS:
            on_b = "t"
        elif abs(mx - xmin) <= EPS and ymin - EPS <= my <= ymax + EPS:
            on_b = "l"
        if on_b:
            ccw = {"b": dx > 0, "r": dy > 0, "t": dx < 0, "l": dy < 0}[on_b]
            if ccw:
                kept.append((a, b))
        elif (xmin + EPS < mx < xmax - EPS) and (ymin + EPS < my < ymax - EPS):
            kept.append((a, b))

    out_edges = {}
    ends = set()
    for i, (a, b) in enumerate(kept):
        out_edges.setdefault(a, []).append(i)
        ends.add(b)
    used = [False] * len(kept)

    def follow(start_idx):
        path = [kept[start_idx][0]]
        i = start_idx
        while True:
            used[i] = True
            path.append(kept[i][1])
            nxt = [j for j in out_edges.get(kept[i][1], []) if not used[j]]
            if not nxt:
                return path
            i = nxt[0]

    open_paths = []
    for i, (a, b) in enumerate(kept):
        if not used[i] and a not in ends:
            open_paths.append(follow(i))
    closed = []
    for i in range(len(kept)):
        if not used[i]:
            closed.append(follow(i)[:-1])

    result = []
    remaining = list(range(len(open_paths)))
    while remaining:
        first = remaining.pop(0)
        ring = list(open_paths[first])
        cur = first
        while True:
            te = _perimeter_t(open_paths[cur][-1], win)
            best, bd = None, None
            cands = remaining + [first]
            for j in cands:
                ts = _perimeter_t(open_paths[j][0], win)
                d = (ts - te) % P
                if d > P - EPS:
                    d = 0.0
                if bd is None or d < bd - EPS:
                    best, bd = j, d
            cs = []
            for c in corners:
                dc = (_perimeter_t(c, win) - te) % P
                if EPS < dc < bd - EPS:
                    cs.append((dc, c))
            ring += [c for _, c in sorted(cs)]
            if best == first:
                break
            remaining.remove(best)
            ring += open_paths[best]
            cur = best
        result.append(ring)
    result += closed

    if not open_paths and not any(
            any(abs(p[0] - xmin) <= EPS or abs(p[0] - xmax) <= EPS
                or abs(p[1] - ymin) <= EPS or abs(p[1] - ymax) <= EPS for p in r)
            for r in closed):
        if point_in_even_odd(xmin + off, ymin + off, orig):
            result.append(list(corners))

    clean = []
    for r in result:
        r2 = [r[0]]
        for p in r[1:]:
            if abs(p[0] - r2[-1][0]) > EPS or abs(p[1] - r2[-1][1]) > EPS:
                r2.append(p)
        if len(r2) > 1 and abs(r2[0][0] - r2[-1][0]) <= EPS and abs(r2[0][1] - r2[-1][1]) <= EPS:
            r2.pop()
        if len(r2) >= 3 and abs(ring_area(r2)) > EPS:
            clean.append(r2)
    return clean


def poly_area(poly):
    n = len(poly)
    return sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
               for i in range(n)) / 2


def is_convex(poly):
    n = len(poly)
    if n < 3 or abs(poly_area(poly)) < EPS:
        return False
    sign = 0
    for i in range(n):
        a, b, c = poly[i], poly[(i + 1) % n], poly[(i + 2) % n]
        cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cr) < EPS:
            continue
        s = 1 if cr > 0 else -1
        if sign and s != sign:
            return False
        sign = s
    return True


def cyrus_beck(x1, y1, x2, y2, poly, log=None):
    if poly_area(poly) < 0:
        poly = poly[::-1]
    n = len(poly)
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        nx, ny = -(by - ay), bx - ax
        ln = (nx * nx + ny * ny) ** 0.5
        den = nx * dx + ny * dy
        num = nx * (x1 - ax) + ny * (y1 - ay)
        if abs(den) < EPS * ln:
            if num < -EPS * ln:
                if log is not None:
                    log.append(f"  ребро {i}: n·d = 0, n·(P-A) = {num:.4f} < 0 -> параллельно и снаружи")
                return None
            if log is not None:
                log.append(f"  ребро {i}: n·d = 0, внутри полуплоскости")
            continue
        t = -num / den
        kind = "вход" if den > 0 else "выход"
        if den > 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if log is not None:
            log.append(f"  ребро {i}: n·d = {den:.4f}, n·(P-A) = {num:.4f}, t = {t:.4f} ({kind})"
                       f" -> t0 = {t0:.4f}, t1 = {t1:.4f}")
        if t0 > t1 + EPS:
            if log is not None:
                log.append("  t0 > t1 -> отрезок вне многоугольника")
            return None
    t1 = max(t0, t1)
    return (x1 + t0 * dx, y1 + t0 * dy, x1 + t1 * dx, y1 + t1 * dy)


def self_test():
    w = (0, 0, 10, 10)
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    cases = [
        ((1, 1, 9, 9), (1, 1, 9, 9)), ((-5, -5, -1, -1), None), ((-5, 5, 15, 5), (0, 5, 10, 5)),
        ((0, 2, 0, 8), (0, 2, 0, 8)), ((-5, 10, 15, 10), (0, 10, 10, 10)), ((-5, 11, 15, 11), None),
        ((0, 0, 0, 0), (0, 0, 0, 0)), ((10, 10, 10, 10), (10, 10, 10, 10)), ((-1, 1, 1, -1), (0, 0, 0, 0)),
        ((-5, -5, 15, 15), (0, 0, 10, 10)), ((-1, -1, -1, -1), None),
    ]
    for s, exp in cases:
        for f, win in ((liang_barsky, w), (cohen_sutherland, w), (cyrus_beck, sq)):
            r = f(*s, win)
            ok = (r is None and exp is None) or (r and exp and all(abs(a - b) < 1e-6 for a, b in zip(r, exp)))
            assert ok, (f.__name__, s, r, exp)
    # ромб (выпуклый)
    r = cyrus_beck(-5, 0, 5, 0, [(0, -2), (2, 0), (0, 2), (-2, 0)])
    assert r and abs(r[0] + 2) < 1e-6 and abs(r[2] - 2) < 1e-6
    print("Все тесты пройдены")


ALGOS = (("Лианг-Барски", "liang_barsky"),
         ("Коэн-Сазерленд", "cohen_sutherland"),
         ("Сайрус-Бек (выпуклый многоуг.)", "cyrus_beck"),
         ("Уайлер-Атертон (многоугольник)", "weiler_atherton"))
NOTES = {
    "liang_barsky": "Лианг-Барски: P(u) = P1 + u(P2-P1), u в [0,1]. p = (-dx, dx, -dy, dy), q - расстояние от P1 до "
                    "границы, r = q/p. p<0 (вход) поднимает u1, p>0 (выход) опускает u2; u1 > u2 - вне окна; "
                    "p = 0 и q < 0 - параллельный снаружи.",
    "cohen_sutherland": "Коэн-Сазерленд: 4-битные коды концов (лево, право, низ, верх). Оба 0 - принять; "
                        "общий бит - отбросить; иначе конец с ненулевым кодом переносится на границу, "
                        "пересечение - из явного уравнения прямой y = k(x-x1)+y1.",
    "cyrus_beck": "Сайрус-Бек: для каждого ребра выпуклого многоугольника параметр t через скалярное произведение "
                  "с внутренней нормалью: n·d > 0 - вход (t0 = max), n·d < 0 - выход (t1 = min).",
    "weiler_atherton": "Уайлер-Атертон: контур многоугольника разбивается точками пересечения с окном на входы и "
                       "выходы; от выхода обход идёт по границе окна (против часовой) до следующего входа. "
                       "Работает для вогнутых и самопересекающихся многоугольников, результат может распасться на части.",
}


class App:
    def __init__(self, root):
        self.root = root
        root.title("Отсечение - лабораторная 5")
        self.cell = CELL_DEFAULT
        self.segs = [[-8, 2, 14, 9], [1, 1, 3, 3], [0, 5, 0, 12], [-5, -5, 15, 15],
                     [4, 4, 4, 4], [-6, -6, -1, -2], [-3, 8, 12, 8], [0, -3, 0, 3]]
        self.rects = {"seg": [0, 0, 8, 6], "wa": [-8, 3, 11, 7]}
        self.poly = [(2, -3), (9, 0), (7, 7), (-1, 6)]
        self.subj = [(-6, -3), (9, -3), (9, 10), (5, 10), (5, 1), (-2, 1), (-2, 10), (-6, 10)]
        self.algo = tk.StringVar(value="liang_barsky")
        self.drag = None

        top = tk.Frame(root, pady=5)
        top.pack()
        for text, val in ALGOS:
            tk.Radiobutton(top, text=text, variable=self.algo, value=val,
                           command=self.on_algo).pack(side=tk.LEFT, padx=5)
        tk.Button(top, text="Clear", command=self.clear).pack(side=tk.LEFT, padx=10)

        zf = tk.Frame(root)
        zf.pack()
        tk.Label(zf, text="Масштаб (размер клетки, px):").pack(side=tk.LEFT)
        self.zoom = tk.Scale(zf, from_=CELL_MIN, to=CELL_MAX, orient=tk.HORIZONTAL,
                             length=250, command=self.on_zoom)
        self.zoom.set(CELL_DEFAULT)
        self.zoom.pack(side=tk.LEFT)

        cf = tk.Frame(root)
        cf.pack(pady=3)
        tk.Button(cf, text="Построить из данных", command=self.apply_text).pack(side=tk.LEFT, padx=6)
        tk.Button(cf, text="Открыть файл...", command=self.open_file).pack(side=tk.LEFT, padx=6)
        tk.Button(cf, text="Вычисления (шаги алгоритма)", command=self.show_trace).pack(side=tk.LEFT, padx=6)
        self.show_src = tk.BooleanVar(value=True)
        tk.Checkbutton(cf, text="Исходные фигуры", variable=self.show_src,
                       command=self.redraw).pack(side=tk.LEFT, padx=6)

        mid = tk.Frame(root)
        mid.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.canvas = tk.Canvas(mid, width=760, height=620, bg="white")
        xb = tk.Scrollbar(mid, orient=tk.HORIZONTAL, command=self.canvas.xview)
        yb = tk.Scrollbar(mid, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xb.set, yscrollcommand=yb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        yb.grid(row=0, column=1, sticky="ns")
        xb.grid(row=1, column=0, sticky="ew")
        self.text = tk.Text(mid, width=26, height=30, font=("Courier New", 9))
        self.text.grid(row=0, column=2, sticky="ns", padx=(8, 0))
        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)

        self.status = tk.Label(root, text="", anchor="w")
        self.status.pack(fill=tk.X, padx=10)
        self.note = tk.Label(root, anchor="w", justify=tk.LEFT, fg="#0b6b2d", wraplength=900)
        self.note.pack(fill=tk.X, padx=10)
        tk.Label(root, anchor="w", justify=tk.LEFT, fg="#444444",
                 text="Точки ставятся в узлах сетки (пересечения линий), как в тетради. Тяните за угол окна, вершину "
                      "или конец отрезка; в пустом месте - новый отрезок (для Уайлера-Атертона - новая вершина "
                      "многоугольника).\nОранжевое - окно, светлое - исходные фигуры, синее - результат. "
                      "Ctrl + колесо мыши - масштаб.").pack(fill=tk.X, padx=10, pady=(0, 5))

        c = self.canvas
        c.bind("<Button-1>", self.down)
        c.bind("<B1-Motion>", self.move)
        c.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag", None))
        c.bind("<Motion>", self.motion)
        c.bind("<Control-MouseWheel>", lambda e: self.zoom.set(
            max(CELL_MIN, min(CELL_MAX, self.cell + (1 if e.delta > 0 else -1)))))
        self.sync_text()
        self.redraw()
        self.center_view()

    @property
    def mode(self):
        return self.algo.get()

    @property
    def rect(self):
        return self.rects["wa" if self.mode == "weiler_atherton" else "seg"]

    @rect.setter
    def rect(self, v):
        self.rects["wa" if self.mode == "weiler_atherton" else "seg"] = v

    def sx(self, x): return MARGIN_L + (x - X_MIN) * self.cell
    def sy(self, y): return MARGIN_T + (Y_MAX - y) * self.cell

    def to_world(self, e):
        cx, cy = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        x = round((cx - MARGIN_L) / self.cell) + X_MIN
        y = Y_MAX - round((cy - MARGIN_T) / self.cell)
        return max(X_MIN, min(X_MAX, x)), max(Y_MIN, min(Y_MAX, y))

    def center_view(self):
        self.root.update_idletasks()
        tw = self.sx(X_MAX) + MARGIN_R
        th = self.sy(Y_MIN) + MARGIN_B
        self.canvas.xview_moveto(max(0.0, (self.sx(0) - self.canvas.winfo_width() / 2) / tw))
        self.canvas.yview_moveto(max(0.0, (self.sy(0) - self.canvas.winfo_height() / 2) / th))

    def on_zoom(self, v):
        self.cell = int(float(v))
        self.redraw()
        self.center_view()

    def on_algo(self):
        self.sync_text()
        self.redraw()

    def fmt(self, vals):
        return " ".join(f"{v:g}" for v in vals)

    def sync_text(self):
        m = self.mode
        if m == "weiler_atherton":
            lines = [f"{len(self.subj)} *вершин многоугольника*"]
            lines += [self.fmt(p) for p in self.subj]
            lines.append(self.fmt(self.rect) + " *Xmin Ymin Xmax Ymax*")
        else:
            lines = [f"{len(self.segs)} *число отрезков*"] + [self.fmt(s) for s in self.segs]
            if m == "cyrus_beck":
                lines.append(f"{len(self.poly)} *вершин многоугольника*")
                lines += [self.fmt(p) for p in self.poly]
            else:
                lines.append(self.fmt(self.rect) + " *Xmin Ymin Xmax Ymax*")
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", "\n".join(lines))

    def apply_text(self):
        try:
            rows = [r.replace(",", ".").split("*")[0].split() for r in self.text.get("1.0", tk.END).split("\n")]
            rows = [r for r in rows if r]
            n = int(rows[0][0])
            items = [tuple(map(float, rows[1 + i])) for i in range(n)]
            m = self.mode
            if m == "weiler_atherton":
                self.subj = [p[:2] for p in items]
                self.rect = self.norm_rect(rows[1 + n])
            elif m == "cyrus_beck":
                self.segs = [list(p[:4]) for p in items]
                k = int(rows[1 + n][0])
                self.poly = [tuple(map(float, rows[2 + n + i][:2])) for i in range(k)]
            else:
                self.segs = [list(p[:4]) for p in items]
                self.rect = self.norm_rect(rows[1 + n])
        except (ValueError, IndexError):
            self.status.config(text="Ошибка формата данных")
            return
        self.redraw()

    @staticmethod
    def norm_rect(row):
        xa, ya, xb, yb = map(float, row[:4])
        return [min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)]

    def open_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename()
        if path:
            with open(path, encoding="utf-8") as f:
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", f.read())
            self.apply_text()

    def clear(self):
        if self.mode == "weiler_atherton":
            self.subj = []
        else:
            self.segs = []
        self.sync_text()
        self.redraw()

    def window_ok(self):
        return self.mode != "cyrus_beck" or is_convex(self.poly)

    def clip(self, s, log=None):
        m = self.mode
        if m == "liang_barsky":
            return liang_barsky(*s, tuple(self.rect), log)
        if m == "cohen_sutherland":
            return cohen_sutherland(*s, tuple(self.rect), log)
        return cyrus_beck(*s, self.poly, log)

    def draw_grid(self):
        c = self.canvas
        left, right = self.sx(X_MIN), self.sx(X_MAX)
        top, bot = self.sy(Y_MAX), self.sy(Y_MIN)
        for i in range(X_MIN, X_MAX + 1):
            c.create_line(self.sx(i), top, self.sx(i), bot, fill="#cccccc")
        for j in range(Y_MIN, Y_MAX + 1):
            c.create_line(left, self.sy(j), right, self.sy(j), fill="#cccccc")
        c.create_line(left, self.sy(0), right + 12, self.sy(0), fill="#222222", width=2, arrow=tk.LAST)
        c.create_line(self.sx(0), bot, self.sx(0), top - 12, fill="#222222", width=2, arrow=tk.LAST)
        c.create_text(right + 14, self.sy(0) - 10, text="X", font=("Arial", 10, "bold"))
        c.create_text(self.sx(0) + 12, top - 14, text="Y", font=("Arial", 10, "bold"))
        step = max(1, -(-24 // self.cell))
        for i in range(X_MIN, X_MAX + 1):
            if i % step == 0 and i != 0:
                c.create_text(self.sx(i), self.sy(0) + 10, text=str(i), font=("Arial", 8))
        for j in range(Y_MIN, Y_MAX + 1):
            if j % step == 0 and j != 0:
                c.create_text(self.sx(0) - 10, self.sy(j), text=str(j), font=("Arial", 8))
        c.create_text(self.sx(0) - 8, self.sy(0) + 10, text="0", font=("Arial", 8))
        c.configure(scrollregion=(0, 0, right + MARGIN_R, bot + MARGIN_B))

    def line(self, s, **kw):
        self.canvas.create_line(self.sx(s[0]), self.sy(s[1]), self.sx(s[2]), self.sy(s[3]), **kw)

    def dot(self, x, y, r, **kw):
        self.canvas.create_oval(self.sx(x) - r, self.sy(y) - r, self.sx(x) + r, self.sy(y) + r, **kw)

    def flat(self, pts):
        return [v for p in pts for v in (self.sx(p[0]), self.sy(p[1]))]

    def rect_corners(self):
        x0, y0, x1, y1 = self.rect
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    def redraw(self):
        c = self.canvas
        m = self.mode
        c.delete("all")
        self.draw_grid()
        self.note.config(text=NOTES[m])
        self.status.config(text="")
        if m == "cyrus_beck":
            c.create_polygon(*self.flat(self.poly), outline=C_WIN, fill="", width=2)
            handles = self.poly
        else:
            x0, y0, x1, y1 = self.rect
            c.create_rectangle(self.sx(x0), self.sy(y1), self.sx(x1), self.sy(y0), outline=C_WIN, width=2)
            handles = self.rect_corners()
        for hx, hy in handles:
            self.dot(hx, hy, 4, fill=C_WIN, outline="")

        if m == "weiler_atherton":
            self.draw_wa()
            return
        ok = self.window_ok()
        if self.show_src.get():
            for s in self.segs:
                self.line(s, fill=C_SRC, dash=(4, 3))
        for s in self.segs:
            self.dot(s[0], s[1], 3, outline=C_SRC)
            self.dot(s[2], s[3], 3, outline=C_SRC)
            if not ok:
                continue
            r = self.clip(s)
            if r:
                if abs(r[0] - r[2]) < EPS and abs(r[1] - r[3]) < EPS:
                    self.dot(r[0], r[1], 5, fill=C_VIS, outline="")
                else:
                    self.line(r, fill=C_VIS, width=3)
        if not ok:
            self.status.config(text="Многоугольник не выпуклый или вырожденный - отсечение недоступно")

    def draw_wa(self):
        c = self.canvas
        n = len(self.subj)
        if n >= 3 and self.show_src.get():
            c.create_polygon(*self.flat(self.subj), outline=C_SRC, fill="", dash=(4, 3), width=1)
        elif n == 2 and self.show_src.get():
            self.line(self.subj[0] + self.subj[1], fill=C_SRC, dash=(4, 3))
        for p in self.subj:
            self.dot(p[0], p[1], 3, outline=C_SRC)
        if n >= 3:
            res = self.wa_result()
            for r in res:
                c.create_polygon(*self.flat(r), fill=C_FILL, outline=C_VIS, width=3)
            self.status.config(text=f"Частей в результате: {len(res)}")

    def wa_result(self):
        return weiler_atherton([self.subj], tuple(self.rect))

    def pick(self, e):
        cx, cy = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        near = lambda x, y: abs(self.sx(x) - cx) < 8 and abs(self.sy(y) - cy) < 8
        m = self.mode
        if m == "cyrus_beck":
            for i, (hx, hy) in enumerate(self.poly):
                if near(hx, hy):
                    return ("poly", i)
        else:
            for i, (hx, hy) in enumerate(self.rect_corners()):
                if near(hx, hy):
                    return ("rect", i)
        if m == "weiler_atherton":
            for i, (hx, hy) in enumerate(self.subj):
                if near(hx, hy):
                    return ("subj", i)
            return None
        for i, s in enumerate(self.segs):
            for k in (0, 2):
                if near(s[k], s[k + 1]):
                    return ("seg", i, k)
        return None

    def down(self, e):
        self.drag = self.pick(e)
        if not self.drag:
            x, y = self.to_world(e)
            if self.mode == "weiler_atherton":
                self.subj.append((x, y))
                self.drag = ("subj", len(self.subj) - 1)
            else:
                self.segs.append([x, y, x, y])
                self.drag = ("seg", len(self.segs) - 1, 2)
        self.move(e)

    def move(self, e):
        if not self.drag:
            return
        x, y = self.to_world(e)
        d = self.drag
        if d[0] == "seg":
            self.segs[d[1]][d[2]], self.segs[d[1]][d[2] + 1] = x, y
        elif d[0] == "poly":
            self.poly[d[1]] = (x, y)
        elif d[0] == "subj":
            self.subj[d[1]] = (x, y)
        else:
            r = self.rect
            ox, oy = [(r[2], r[3]), (r[0], r[3]), (r[0], r[1]), (r[2], r[1])][d[1]]
            self.rect = [min(x, ox), min(y, oy), max(x, ox), max(y, oy)]
            r = self.rect
            self.drag = ("rect", {(r[0], r[1]): 0, (r[2], r[1]): 1,
                                  (r[2], r[3]): 2, (r[0], r[3]): 3}.get((x, y), d[1]))
        self.redraw()
        self.sync_text()

    def motion(self, e):
        x, y = self.to_world(e)
        self.status.config(text=f"Курсор: узел ({x}, {y})")

    def show_trace(self):
        m = self.mode
        out = []
        if m == "weiler_atherton":
            win = tuple(self.rect)
            out.append(f"Окно: {win}")
            out.append(f"Многоугольник: {self.subj}\n")
            res = self.wa_result() if len(self.subj) >= 3 else []
            out.append(f"Контуров в результате: {len(res)}")
            for i, r in enumerate(res):
                out.append(f"Контур {i + 1} (площадь {ring_area(r):.4f}):")
                out += [f"  ({p[0]:g}, {p[1]:g})" for p in r]
        else:
            if not self.window_ok():
                self.status.config(text="Многоугольник не выпуклый")
                return
            for i, s in enumerate(self.segs):
                out.append(f"Отрезок {i + 1}: ({s[0]:g},{s[1]:g}) -> ({s[2]:g},{s[3]:g}),"
                           f" d = ({s[2] - s[0]:g}, {s[3] - s[1]:g})")
                log = []
                r = self.clip(s, log)
                out += log
                out.append("  Результат: " + (f"({r[0]:.4f},{r[1]:.4f}) -> ({r[2]:.4f},{r[3]:.4f})"
                                              if r else "отрезок невидим") + "\n")
        win = tk.Toplevel(self.root)
        win.title("Вычисления")
        box = tk.Text(win, width=110, height=40, font=("Courier New", 9), wrap="none")
        sb = tk.Scrollbar(win, command=box.yview)
        box.configure(yscrollcommand=sb.set)
        box.insert("1.0", "\n".join(out))
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        box.pack(fill=tk.BOTH, expand=True)


if __name__ == "__main__":
    if "--test" in sys.argv:
        self_test()
    elif tk is None:
        print("tkinter не установлен. Проверка: python3 main.py --test")
    else:
        root = tk.Tk()
        App(root)
        root.mainloop()
