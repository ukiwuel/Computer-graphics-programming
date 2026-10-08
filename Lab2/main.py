import csv
import os
import queue
import re
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

HEAD_SIZE = 4096
WORKERS = min(16, (os.cpu_count() or 4) * 2)
BATCH = 300
SUPPORTED_EXT = {'.jpg', '.jpeg', '.gif', '.tif', '.tiff',
                 '.bmp', '.png', '.pcx'}

EXT_TO_FORMATS = {
    '.jpg': {'JPEG', 'MPO'}, '.jpeg': {'JPEG', 'MPO'},
    '.gif': {'GIF'}, '.tif': {'TIFF'}, '.tiff': {'TIFF'},
    '.bmp': {'BMP'}, '.png': {'PNG'}, '.pcx': {'PCX'},
}

MODE_BITS = {
    '1': 1, 'L': 8, 'P': 8, 'RGB': 24, 'RGBA': 32, 'RGBX': 32,
    'RGBa': 32, 'CMYK': 32, 'YCbCr': 24, 'LAB': 24, 'HSV': 24,
    'I': 32, 'F': 32, 'I;16': 16, 'I;16B': 16, 'I;16L': 16,
    'LA': 16, 'La': 16, 'PA': 16,
}

TIFF_COMPRESSION = {
    1: 'Нет', 2: 'CCITT RLE (Modified Huffman)', 3: 'CCITT Group 3 (T.4)',
    4: 'CCITT Group 4 (T.6)', 5: 'LZW', 6: 'JPEG (старый)', 7: 'JPEG',
    8: 'Deflate (Adobe)', 32773: 'PackBits', 32946: 'Deflate',
    34712: 'JPEG 2000',
}
TIFF_PHOTOMETRIC = {
    0: 'WhiteIsZero', 1: 'BlackIsZero', 2: 'RGB', 3: 'Palette',
    4: 'Mask', 5: 'CMYK', 6: 'YCbCr', 8: 'CIELab',
}
BMP_COMPRESSION = {0: 'Нет (BI_RGB)', 1: 'RLE8', 2: 'RLE4',
                   3: 'Bitfields', 4: 'JPEG', 5: 'PNG',
                   6: 'Alpha-bitfields'}
PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
PNG_COLOR_TYPE = {0: 'Градации серого', 2: 'RGB', 3: 'Палитра',
                  4: 'Серый+альфа', 6: 'RGBA'}



def _mode_bits(img):
    return MODE_BITS.get(img.mode, 0) or '—'


def _png_info(head):
    if len(head) < 29 or head[:8] != b'\x89PNG\r\n\x1a\n' \
            or head[12:16] != b'IHDR':
        return None
    bit_depth, ctype, _, _, interlace = struct.unpack_from('5B', head, 24)
    depth = bit_depth * PNG_CHANNELS.get(ctype, 1)
    extra = [f"тип цвета: {PNG_COLOR_TYPE.get(ctype, ctype)}",
             f"{bit_depth} бит/канал"]
    if interlace:
        extra.append('Adam7 (interlaced)')
    return {'depth': depth, 'comp': 'Deflate', 'extra': extra}


def _bmp_info(head):
    if len(head) < 30 or head[:2] != b'BM':
        return None
    hsize = struct.unpack_from('<I', head, 14)[0]
    extra = []
    if hsize == 12:                       # BITMAPCOREHEADER (OS/2)
        bpp = struct.unpack_from('<H', head, 24)[0]
        comp = 0
        extra.append('OS/2 core header')
    elif hsize >= 40 and len(head) >= 50:
        height = struct.unpack_from('<i', head, 22)[0]
        bpp = struct.unpack_from('<H', head, 28)[0]
        comp = struct.unpack_from('<I', head, 30)[0]
        clr_used = struct.unpack_from('<I', head, 46)[0]
        if bpp <= 8:
            extra.append(f"палитра: {clr_used or (1 << bpp)} цв.")
        if height < 0:
            extra.append('top-down')
        extra.append(f"DIB-заголовок {hsize} Б")
    else:
        return None
    return {'depth': bpp, 'comp': BMP_COMPRESSION.get(comp, f'код {comp}'),
            'extra': extra}


