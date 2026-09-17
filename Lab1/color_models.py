# color_models.py
# Слой Model: только математика преобразований цветов. Ничего не знает про UI.
import math

# ---------- Матричные операции ----------
def mat_mul_vec(M, v):
    return [sum(M[i][j] * v[j] for j in range(3)) for i in range(3)]

def mat_mul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

def mat_inv_3x3(M):
    """Обращение матрицы 3x3 методом Гаусса (без внешних библиотек)."""
    n = 3
    aug = [M[i][:] + [1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for i in range(n):
        pivot = aug[i][i]
        if abs(pivot) < 1e-12:
            swap = i
            for k in range(i + 1, n):
                if abs(aug[k][i]) > abs(aug[swap][i]):
                    swap = k
            aug[i], aug[swap] = aug[swap], aug[i]
            pivot = aug[i][i]
        for j in range(2 * n):
            aug[i][j] /= pivot
        for k in range(n):
            if k != i:
                factor = aug[k][i]
                for j in range(2 * n):
                    aug[k][j] -= factor * aug[i][j]
    return [row[n:] for row in aug]

# ---------- Базовая матрица sRGB -> XYZ (D65) ----------
M_D65 = [
    [0.4124, 0.3576, 0.1805],
    [0.2126, 0.7152, 0.0722],
    [0.0193, 0.1192, 0.9505]
]
M_D65_inv = mat_inv_3x3(M_D65)

WHITE_D65 = (0.95047, 1.0, 1.08883)
WHITE_D50 = (0.96422, 1.0, 0.82521)
WHITE_E   = (1.0, 1.0, 1.0)

WHITE_POINTS = {'D65': WHITE_D65, 'D50': WHITE_D50, 'E': WHITE_E}

# Матрица Брэдфорда XYZ -> LMS (только для адаптации под другую белую точку)
M_B = [
    [0.8951, 0.2664, -0.1614],
    [-0.7502, 1.7135, 0.0367],
    [0.0389, -0.0685, 1.0296]
]
M_B_inv = mat_inv_3x3(M_B)

def adapt_matrix_for_whitepoint(M, src_wp, dst_wp):
    """Адаптация матрицы RGB->XYZ под новую белую точку методом Брэдфорда (на лету)."""
    lms_src = mat_mul_vec(M_B, list(src_wp))
    lms_dst = mat_mul_vec(M_B, list(dst_wp))
    k = [lms_dst[i] / lms_src[i] for i in range(3)]
    K = [[k[0], 0, 0], [0, k[1], 0], [0, 0, k[2]]]
    temp = mat_mul(M_B, M)
    temp = mat_mul(K, temp)
    return mat_mul(M_B_inv, temp)

def get_matrices_for_standard(standard):
    """Возвращает (M_RGB2XYZ, M_XYZ2RGB, белая_точка) для стандарта освещения.
    Матрицы для D50/E не захардкожены — пересчитываются адаптацией Брэдфорда от D65."""
    if standard == 'D65':
        return M_D65, M_D65_inv, WHITE_D65
    elif standard in WHITE_POINTS:
        M = adapt_matrix_for_whitepoint(M_D65, WHITE_D65, WHITE_POINTS[standard])
        return M, mat_inv_3x3(M), WHITE_POINTS[standard]
    else:
        raise ValueError("Unknown standard: %s" % standard)

# ---------- RGB <-> XYZ ----------
def rgb_to_xyz(r, g, b, M):
    return tuple(mat_mul_vec(M, [r, g, b]))

def xyz_to_rgb(x, y, z, Minv):
    return tuple(mat_mul_vec(Minv, [x, y, z]))

# ---------- RGB <-> HSV ----------
def rgb_to_hsv(r, g, b):
    maxv = max(r, g, b)
    minv = min(r, g, b)
    delta = maxv - minv
    V = maxv
    S = delta / maxv if maxv != 0 else 0.0
    if delta == 0:
        H = 0.0
    else:
        if maxv == r:
            H = 60 * (((g - b) / delta) % 6)
        elif maxv == g:
            H = 60 * (2 + (b - r) / delta)
        else:
            H = 60 * (4 + (r - g) / delta)
        if H < 0:
            H += 360
    return H, S, V

def hsv_to_rgb(H, S, V):
    if S == 0:
        return V, V, V
    H = (H % 360) / 60.0
    i = int(math.floor(H))
    f = H - i
    a = V * (1 - S)
    b = V * (1 - S * f)
    c = V * (1 - S * (1 - f))
    if i == 0:
        return V, c, a
    elif i == 1:
        return b, V, a
    elif i == 2:
        return a, V, c
    elif i == 3:
        return a, b, V
    elif i == 4:
        return c, a, V
    else:
        return V, a, b

# ---------- Стратегии обработки выхода за границы [0,1] ----------
def clamp_rgb(r, g, b):
    out = (r < 0 or r > 1 or g < 0 or g > 1 or b < 0 or b > 1)
    return (max(0.0, min(1.0, r)), max(0.0, min(1.0, g)), max(0.0, min(1.0, b))), out

def scale_rgb(r, g, b):
    out = (r < 0 or r > 1 or g < 0 or g > 1 or b < 0 or b > 1)
    if not out:
        return (r, g, b), False
    mn = min(r, g, b)
    mx = max(r, g, b)
    if mx == mn:
        return (0.0, 0.0, 0.0), True
    return ((r - mn) / (mx - mn), (g - mn) / (mx - mn), (b - mn) / (mx - mn)), True

STRATEGIES = {'clip': clamp_rgb, 'scale': scale_rgb}

# ---------- Модель ----------
class ColorModel:
    """Чистая модель цвета: хранит текущий цвет (RGB/XYZ/HSV) и умеет пересчитывать
    все представления друг из друга. Не содержит ни строчки Qt/UI кода."""

    def __init__(self):
        self.standard = 'D65'
        self.strategy = 'clip'
        self._M, self._Minv, self._white = get_matrices_for_standard(self.standard)

        self.r = self.g = self.b = 0.0
        self.x = self.y = self.z = 0.0
        self.h = self.s = self.v = 0.0

        self.out_of_gamut = False  # признак для UI-предупреждения "цвет скорректирован"
        self._updating = False
        self._recompute_all_from_rgb(0.0, 0.0, 0.0)

    # ---- смена настроек ----
    def set_standard(self, standard):
        if standard != self.standard:
            self.standard = standard
            self._M, self._Minv, self._white = get_matrices_for_standard(standard)
            self._recompute_all_from_rgb(self.r, self.g, self.b)

    def set_strategy(self, strategy):
        if strategy != self.strategy:
            self.strategy = strategy
            self._recompute_all_from_xyz(self.x, self.y, self.z)

    # ---- внутренние пересчёты ----
    def _recompute_all_from_rgb(self, r, g, b):
        if self._updating:
            return
        self._updating = True
        self.out_of_gamut = False
        self.r, self.g, self.b = r, g, b
        self.x, self.y, self.z = rgb_to_xyz(r, g, b, self._M)
        self.h, self.s, self.v = rgb_to_hsv(r, g, b)
        self._updating = False

    def _recompute_all_from_xyz(self, x, y, z):
        if self._updating:
            return
        self._updating = True
        self.x, self.y, self.z = x, y, z
        r, g, b = xyz_to_rgb(x, y, z, self._Minv)
        fn = STRATEGIES.get(self.strategy, clamp_rgb)
        (r, g, b), out = fn(r, g, b)
        self.out_of_gamut = out
        self.r, self.g, self.b = r, g, b
        self.h, self.s, self.v = rgb_to_hsv(r, g, b)
        self._updating = False

    def _recompute_all_from_hsv(self, h, s, v):
        if self._updating:
            return
        self._updating = True
        self.out_of_gamut = False
        self.h, self.s, self.v = h, s, v
        r, g, b = hsv_to_rgb(h, s, v)
        self.r, self.g, self.b = r, g, b
        self.x, self.y, self.z = rgb_to_xyz(r, g, b, self._M)
        self._updating = False

    # ---- публичный API ----
    def set_rgb(self, r, g, b):
        self._recompute_all_from_rgb(r, g, b)

    def set_xyz(self, x, y, z):
        self._recompute_all_from_xyz(x, y, z)

    def set_hsv(self, h, s, v):
        self._recompute_all_from_hsv(h, s, v)

    def get_rgb(self):
        return (self.r, self.g, self.b)

    def get_xyz(self):
        return (self.x, self.y, self.z)

    def get_hsv(self):
        return (self.h, self.s, self.v)

    def white_point(self):
        return self._white