import math
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from numba import njit, prange
from PIL import Image, ImageTk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

CLAMP, REFLECT = 0, 1


@njit(inline="always", cache=True)
def ix(i, n, mode):
    if mode == CLAMP:
        if i < 0:
            return 0
        if i >= n:
            return n - 1
        return i
    if n == 1:
        return 0
    while i < 0 or i >= n:
        if i < 0:
            i = -i - 1
        if i >= n:
            i = 2 * n - 1 - i
    return i


@njit(parallel=True, cache=True)
def conv2d(src, k, mode):
    h, w = src.shape
    kh, kw = k.shape
    ry, rx = kh // 2, kw // 2
    out = np.empty((h, w), np.float32)
    for y in prange(h):
        for x in range(w):
            acc = 0.0
            for j in range(kh):
                yy = ix(y + j - ry, h, mode)
                for i in range(kw):
                    xx = ix(x + i - rx, w, mode)
                    acc += src[yy, xx] * k[j, i]
            out[y, x] = acc
    return out


@njit(cache=True)
def gauss_kernel1d(sigma):
    r = max(1, int(math.ceil(3.0 * sigma)))
    k = np.empty(2 * r + 1, np.float32)
    s = 0.0
    for i in range(-r, r + 1):
        v = math.exp(-(i * i) / (2.0 * sigma * sigma))
        k[i + r] = v
        s += v
    for i in range(2 * r + 1):
        k[i] /= s
    return k


@njit(parallel=True, cache=True)
def sep_conv(src, k1, mode):
    h, w = src.shape
    r = len(k1) // 2
    tmp = np.empty((h, w), np.float32)
    out = np.empty((h, w), np.float32)
    for y in prange(h):
        for x in range(w):
            acc = 0.0
            for i in range(len(k1)):
                acc += src[y, ix(x + i - r, w, mode)] * k1[i]
            tmp[y, x] = acc
    for y in prange(h):
        for x in range(w):
            acc = 0.0
            for j in range(len(k1)):
                acc += tmp[ix(y + j - r, h, mode), x] * k1[j]
            out[y, x] = acc
    return out


LAP4 = np.array([[0, -1, 0], [-1, 4, -1], [0, -1, 0]], np.float32)


@njit(parallel=True, cache=True)
def combine_clip(base, detail, amount):
    h, w = base.shape
    out = np.empty((h, w), np.float32)
    for y in prange(h):
        for x in range(w):
            v = base[y, x] + amount * detail[y, x]
            out[y, x] = 0.0 if v < 0 else (255.0 if v > 255 else v)
    return out


@njit(parallel=True, cache=True)
def unsharp_detail(base, blurred):
    h, w = base.shape
    out = np.empty((h, w), np.float32)
    for y in prange(h):
        for x in range(w):
            out[y, x] = base[y, x] - blurred[y, x]
    return out


def sharpen_channel(ch, method, amount, sigma, mode):
    if method == 0:
        return combine_clip(ch, conv2d(ch, LAP4, mode), amount)
    blur = sep_conv(ch, gauss_kernel1d(sigma), mode)
    return combine_clip(ch, unsharp_detail(ch, blur), amount)


@njit(cache=True)
def hist256(gray):
    h = np.zeros(256, np.int64)
    hh, ww = gray.shape
    for y in range(hh):
        for x in range(ww):
            h[gray[y, x]] += 1
    return h


@njit(cache=True)
def otsu_threshold(hist):
    total = 0
    sum_all = 0.0
    for i in range(256):
        total += hist[i]
        sum_all += i * hist[i]
    w0 = 0.0
    sum0 = 0.0
    best, best_t = -1.0, 0
    for t in range(256):
        w0 += hist[t]
        if w0 == 0:
            continue
        w1 = total - w0
        if w1 == 0:
            break
        sum0 += t * hist[t]
        m0 = sum0 / w0
        m1 = (sum_all - sum0) / w1
        var_b = w0 * w1 * (m0 - m1) * (m0 - m1)
        if var_b > best:
            best = var_b
            best_t = t
    return best_t


@njit(cache=True)
def kapur_threshold(hist):
    total = 0.0
    for i in range(256):
        total += hist[i]
    p = np.empty(256)
    for i in range(256):
        p[i] = hist[i] / total
    best, best_t = -1e18, 0
    for t in range(255):
        pb = 0.0
        for i in range(t + 1):
            pb += p[i]
        if pb <= 1e-12 or pb >= 1 - 1e-12:
            continue
        hb = 0.0
        for i in range(t + 1):
            if p[i] > 0:
                q = p[i] / pb
                hb -= q * math.log(q)
        ho = 0.0
        for i in range(t + 1, 256):
            if p[i] > 0:
                q = p[i] / (1 - pb)
                ho -= q * math.log(q)
        if hb + ho > best:
            best = hb + ho
            best_t = t
    return best_t