def _gif_info(head):
    if head[:6] not in (b'GIF87a', b'GIF89a') or len(head) < 13:
        return None
    packed = head[10]
    has_global = bool(packed & 0x80)
    gbits = (packed & 7) + 1
    pos = 13 + (3 * (1 << gbits) if has_global else 0)
    lbits = None
    interlaced = False
    while pos < len(head):
        b = head[pos]
        if b == 0x2C:
            if pos + 10 <= len(head):
                lp = head[pos + 9]
                if lp & 0x80:
                    lbits = (lp & 7) + 1
                interlaced = bool(lp & 0x40)
            break
        if b == 0x21:
            pos += 2
            while pos < len(head):
                size = head[pos]
                pos += 1 + size
                if size == 0:
                    break
        else:
            break
    bits = lbits or (gbits if has_global else None)
    if not bits:
        return None
    extra = [f"палитра: {1 << bits} цв."]
    if interlaced:
        extra.append('interlaced')
    extra.append(head[:6].decode())
    return {'depth': bits, 'comp': 'LZW', 'extra': extra}


def _pcx_info(head):
    if len(head) < 128 or head[0] != 0x0A:
        return None
    enc, bpp = head[2], head[3]
    hdpi, vdpi = struct.unpack_from('<2H', head, 12)
    planes = head[65]
    return {'depth': bpp * planes,
            'comp': 'RLE' if enc == 1 else 'Нет',
            'dpi': (hdpi, vdpi) if hdpi and vdpi else None,
            'extra': [f"плоскостей: {planes}", f"версия {head[1]}"]}


def _jpeg_info(img):
    progressive = bool(img.info.get('progressive')
                       or img.info.get('progression'))
    return {
        'depth': _mode_bits(img),
        'comp': 'JPEG (DCT, ' + ('progressive' if progressive
                                  else 'baseline') + ')',
        'extra': ['progressive' if progressive else 'baseline']
                 + (['Adobe'] if 'adobe' in img.info else []),
    }


def _tiff_info(img):
    tags = getattr(img, 'tag_v2', {})
    comp = tags.get(259, 1)
    bps = tags.get(258, 1)
    spp = tags.get(277, 1)
    if isinstance(bps, (tuple, list)):
        depth = sum(bps)
    else:
        depth = bps * spp
    extra = []
    photo = tags.get(262)
    if photo is not None:
        extra.append(TIFF_PHOTOMETRIC.get(photo, f'photometric {photo}'))
    try:
        frames = getattr(img, 'n_frames', 1)
        if frames > 1:
            extra.append(f"страниц: {frames}")
    except Exception:
        pass
    dpi = None
    xr, yr = tags.get(282), tags.get(283)
    unit = tags.get(296, 2)
    if xr and yr and unit in (2, 3):
        k = 2.54 if unit == 3 else 1.0
        dpi = (float(xr) * k, float(yr) * k)
    return {'depth': depth,
            'comp': TIFF_COMPRESSION.get(comp, f'код {comp}'),
            'extra': extra, 'dpi': dpi, 'own_dpi': True}


def _dpi_str(dpi):
    try:
        x, y = float(dpi[0]), float(dpi[1])
        if x > 0 and y > 0:
            return f"{x:.0f}×{y:.0f}"
    except Exception:
        pass
    return "—"


def _pillow_dpi(img):
    dpi = img.info.get('dpi')
    if not dpi:
        jd = img.info.get('jfif_density')
        ju = img.info.get('jfif_unit')
        if jd and ju == 1:
            dpi = jd
        elif jd and ju == 2:
            dpi = (jd[0] * 2.54, jd[1] * 2.54)
    return dpi


