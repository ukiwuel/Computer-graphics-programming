import os
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HEAD_SIZE = 8192
TAIL_SIZE = 4096
WORKERS = min(32, (os.cpu_count() or 4) * 4)
BATCH = 300

SUPPORTED_EXT = {'.jpg', '.jpeg', '.gif', '.tif', '.tiff',
                 '.bmp', '.png', '.pcx'}
EXT_TO_FORMAT = {
    '.jpg': 'JPEG', '.jpeg': 'JPEG', '.gif': 'GIF', '.tif': 'TIFF',
    '.tiff': 'TIFF', '.bmp': 'BMP', '.png': 'PNG', '.pcx': 'PCX',
}

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


class Corrupt(Exception):
    pass


def u16(b, o, le=True):
    return int.from_bytes(b[o:o + 2], 'little' if le else 'big')


def u32(b, o, le=True):
    return int.from_bytes(b[o:o + 4], 'little' if le else 'big')


def u64(b, o, le=True):
    return int.from_bytes(b[o:o + 8], 'little' if le else 'big')


def s32(b, o, le=True):
    return int.from_bytes(b[o:o + 4], 'little' if le else 'big', signed=True)


def need(data, n, what='обрыв заголовка'):
    if len(data) < n:
        raise Corrupt(what)
    return data


class Src:
    def __init__(self, f, size):
        self.f = f
        self.size = size
        self.head = f.read(HEAD_SIZE)
        if len(self.head) < HEAD_SIZE:
            self.size = len(self.head)
        else:
            try:
                self.size = os.fstat(f.fileno()).st_size
            except OSError:
                self.size = size

    def read(self, off, n):
        if off < 0 or n <= 0 or off >= self.size:
            return b''
        h = self.head
        if off + n <= len(h):
            return h[off:off + n]
        if len(h) < HEAD_SIZE:
            return h[off:off + n]
        self.f.seek(off)
        return self.f.read(n)

    def tail(self, n):
        return self.read(max(0, self.size - n), n)


class BufSrc:
    def __init__(self, data):
        self.data = data
        self.size = len(data)

    def read(self, off, n):
        if off < 0 or n <= 0:
            return b''
        return self.data[off:off + n]


def new_result(fmt):
    return {'fmt': fmt, 'w': None, 'h': None, 'dpi': None, 'depth': None,
            'comp': '—', 'extra': [], 'problems': []}


def ppm_to_dpi(x, y):
    if x > 0 and y > 0:
        return (x * 0.0254, y * 0.0254)
    return None


PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
PNG_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8),
              4: (8, 16), 6: (8, 16)}
PNG_COLOR_NAMES = {0: 'градации серого', 2: 'RGB', 3: 'палитра',
                   4: 'серый + альфа', 6: 'RGBA'}