@njit(parallel=True, cache=True)
def binarize(gray, t):
    h, w = gray.shape
    out = np.empty((h, w), np.uint8)
    for y in prange(h):
        for x in range(w):
            out[y, x] = 255 if gray[y, x] > t else 0
    return out


@njit(cache=True)
def integral_images(gray):
    h, w = gray.shape
    s = np.zeros((h + 1, w + 1), np.float64)
    s2 = np.zeros((h + 1, w + 1), np.float64)
    for y in range(h):
        row = 0.0
        row2 = 0.0
        for x in range(w):
            v = float(gray[y, x])
            row += v
            row2 += v * v
            s[y + 1, x + 1] = s[y, x + 1] + row
            s2[y + 1, x + 1] = s2[y, x + 1] + row2
    return s, s2


@njit(parallel=True, cache=True)
def local_stats(gray, s, s2, r):
    h, w = gray.shape
    mean = np.empty((h, w), np.float32)
    std = np.empty((h, w), np.float32)
    for y in prange(h):
        y0 = max(0, y - r)
        y1 = min(h - 1, y + r) + 1
        for x in range(w):
            x0 = max(0, x - r)
            x1 = min(w - 1, x + r) + 1
            n = (y1 - y0) * (x1 - x0)
            a = s[y1, x1] - s[y0, x1] - s[y1, x0] + s[y0, x0]
            b = s2[y1, x1] - s2[y0, x1] - s2[y1, x0] + s2[y0, x0]
            m = a / n
            var = b / n - m * m
            mean[y, x] = m
            std[y, x] = math.sqrt(var) if var > 0 else 0.0
    return mean, std


@njit(parallel=True, cache=True)
def adaptive_apply(gray, mean, std, k):
    h, w = gray.shape
    out = np.empty((h, w), np.uint8)
    for y in prange(h):
        for x in range(w):
            m = mean[y, x]
            sd = std[y, x]
            t = m * (1.0 + k * (sd / 128.0 - 1.0))
            out[y, x] = 255 if gray[y, x] > t else 0
    return out