def analyze_file(path):
    name = os.path.basename(path)
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, 'rb') as f:
            head = f.read(HEAD_SIZE)
            f.seek(0)
            with Image.open(f) as img:
                fmt = img.format or ''
                w, h = img.size
                info = None
                if fmt == 'PNG':
                    info = _png_info(head)
                elif fmt == 'BMP':
                    info = _bmp_info(head)
                elif fmt == 'GIF':
                    info = _gif_info(head)
                    if getattr(img, 'is_animated', False):
                        if info:
                            info['extra'].append('анимация')
                elif fmt == 'PCX':
                    info = _pcx_info(head)
                elif fmt in ('JPEG', 'MPO'):
                    info = _jpeg_info(img)
                elif fmt == 'TIFF':
                    info = _tiff_info(img)
                if info is None:
                    info = {'depth': _mode_bits(img), 'comp': '—',
                            'extra': []}

                if info.get('own_dpi'):
                    dpi = info.get('dpi')
                else:
                    dpi = _pillow_dpi(img) or info.get('dpi')
                extra = list(info['extra'])
                expected = EXT_TO_FORMATS.get(ext)
                if expected and fmt not in expected:
                    extra.insert(
                        0, f"⚠ расширение {ext} не соответствует "
                           f"формату {fmt}")
                return {
                    'name': name,
                    'size': f"{w} × {h}",
                    'dpi': _dpi_str(dpi) if dpi else '—',
                    'depth': info['depth'],
                    'compression': info['comp'],
                    'format': fmt,
                    'extra': '; '.join(extra),
                    'error': False,
                }
    except Exception as e:
        reason = ('не является изображением или повреждён'
                  if isinstance(e, (OSError, SyntaxError, ValueError,
                                    struct.error, EOFError))
                  else type(e).__name__)
        return {
            'name': name, 'size': '—', 'dpi': '—', 'depth': '—',
            'compression': '—', 'format': '—',
            'extra': f"Ошибка: {reason}", 'error': True,
        }


COLUMNS = ('name', 'size', 'dpi', 'depth', 'compression', 'format', 'extra')
HEADERS = {
    'name': 'Файл',
    'size': 'Размер (px)',
    'dpi': 'DPI',
    'depth': 'Глубина цвета (бит)',
    'compression': 'Сжатие',
    'format': 'Формат',
    'extra': 'Дополнительно',
}
WIDTHS = {'name': 260, 'size': 110, 'dpi': 90, 'depth': 130,
          'compression': 170, 'format': 70, 'extra': 380}


def _numbers(s):
    return [int(x) for x in re.findall(r'\d+', str(s))]


def sort_key(col, val):
    if col == 'size':
        n = _numbers(val)
        return (0, n[0] * n[1]) if len(n) >= 2 else (1, 0)
    if col in ('dpi', 'depth'):
        n = _numbers(val)
        return (0, n[0]) if n else (1, 0)
    s = str(val).lower()
    return (0, [int(t) if t.isdigit() else t
                for t in re.split(r'(\d+)', s)])