def parse_png(src, r):
    pos = 8
    first = need(src.read(pos, 8), 8, 'обрыв до конца блока IHDR')
    if first[4:8] == b'CgBI':
        pos += 12 + u32(first, 0, False)
        r['extra'].append('Apple CgBI (PNG от iOS)')
    ihdr = need(src.read(pos, 25), 25, 'обрыв до конца блока IHDR')
    if u32(ihdr, 0, False) != 13 or ihdr[4:8] != b'IHDR':
        raise Corrupt('первым блоком не является IHDR')
    w = u32(ihdr, 8, False)
    h = u32(ihdr, 12, False)
    bit_depth, color_type, comp_method, filter_method, interlace = ihdr[16:21]
    r['w'], r['h'] = w, h
    r['depth'] = bit_depth * PNG_CHANNELS.get(color_type, 1)
    r['comp'] = 'Deflate (zlib)'
    if w == 0 or h == 0 or w > 0x7FFFFFFF or h > 0x7FFFFFFF:
        r['problems'].append('недопустимые размеры в IHDR')
    if color_type not in PNG_DEPTHS:
        r['problems'].append('неизвестный тип цвета в IHDR')
    elif bit_depth not in PNG_DEPTHS[color_type]:
        r['problems'].append('недопустимое сочетание глубины и типа цвета')
    if comp_method != 0:
        r['problems'].append('неизвестный метод сжатия в IHDR')
    if interlace > 1:
        r['problems'].append('неизвестный метод чересстрочности в IHDR')
    if filter_method != 0:
        r['problems'].append('неизвестный метод фильтрации в IHDR')
    r['extra'].append('тип цвета: ' +
                      PNG_COLOR_NAMES.get(color_type, f'код {color_type}'))
    r['extra'].append(f'{bit_depth} бит на канал')
    r['extra'].append('фильтрация: метод 0 (5 типов фильтров по строкам)'
                      if filter_method == 0
                      else f'фильтрация: метод {filter_method}')
    if interlace:
        r['extra'].append('чересстрочность Adam7')

    pos += 25
    has_idat = False
    has_plte = False
    for _ in range(256):
        hd = src.read(pos, 8)
        if len(hd) < 8:
            break
        ln = u32(hd, 0, False)
        typ = hd[4:8]
        name = typ.decode('latin-1')
        if pos + 12 + ln > src.size:
            r['problems'].append(f'блок {name} выходит за конец файла')
            has_idat = True
            break
        if typ == b'IDAT':
            has_idat = True
            break
        if typ == b'IEND':
            break
        if typ == b'pHYs' and ln == 9:
            d = src.read(pos + 8, 9)
            if len(d) == 9 and d[8] == 1:
                r['dpi'] = ppm_to_dpi(u32(d, 0, False), u32(d, 4, False))
        elif typ == b'PLTE':
            has_plte = True
            r['extra'].append(f'палитра: {ln // 3} цв.')
        elif typ == b'tRNS':
            r['extra'].append('прозрачность (tRNS)')
        elif typ == b'acTL':
            r['extra'].append('анимация APNG')
        elif typ == b'iCCP':
            r['extra'].append('ICC-профиль')
        pos += 12 + ln
    if not has_idat:
        r['problems'].append('нет блока данных IDAT')
    if color_type == 3 and not has_plte:
        r['problems'].append('нет палитры PLTE')
    if b'IEND' not in src.tail(32):
        r['problems'].append('нет завершающего блока IEND')
    return r


JPEG_SOF = {
    0xC0: 'DCT, Huffman, baseline',
    0xC1: 'DCT, Huffman, extended sequential',
    0xC2: 'DCT, Huffman, progressive',
    0xC3: 'без потерь, Huffman',
    0xC5: 'DCT, Huffman, differential sequential',
    0xC6: 'DCT, Huffman, differential progressive',
    0xC7: 'без потерь, Huffman, differential',
    0xC9: 'DCT, арифметическое, sequential',
    0xCA: 'DCT, арифметическое, progressive',
    0xCB: 'без потерь, арифметическое',
    0xCD: 'DCT, арифметическое, differential sequential',
    0xCE: 'DCT, арифметическое, differential progressive',
    0xCF: 'без потерь, арифметическое, differential',
}
JPEG_SUBSAMPLING = {(1, 1): '4:4:4', (2, 1): '4:2:2', (2, 2): '4:2:0',
                    (1, 2): '4:4:0', (4, 1): '4:1:1', (4, 2): '4:1:0'}