def adaptive_threshold(gray, window, k):
    s, s2 = integral_images(gray)
    mean, std = local_stats(gray, s, s2, window // 2)
    return adaptive_apply(gray, mean, std, k)


def to_gray(rgb):
    return _to_gray(rgb)


@njit(parallel=True, cache=True)
def _to_gray(rgb):
    h, w, _ = rgb.shape
    out = np.empty((h, w), np.uint8)
    for y in prange(h):
        for x in range(w):
            v = 0.299 * rgb[y, x, 0] + 0.587 * rgb[y, x, 1] + 0.114 * rgb[y, x, 2]
            out[y, x] = np.uint8(v + 0.5)
    return out


def sharpen_image(rgb, method, amount, sigma, mode):
    out = np.empty(rgb.shape, np.uint8)
    for c in range(3):
        ch = np.ascontiguousarray(rgb[:, :, c]).astype(np.float32)
        res = sharpen_channel(ch, method, amount, sigma, mode)
        out[:, :, c] = (res + 0.5).astype(np.uint8)
    return out


class App(tk.Tk):
    VIEW_W, VIEW_H = 520, 360

    def __init__(self):
        super().__init__()
        self.title("ЛР1, вариант 8: резкость, глобальный и адаптивный пороги")
        self.geometry("1250x900")
        self.src = None       # RGB uint8
        self.busy = False
        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=6, pady=4)
        ttk.Button(top, text="Открыть...", command=self.open_image).pack(side="left")
        ttk.Label(top, text="  Края:").pack(side="left")
        self.edge = ttk.Combobox(top, values=["Clamp (дублирование)", "Reflect (зеркало)"],
                                 state="readonly", width=20)
        self.edge.current(0)
        self.edge.pack(side="left")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="x", padx=6)

        f1 = ttk.Frame(self.nb)
        self.nb.add(f1, text="Резкость (ВЧ-фильтры)")
        self.sh_method = ttk.Combobox(f1, state="readonly", width=34, values=[
            "Лапласиан", "Нерезкая маска (Гаусс, разделяемая свёртка)"])
        self.sh_method.current(1)
        self.sh_amount = tk.Scale(f1, from_=0.1, to=5.0, resolution=0.1, orient="horizontal",
                                  length=220, label="Сила (amount)")
        self.sh_amount.set(1.5)
        self.sh_sigma = tk.Scale(f1, from_=0.5, to=10.0, resolution=0.1, orient="horizontal",
                                 length=220, label="σ Гаусса (нерезкая маска)")
        self.sh_sigma.set(2.0)
        for w in (self.sh_method, self.sh_amount, self.sh_sigma):
            w.pack(side="left", padx=8, pady=4)

        f2 = ttk.Frame(self.nb)
        self.nb.add(f2, text="Глобальный порог")
        self.gl_method = ttk.Combobox(f2, state="readonly", width=28,
                                      values=["Оцу", "Капур (энтропия)"])
        self.gl_method.current(0)
        self.gl_method.pack(side="left", padx=8, pady=4)

        f3 = ttk.Frame(self.nb)
        self.nb.add(f3, text="Адаптивный порог (Саувола, SAT)")
        self.ad_win = tk.Scale(f3, from_=3, to=151, resolution=2, orient="horizontal",
                               length=220, label="Размер окна")
        self.ad_win.set(31)
        self.ad_k = tk.Scale(f3, from_=0.01, to=0.9, resolution=0.01, orient="horizontal",
                             length=220, label="k")
        self.ad_k.set(0.3)
        for w in (self.ad_win, self.ad_k):
            w.pack(side="left", padx=8, pady=4)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=4)
        ttk.Button(bar, text="Применить", command=self.apply).pack(side="left")
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=200)
        self.progress.pack(side="left", padx=10)
        self.status = ttk.Label(bar, text="Откройте изображение")
        self.status.pack(side="left")

        views = ttk.Frame(self)
        views.pack(fill="x", padx=6)
        self.lbl_before = ttk.Label(views)
        self.lbl_after = ttk.Label(views)
        self.lbl_before.pack(side="left", expand=True)
        self.lbl_after.pack(side="left", expand=True)

        self.fig = Figure(figsize=(10, 2.8), dpi=90)
        self.ax1 = self.fig.add_subplot(121)
        self.ax2 = self.fig.add_subplot(122)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=4)

    def open_image(self):
        p = filedialog.askopenfilename(filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff")])
        if not p:
            return
        self.src = np.ascontiguousarray(np.asarray(Image.open(p).convert("RGB")))
        self._show(self.lbl_before, self.src)
        self.lbl_after.configure(image="")
        self._hists(None, None)
        self.status.config(text=f"{os.path.basename(p)}  {self.src.shape[1]}x{self.src.shape[0]}")

    def apply(self):
        if self.src is None:
            messagebox.showwarning("Нет изображения", "Сначала откройте изображение")
            return
        if self.busy:
            return
        self.busy = True
        self.progress.start(10)
        tab = self.nb.index(self.nb.select())
        params = dict(
            tab=tab, mode=self.edge.current(),
            sh=self.sh_method.current(), amount=float(self.sh_amount.get()),
            sigma=float(self.sh_sigma.get()),
            gl=self.gl_method.current(),
            win=int(self.ad_win.get()), k=float(self.ad_k.get()))
        threading.Thread(target=self._worker, args=(params,), daemon=True).start()

    def _worker(self, p):
        try:
            info = ""
            thr = None
            if p["tab"] == 0:
                res = sharpen_image(self.src, p["sh"], p["amount"], p["sigma"], p["mode"])
            elif p["tab"] == 1:
                gray = to_gray(self.src)
                h = hist256(gray)
                thr = otsu_threshold(h) if p["gl"] == 0 else kapur_threshold(h)
                res = binarize(gray, thr)
                info = f"порог = {thr}"
            else:
                gray = to_gray(self.src)
                res = adaptive_threshold(gray, p["win"], p["k"])
            self.after(0, self._done, res, thr, info)
        except Exception as e:  # noqa
            self.after(0, self._fail, str(e))

    def _done(self, res, thr, text):
        self.progress.stop()
        self.busy = False
        self._show(self.lbl_after, res)
        self._hists(res, thr)
        self.status.config(text=text)

    def _fail(self, msg):
        self.progress.stop()
        self.busy = False
        messagebox.showerror("Ошибка", msg)

    def _show(self, label, arr):
        im = Image.fromarray(arr)
        im.thumbnail((self.VIEW_W, self.VIEW_H))
        ph = ImageTk.PhotoImage(im)
        label.configure(image=ph)
        label.image = ph

    def _hists(self, res, thr):
        self.ax1.clear()
        self.ax2.clear()
        if self.src is not None:
            h = hist256(to_gray(self.src))
            self.ax1.bar(range(256), h, width=1.0, color="gray")
            if thr is not None:
                self.ax1.axvline(thr, color="red", label=f"порог {thr}")
                self.ax1.legend()
        self.ax1.set_title("Гистограмма: до")
        if res is not None:
            g = res if res.ndim == 2 else to_gray(np.ascontiguousarray(res))
            self.ax2.bar(range(256), hist256(g), width=1.0, color="steelblue")
        self.ax2.set_title("Гистограмма: после")
        self.fig.tight_layout()
        self.canvas.draw_idle()


if __name__ == "__main__":
    App().mainloop()