class App:
    def __init__(self, root):
        self.root = root
        root.title("Лаба 2 — чтение информации из графических файлов")
        root.geometry("1250x700")

        top = ttk.Frame(root)
        top.pack(fill='x', padx=8, pady=6)

        self.folder_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.folder_var).pack(
            side='left', fill='x', expand=True)
        ttk.Button(top, text="Обзор...", command=self.choose_folder)\
            .pack(side='left', padx=4)
        self.recursive = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="С подпапками", variable=self.recursive)\
            .pack(side='left', padx=4)
        self.btn_run = ttk.Button(top, text="Анализ", command=self.run_analysis)
        self.btn_run.pack(side='left')
        self.btn_stop = ttk.Button(top, text="Стоп", command=self.stop,
                                   state='disabled')
        self.btn_stop.pack(side='left', padx=4)
        self.btn_csv = ttk.Button(top, text="Экспорт в CSV",
                                  command=self.export_csv)
        self.btn_csv.pack(side='left')

        self.status = tk.StringVar(value="Готов")
        ttk.Label(root, textvariable=self.status, anchor='w')\
            .pack(fill='x', padx=8)
        self.progress = ttk.Progressbar(root, mode='determinate')
        self.progress.pack(fill='x', padx=8, pady=(0, 4))

        frame = ttk.Frame(root)
        frame.pack(fill='both', expand=True, padx=8, pady=6)
        self.tree = ttk.Treeview(frame, columns=COLUMNS, show='headings')
        for c in COLUMNS:
            self.tree.heading(c, text=HEADERS[c],
                              command=lambda col=c: self.sort_by(col))
            self.tree.column(c, width=WIDTHS[c], anchor='w', stretch=False)
        self.tree.tag_configure('err', foreground='#b00020')
        vsb = ttk.Scrollbar(frame, orient='vertical', command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient='horizontal',
                            command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.q = queue.Queue()
        self.stop_evt = threading.Event()
        self.run_id = 0
        self.running = False
        self.done = 0
        self.total = 0
        self.errors = 0
        self.t0 = 0.0
        self.sort_state = {}

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._poll()

    def choose_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.folder_var.set(d)

    def on_close(self):
        self.stop_evt.set()
        self.root.destroy()

    def stop(self):
        self.stop_evt.set()
        self.status.set("Останавливаю...")

    def run_analysis(self):
        if self.running:
            return
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Ошибка", "Папка не выбрана или не существует")
            return
        self.tree.delete(*self.tree.get_children())
        self.run_id += 1
        self.stop_evt.clear()
        self.running = True
        self.done = self.total = self.errors = 0
        self.t0 = time.time()
        self.btn_run.configure(state='disabled')
        self.btn_stop.configure(state='normal')
        self.progress.configure(mode='indeterminate', maximum=100, value=0)
        self.progress.start(15)
        self.status.set("Сканирую папку...")
        threading.Thread(target=self._worker,
                         args=(folder, self.recursive.get(), self.run_id),
                         daemon=True).start()

    def export_csv(self):
        if not self.tree.get_children():
            messagebox.showinfo("Экспорт", "Таблица пуста")
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.csv', filetypes=[('CSV', '*.csv')])
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                wr = csv.writer(f, delimiter=';')
                wr.writerow([HEADERS[c] for c in COLUMNS])
                for iid in self.tree.get_children():
                    wr.writerow(self.tree.item(iid, 'values'))
        except OSError as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить: {e}")

    def sort_by(self, col):
        reverse = self.sort_state.get(col, True) is False
        self.sort_state = {col: not reverse}
        idx = COLUMNS.index(col)
        items = [(sort_key(col, self.tree.item(i, 'values')[idx]), i)
                 for i in self.tree.get_children()]
        items.sort(key=lambda t: t[0], reverse=reverse)
        for pos, (_, iid) in enumerate(items):
            self.tree.move(iid, '', pos)
        for c in COLUMNS:
            arrow = (' ▼' if reverse else ' ▲') if c == col else ''
            self.tree.heading(c, text=HEADERS[c] + arrow)

    def _scan(self, folder, recursive):
        files = []
        stack = [folder]
        while stack and not self.stop_evt.is_set():
            d = stack.pop()
            try:
                with os.scandir(d) as it:
                    for e in it:
                        try:
                            if e.is_file():
                                if os.path.splitext(e.name)[1].lower() \
                                        in SUPPORTED_EXT:
                                    files.append(e.path)
                            elif recursive and e.is_dir():
                                stack.append(e.path)
                        except OSError:
                            pass
            except OSError:
                pass
        return files

    def _job(self, path):
        if self.stop_evt.is_set():
            return None
        return analyze_file(path)

    def _worker(self, folder, recursive, run):
        q = self.q
        try:
            files = self._scan(folder, recursive)
            q.put(('total', run, len(files)))
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                for r in pool.map(self._job, files):
                    if r is not None:
                        q.put(('row', run, r))
        except Exception as e:
            q.put(('error', run, str(e)))
        finally:
            q.put(('end', run, None))

    def _poll(self):
        try:
            for _ in range(BATCH):
                kind, run, payload = self.q.get_nowait()
                if run != self.run_id:
                    continue
                if kind == 'total':
                    self.total = payload
                    self.progress.stop()
                    self.progress.configure(mode='determinate',
                                            maximum=max(payload, 1), value=0)
                elif kind == 'row':
                    self.tree.insert(
                        '', 'end',
                        values=tuple(payload[c] for c in COLUMNS),
                        tags=('err',) if payload['error'] else ())
                    self.done += 1
                    if payload['error']:
                        self.errors += 1
                elif kind == 'error':
                    messagebox.showerror("Ошибка", payload)
                elif kind == 'end':
                    self._finish()
        except queue.Empty:
            pass
        if self.running and self.total:
            self.progress.configure(value=self.done)
            self.status.set(f"Обработано {self.done} из {self.total}")
        self.root.after(30, self._poll)

    def _finish(self):
        elapsed = time.time() - self.t0
        stopped = self.stop_evt.is_set()
        self.running = False
        self.progress.stop()
        self.progress.configure(mode='determinate',
                                maximum=max(self.total, 1),
                                value=self.done)
        self.btn_run.configure(state='normal')
        self.btn_stop.configure(state='disabled')
        if not self.total and not stopped:
            self.status.set("Подходящих файлов в папке не найдено")
            return
        prefix = "Остановлено" if stopped else "Готово"
        self.status.set(
            f"{prefix}: {self.done} из {self.total} файлов за "
            f"{elapsed:.1f} с, ошибок/нечитаемых: {self.errors}")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()