def parse_jpeg(src, r):
    pos = 2
    sof = None
    jfif_dpi = None
    exif_dpi = None
    adobe = None
    dqt = []
    flags = []
    has_icc = False
    for _ in range(2000):
        hd = src.read(pos, 4)
        if len(hd) < 2:
            break
        if hd[0] != 0xFF:
            raise Corrupt('нарушена структура маркеров')
        m = hd[1]
        if m == 0xFF:
            pos += 1
            continue
        if m == 0x00 or m == 0x01 or 0xD0 <= m <= 0xD8:
            pos += 2
            continue
        if m == 0xD9 or len(hd) < 4:
            break
        ln = u16(hd, 2, False)
        if ln < 2:
            raise Corrupt('некорректная длина сегмента')
        body = ln - 2
        start = pos + 4
        if m == 0xDA:
            break
        if m in JPEG_SOF:
            d = need(src.read(start, body), body, 'обрыв сегмента SOF')
            need(d, 6, 'слишком короткий сегмент SOF')
            n = d[5]
            need(d, 6 + 3 * n, 'слишком короткий сегмент SOF')
            comps = [(d[6 + 3 * i], d[7 + 3 * i] >> 4, d[7 + 3 * i] & 15)
                     for i in range(n)]
            sof = (m, d[0], u16(d, 1, False), u16(d, 3, False), comps)
        elif m == 0xE0 and body >= 14:
            d = src.read(start, 14)
            if d[:5] == b'JFIF\x00' and len(d) >= 12:
                unit = d[7]
                xd = u16(d, 8, False)
                yd = u16(d, 10, False)
                flags.append(f'JFIF {d[5]}.{d[6]:02d}')
                if unit == 1 and xd and yd:
                    jfif_dpi = (xd, yd)
                elif unit == 2 and xd and yd:
                    jfif_dpi = (xd * 2.54, yd * 2.54)
        elif m == 0xE1 and body >= 14:
            if src.read(start, 6) == b'Exif\x00\x00':
                flags.append('EXIF')
                if exif_dpi is None:
                    d = src.read(start + 6, body - 6)
                    exif_dpi = exif_resolution(d)
        elif m == 0xE2 and not has_icc:
            if src.read(start, 12) == b'ICC_PROFILE\x00':
                has_icc = True
                flags.append('ICC-профиль')
        elif m == 0xEE:
            d = src.read(start, 12)
            if len(d) >= 12 and d[:5] == b'Adobe':
                adobe = d[11]
                flags.append('Adobe APP14')
        elif m == 0xDB:
            d = src.read(start, body)
            o = 0
            while o < len(d):
                pq = d[o] >> 4
                dqt.append(16 if pq else 8)
                o += 1 + 64 * (pq + 1)
        pos = start + body
    if sof is None:
        raise Corrupt('не найден сегмент SOF (нет данных изображения)')
    marker, precision, h, w, comps = sof
    if w == 0:
        raise Corrupt('нулевая ширина в SOF')
    if h == 0:
        r['problems'].append('высота в SOF равна 0')
    if not comps or precision == 0:
        raise Corrupt('некорректный сегмент SOF')
    n = len(comps)
    ids = [c[0] for c in comps]
    if n == 1:
        model = 'оттенки серого'
    elif n == 3:
        model = 'RGB' if adobe == 0 or ids == [0x52, 0x47, 0x42] else 'YCbCr'
    elif n == 4:
        model = 'YCCK' if adobe == 2 else 'CMYK'
    else:
        model = f'{n} компонентов'
    r['w'], r['h'] = w, h
    r['depth'] = precision * n
    r['dpi'] = jfif_dpi or exif_dpi
    r['comp'] = f'JPEG ({JPEG_SOF[marker]})'
    r['extra'].append(f'цветовая модель: {model}')
    r['extra'].append(f'{precision} бит на компонент, компонентов: {n}')
    if n == 3 and model == 'YCbCr':
        (h1, v1), (h2, v2) = comps[0][1:], comps[1][1:]
        if h2 and v2 and h1 % h2 == 0 and v1 % v2 == 0:
            ss = JPEG_SUBSAMPLING.get((h1 // h2, v1 // v2))
            if ss:
                r['extra'].append('субдискретизация ' + ss)
    if dqt:
        bits = '/'.join(str(b) for b in sorted(set(dqt)))
        r['extra'].append(f'таблиц квантования (DQT): {len(dqt)}, {bits} бит')
    r['extra'].extend(dict.fromkeys(flags))
    if b'\xff\xd9' not in src.tail(TAIL_SIZE):
        r['problems'].append('нет маркера конца изображения EOI (FF D9)')
    return r


def parse_gif(src, r):
    h = need(src.read(0, 13), 13, 'обрыв заголовка GIF')
    version = h[:6].decode('ascii', 'replace')
    w = u16(h, 6)
    hh = u16(h, 8)
    packed = h[10]
    has_gct = bool(packed & 0x80)
    color_res = ((packed >> 4) & 7) + 1
    gct_bits = (packed & 7) + 1
    pos = 13 + (3 * (1 << gct_bits) if has_gct else 0)
    if w == 0 or hh == 0:
        raise Corrupt('нулевой размер логического экрана')
    if pos > src.size:
        r['problems'].append('глобальная таблица цветов выходит за конец файла')

    frame_bits = None
    local = False
    interlaced = False
    transparent = False
    animated = False
    found = False
    for _ in range(1000):
        b = src.read(pos, 1)
        if not b:
            break
        t = b[0]
        if t == 0x21:
            lab = src.read(pos + 1, 1)
            if not lab:
                break
            if lab[0] == 0xF9:
                g = src.read(pos + 2, 6)
                if len(g) >= 2 and g[1] & 1:
                    transparent = True
            elif lab[0] == 0xFF:
                a = src.read(pos + 2, 12)
                if a[1:12] == b'NETSCAPE2.0':
                    animated = True
            pos += 2
            complete = False
            for _ in range(100000):
                sz = src.read(pos, 1)
                if not sz:
                    break
                pos += 1 + sz[0]
                if sz[0] == 0:
                    complete = True
                    break
            if not complete:
                break
        elif t == 0x2C:
            d = src.read(pos, 10)
            if len(d) < 10:
                break
            p = d[9]
            lct_len = 0
            if p & 0x80:
                frame_bits = (p & 7) + 1
                lct_len = 3 * (1 << frame_bits)
                local = True
            elif has_gct:
                frame_bits = gct_bits
            else:
                raise Corrupt('у первого кадра нет глобальной или локальной палитры')
            interlaced = bool(p & 0x40)
            lzw = src.read(pos + 10 + lct_len, 1)
            if lzw and not 2 <= lzw[0] <= 8:
                r['problems'].append('недопустимый начальный размер кода LZW')
            found = True
            break
        elif t == 0x3B:
            break
        else:
            raise Corrupt(f'недопустимый блок 0x{t:02X}')
    if not found:
        raise Corrupt('нет данных изображения (Image Descriptor)')
    r['w'], r['h'] = w, hh
    r['depth'] = frame_bits
    r['comp'] = 'LZW'
    r['extra'].append(version)
    if has_gct or local:
        kind = 'локальная' if local else 'глобальная'
        r['extra'].append(f'палитра: {1 << frame_bits} цв. ({kind})')
    r['extra'].append(f'цветовое разрешение: {color_res} бит')
    if interlaced:
        r['extra'].append('чересстрочность (4 прохода)')
    if animated:
        r['extra'].append('анимация (NETSCAPE2.0)')
    if transparent:
        r['extra'].append('есть прозрачный цвет')
    if src.tail(1) != b'\x3b':
        r['problems'].append('нет завершающего байта 0x3B')
    return r


BMP_COMP = {0: 'нет (BI_RGB)', 1: 'RLE8', 2: 'RLE4', 3: 'Bitfields',
            4: 'JPEG', 5: 'PNG', 6: 'Alpha-bitfields'}
BMP_COMP_OS2 = {0: 'нет', 1: 'RLE8', 2: 'RLE4', 3: 'Huffman 1D', 4: 'RLE24'}
BMP_HEADERS = {12: 'CORE (OS/2)', 40: 'INFO', 52: 'V2', 56: 'V3',
               64: 'OS/2 v2', 108: 'V4', 124: 'V5'}


def parse_bmp(src, r):
    fh = need(src.read(0, 18), 18, 'обрыв заголовка BMP')
    bf_size = u32(fh, 2)
    off_bits = u32(fh, 10)
    hs = u32(fh, 14)
    if hs == 12:
        d = need(src.read(14, 12), 12, 'обрыв заголовка DIB')
        w = u16(d, 4)
        h = u16(d, 6)
        planes = u16(d, 8)
        bpp = u16(d, 10)
        comp = 0
        size_img = 0
        xp = yp = 0
        clr_used = 0
        pal_entry = 3
    elif hs >= 40:
        d = need(src.read(14, 40), 40, 'обрыв заголовка DIB')
        w = s32(d, 4)
        h = s32(d, 8)
        planes = u16(d, 12)
        bpp = u16(d, 14)
        comp = u32(d, 16)
        size_img = u32(d, 20)
        xp = s32(d, 24)
        yp = s32(d, 28)
        clr_used = u32(d, 32)
        pal_entry = 4
    else:
        raise Corrupt('недопустимый размер DIB-заголовка')
    ah = abs(h)
    if w <= 0 or ah == 0 or w > 0x7FFFFF or ah > 0x7FFFFF:
        raise Corrupt('недопустимые размеры в заголовке')
    if bpp not in (1, 4, 8, 16, 24, 32) and not (bpp == 0 and comp in (4, 5)):
        raise Corrupt('недопустимая глубина цвета в заголовке')
    if off_bits > src.size:
        raise Corrupt('смещение пикселей за пределами файла')
    if planes != 1:
        r['problems'].append('поле planes не равно 1')
    comp_table = BMP_COMP_OS2 if hs == 64 else BMP_COMP
    r['w'], r['h'] = w, ah
    r['depth'] = bpp if bpp else None
    r['comp'] = comp_table.get(comp, f'код {comp}')
    r['dpi'] = ppm_to_dpi(xp, yp)
    r['extra'].append(f'DIB-заголовок: {hs} Б ({BMP_HEADERS.get(hs, "иной")})')
    if h < 0:
        r['extra'].append('строки хранятся сверху вниз')
    colors = 0
    if 0 < bpp <= 8:
        colors = clr_used or (1 << bpp)
    elif clr_used:
        colors = clr_used
    if colors:
        r['extra'].append(f'палитра: {colors} цв. ({pal_entry} Б на запись)')
        if comp != 3 and 14 + hs + colors * pal_entry > off_bits:
            r['problems'].append('палитра не помещается до начала пикселей')
    size_bad = False
    if comp in (0, 3, 6) and bpp:
        stride = ((w * bpp + 31) // 32) * 4
        expected = off_bits + stride * ah
        if expected > src.size:
            size_bad = True
            r['problems'].append(
                f'размер файла меньше, чем указано в заголовке '
                f'({src.size} < {expected} байт)')
    elif comp in (1, 2) and size_img and off_bits + size_img > src.size:
        size_bad = True
        r['problems'].append('размер файла меньше, чем указано в заголовке')
    if not size_bad and bf_size > src.size:
        r['problems'].append(
            f'размер в BITMAPFILEHEADER ({bf_size}) больше фактического')
    return r


TIFF_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4,
                  10: 8, 11: 4, 12: 8, 13: 4, 16: 8, 17: 8, 18: 8}
TIFF_COMPRESSION = {
    1: 'нет', 2: 'CCITT RLE', 3: 'CCITT Group 3 (T.4)',
    4: 'CCITT Group 4 (T.6)', 5: 'LZW', 6: 'JPEG (старый)', 7: 'JPEG',
    8: 'Deflate', 32771: 'CCITT RLEW', 32773: 'PackBits',
    32946: 'Deflate', 34712: 'JPEG 2000', 34925: 'LZMA', 50000: 'ZSTD',
    50001: 'WebP',
}
TIFF_PHOTOMETRIC = {0: 'WhiteIsZero', 1: 'BlackIsZero', 2: 'RGB',
                    3: 'Palette', 4: 'Mask', 5: 'CMYK', 6: 'YCbCr',
                    8: 'CIELab', 9: 'ICCLab', 10: 'ITULab',
                    32803: 'CFA', 34892: 'LinearRaw'}
TIFF_PREDICTOR = {2: 'горизонтальное предсказание', 3: 'предсказание для float'}


class Tiff:
    def __init__(self, src):
        self.src = src
        h = need(src.read(0, 16), 8, 'обрыв заголовка TIFF')
        if h[:2] == b'II':
            self.le = True
        elif h[:2] == b'MM':
            self.le = False
        else:
            raise Corrupt('неверный порядок байтов в заголовке TIFF')
        magic = u16(h, 2, self.le)
        if magic == 42:
            self.big = False
            self.first = u32(h, 4, self.le)
        elif magic == 43:
            need(h, 16, 'обрыв заголовка BigTIFF')
            self.big = True
            self.first = u64(h, 8, self.le)
        else:
            raise Corrupt('неверный номер версии TIFF')
        self.inline = 8 if self.big else 4
        self.sizes = (8, 20, 8) if self.big else (2, 12, 4)

    def uint(self, b, o, n):
        return int.from_bytes(b[o:o + n], 'little' if self.le else 'big')

    def ifd(self, off):
        cs, es, ns = self.sizes
        c = need(self.src.read(off, cs), cs, 'каталог IFD за пределами файла')
        cnt = self.uint(c, 0, cs)
        if cnt == 0 or cnt > 4096:
            raise Corrupt('некорректный каталог IFD')
        total = cnt * es + ns
        raw = need(self.src.read(off + cs, total), total, 'обрыв каталога IFD')
        entries = {}
        for i in range(cnt):
            o = i * es
            tag = u16(raw, o, self.le)
            typ = u16(raw, o + 2, self.le)
            if self.big:
                count = u64(raw, o + 4, self.le)
                vf = raw[o + 12:o + 20]
            else:
                count = u32(raw, o + 4, self.le)
                vf = raw[o + 8:o + 12]
            entries[tag] = (typ, count, vf)
        return entries, self.uint(raw, cnt * es, ns)

    def next_ifd(self, off):
        cs, es, ns = self.sizes
        c = self.src.read(off, cs)
        if len(c) < cs:
            return None
        cnt = self.uint(c, 0, cs)
        nb = self.src.read(off + cs + cnt * es, ns)
        if len(nb) < ns:
            return None
        return self.uint(nb, 0, ns)

    def values(self, e, limit=262144):
        typ, count, vf = e
        sz = TIFF_TYPE_SIZE.get(typ)
        if not sz or count == 0:
            return []
        total = sz * count
        if total <= self.inline:
            data = vf[:total]
        else:
            off = self.uint(vf, 0, self.inline)
            if total > limit:
                off += total - sz
                total = sz
                count = 1
            data = self.src.read(off, total)
            if len(data) < total:
                raise Corrupt('значение тега за пределами файла')
        out = []
        le = self.le
        for i in range(count):
            o = i * sz
            if typ in (3, 8):
                out.append(u16(data, o, le))
            elif typ in (4, 9, 13):
                out.append(u32(data, o, le))
            elif typ in (16, 17, 18):
                out.append(u64(data, o, le))
            elif typ in (5, 10):
                n = u32(data, o, le)
                d = u32(data, o + 4, le)
                out.append(n / d if d else 0.0)
            elif typ in (1, 2, 6, 7):
                out.append(data[o])
            else:
                out.append(0)
        return out

    def first_value(self, entries, tag, default=None):
        e = entries.get(tag)
        if e is None:
            return default
        v = self.values(e)
        return v[0] if v else default

    def dpi(self, entries):
        xr = self.first_value(entries, 282)
        yr = self.first_value(entries, 283)
        unit = self.first_value(entries, 296, 2)
        if xr and yr and unit in (2, 3):
            k = 2.54 if unit == 3 else 1.0
            return (xr * k, yr * k)
        return None


def exif_resolution(data):
    try:
        t = Tiff(BufSrc(data))
        entries, _ = t.ifd(t.first)
        return t.dpi(entries)
    except Exception:
        return None


def parse_tiff(src, r):
    t = Tiff(src)
    ent, nxt = t.ifd(t.first)
    w = t.first_value(ent, 256)
    h = t.first_value(ent, 257)
    if not w or not h:
        raise Corrupt('в каталоге нет тегов ширины и высоты')
    bps_e = ent.get(258)
    bps = t.values(bps_e) if bps_e else [1]
    spp = t.first_value(ent, 277, 1)
    if len(bps) == 1 and spp > 1:
        depth = bps[0] * spp
    else:
        depth = sum(bps) if bps else 1
    comp = t.first_value(ent, 259, 1)
    photo = t.first_value(ent, 262)
    r['w'], r['h'] = w, h
    r['depth'] = depth
    r['comp'] = TIFF_COMPRESSION.get(comp, f'код {comp}')
    r['dpi'] = t.dpi(ent)
    r['extra'].append(('BigTIFF, ' if t.big else '') +
                      ('little-endian (II)' if t.le else 'big-endian (MM)'))
    if photo is not None:
        r['extra'].append('PhotometricInterpretation: ' +
                          TIFF_PHOTOMETRIC.get(photo, f'код {photo}'))
    if 320 in ent:
        r['extra'].append(f'палитра: {ent[320][1] // 3} цв.')
    pred = t.first_value(ent, 317)
    if pred in TIFF_PREDICTOR:
        r['extra'].append(TIFF_PREDICTOR[pred])
    extra_samples = ent.get(338)
    if extra_samples:
        r['extra'].append(f'дополнительных каналов (альфа): {extra_samples[1]}')
    if t.first_value(ent, 284, 1) == 2:
        r['extra'].append('раздельные плоскости')
    if 322 in ent:
        r['extra'].append(f'тайлы {t.first_value(ent, 322)}×'
                          f'{t.first_value(ent, 323)}')

    offs_e = ent.get(273) or ent.get(324)
    cnts_e = ent.get(279) or ent.get(325)
    if offs_e is None:
        r['problems'].append('нет данных изображения (StripOffsets/TileOffsets)')
    elif cnts_e is not None:
        offs = t.values(offs_e)
        cnts = t.values(cnts_e)
        n = min(len(offs), len(cnts))
        if n:
            end = max(offs[i] + cnts[i] for i in range(n))
            if end > src.size:
                r['problems'].append(
                    f'размер файла меньше, чем указано в заголовке '
                    f'(данные до {end} байта, в файле {src.size})')
    elif offs_e is not None:
        offs = t.values(offs_e)
        if offs and offs[0] >= src.size:
            r['problems'].append('данные изображения за концом файла')

    pages = 1
    seen = {t.first}
    cur = nxt
    while cur and cur not in seen and cur < src.size and pages < 1000:
        seen.add(cur)
        pages += 1
        cur = t.next_ifd(cur)
    if pages > 1:
        r['extra'].append(f'страниц: {pages}' + ('+' if pages >= 1000 else '') +
                          ' (показана первая)')
    return r


PCX_VERSIONS = {0: '2.5', 2: '2.8 с палитрой', 3: '2.8 без палитры',
                4: 'для Windows', 5: '3.0+'}


def parse_pcx(src, r):
    h = need(src.read(0, 128), 128, 'обрыв заголовка PCX (меньше 128 байт)')
    ver, enc, bpp = h[1], h[2], h[3]
    x0, y0, x1, y1 = u16(h, 4), u16(h, 6), u16(h, 8), u16(h, 10)
    hdpi, vdpi = u16(h, 12), u16(h, 14)
    planes = h[65]
    bpl = u16(h, 66)
    if enc not in (0, 1):
        raise Corrupt('неизвестный способ кодирования')
    if x1 < x0 or y1 < y0:
        raise Corrupt('некорректные границы изображения')
    if bpp not in (1, 2, 4, 8) or planes not in (1, 2, 3, 4):
        raise Corrupt('недопустимые параметры бит/плоскостей')
    w = x1 - x0 + 1
    hh = y1 - y0 + 1
    r['w'], r['h'] = w, hh
    r['depth'] = bpp * planes
    r['comp'] = 'RLE (PCX)' if enc == 1 else 'нет'
    if hdpi and vdpi:
        r['dpi'] = (hdpi, vdpi)
    r['extra'].append(f'версия {ver} ({PCX_VERSIONS.get(ver, "неизвестная")})')
    r['extra'].append(f'плоскостей: {planes}, {bpp} бит на плоскость')
    if bpl < (w * bpp + 7) // 8:
        r['problems'].append('BytesPerLine меньше ширины строки')
    total = bpl * planes * hh
    if enc == 1:
        min_size = 128 + ((total + 62) // 63) * 2
    else:
        min_size = 128 + total
    if src.size < min_size:
        r['problems'].append(
            f'размер файла меньше, чем нужно для заявленных размеров '
            f'({src.size} < {min_size} байт)')
    if ver == 5 and bpp == 8 and planes == 1:
        if src.size < 128 + 769:
            r['problems'].append('нет 256-цветной палитры в конце файла')
        elif src.read(src.size - 769, 1) != b'\x0c':
            r['problems'].append('нет маркера 0x0C перед палитрой')
        else:
            r['extra'].append('палитра: 256 цв. (в конце файла)')
    elif bpp * planes <= 4:
        r['extra'].append('палитра: 16 цв. (в заголовке)')
    return r


PARSERS = {'PNG': parse_png, 'JPEG': parse_jpeg, 'GIF': parse_gif,
           'BMP': parse_bmp, 'TIFF': parse_tiff, 'PCX': parse_pcx}


def detect_format(head):
    if head[:8] == PNG_SIGNATURE:
        return 'PNG'
    if head[:3] == b'\xff\xd8\xff':
        return 'JPEG'
    if head[:6] in (b'GIF87a', b'GIF89a'):
        return 'GIF'
    if head[:2] == b'BM':
        return 'BMP'
    if head[:4] in (b'II*\x00', b'MM\x00*', b'II+\x00', b'MM\x00+'):
        return 'TIFF'
    if (len(head) >= 128 and head[0] == 0x0A and head[1] in (0, 2, 3, 4, 5)
            and head[2] in (0, 1) and head[3] in (1, 2, 4, 8)):
        return 'PCX'
    return None


def format_dpi(dpi):
    if not dpi:
        return '—'
    return f'{dpi[0]:.0f}×{dpi[1]:.0f}'


def make_row(name, size='—', dpi='—', depth='—', comp='—', fmt='—',
             status='OK', extra='', error=False):
    return {'name': name, 'size': size, 'dpi': dpi, 'depth': depth,
            'compression': comp, 'format': fmt, 'status': status,
            'extra': extra, 'error': error}


def failure_row(name, fmt, res, status):
    if res is None:
        return make_row(name, fmt=fmt or '—', status=status, error=True)
    size = f"{res['w']} × {res['h']}" if res['w'] and res['h'] else '—'
    depth = res['depth'] if res['depth'] is not None else '—'
    return make_row(name, size=size, dpi=format_dpi(res['dpi']), depth=depth,
                    comp=res['comp'], fmt=fmt or '—', status=status,
                    extra='; '.join(res['extra']), error=True)


def analyze_file(path, size):
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    fmt = None
    res = None
    try:
        with open(path, 'rb', buffering=0) as f:
            src = Src(f, size)
            if not src.head:
                return make_row(name, status='Файл пуст (0 байт)', error=True)
            fmt = detect_format(src.head)
            if fmt is None:
                return make_row(
                    name,
                    status='Файл поврежден или не является изображением',
                    extra=f'сигнатура формата {ext} не найдена', error=True)
            res = new_result(fmt)
            PARSERS[fmt](src, res)
    except Corrupt as e:
        return failure_row(name, fmt, res, f'Файл поврежден: {e}')
    except OSError:
        return failure_row(name, fmt, res, 'Ошибка чтения файла')
    except Exception:
        return failure_row(name, fmt, res,
                           'Файл поврежден: ошибка разбора структуры')
    extra = list(res['extra'])
    if EXT_TO_FORMAT.get(ext) != fmt:
        extra.insert(0, f'⚠ расширение {ext}, а содержимое — {fmt}')
    problems = res['problems']
    status = 'OK' if not problems else 'Файл поврежден: ' + '; '.join(problems)
    depth = res['depth'] if res['depth'] is not None else '—'
    return make_row(name, size=f"{res['w']} × {res['h']}",
                    dpi=format_dpi(res['dpi']), depth=depth,
                    comp=res['comp'], fmt=fmt, status=status,
                    extra='; '.join(extra), error=bool(problems))


COLUMNS = ('name', 'size', 'dpi', 'depth', 'compression', 'format',
           'status', 'extra')
HEADERS = {
    'name': 'Файл',
    'size': 'Размер (px)',
    'dpi': 'DPI',
    'depth': 'Глубина цвета (бит)',
    'compression': 'Сжатие',
    'format': 'Формат',
    'status': 'Статус',
    'extra': 'Дополнительно',
}
WIDTHS = {'name': 230, 'size': 105, 'dpi': 85, 'depth': 125,
          'compression': 190, 'format': 65, 'status': 230, 'extra': 380}


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
    return (0, [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)])


class App:
    def __init__(self, root):
        self.root = root
        root.title("Лаба 2 — чтение информации из графических файлов")
        root.geometry("1350x700")
        root.minsize(700, 400)
        # Основные области окна растут вместе с окном; таблица занимает всё
        # доступное пространство, а её полосы прокрутки остаются видимыми.

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
            self.tree.column(c, width=WIDTHS[c], minwidth=60, anchor='w',
                             stretch=True)
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
        start = self.folder_var.get().strip()
        if not os.path.isdir(start):
            start = os.path.expanduser('~')
        d = filedialog.askdirectory(parent=self.root, initialdir=start,
                                    mustexist=True)
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
                                    files.append((e.path, e.stat().st_size))
                            elif recursive and e.is_dir():
                                stack.append(e.path)
                        except OSError:
                            pass
            except OSError:
                pass
        return files

    def _job(self, item):
        if self.stop_evt.is_set():
            return None
        return analyze_file(item[0], item[1])

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
            f"{elapsed:.1f} с, поврежденных/нечитаемых: {self.errors}")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
