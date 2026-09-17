# main_window.py
# Слой View: только виджеты и их расположение. Вся логика идёт через ColorViewModel.
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QGroupBox, QLabel, QLineEdit, QComboBox,
                              QFrame, QPushButton, QColorDialog, QMessageBox)
from PyQt5.QtGui import QColor, QPalette

from color_view_model import ColorViewModel
from color_slider import GradientSlider
from color_models import hsv_to_rgb, xyz_to_rgb

MODEL_LABELS = {
    'RGB': ['R', 'G', 'B'],
    'XYZ': ['X', 'Y', 'Z'],
    'HSV': ['H', 'S', 'V'],
}
CHANNEL_RANGES = {
    ('RGB', 'R'): (0, 255), ('RGB', 'G'): (0, 255), ('RGB', 'B'): (0, 255),
    ('XYZ', 'X'): (0, 200), ('XYZ', 'Y'): (0, 200), ('XYZ', 'Z'): (0, 200),
    ('HSV', 'H'): (0, 360), ('HSV', 'S'): (0, 100), ('HSV', 'V'): (0, 100),
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Лабораторная работа 1 - Вариант 8 (RGB↔XYZ↔HSV)")
        self.setGeometry(100, 100, 900, 700)

        self.vm = ColorViewModel()
        self._updating_view = False

        self.sliders = {}
        self.inputs = {}

        self._init_ui()
        self._connect_signals()
        self.vm.colorChanged.connect(self._refresh_view)
        self._refresh_view()

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        top = QHBoxLayout()
        top.addWidget(QLabel("Стандарт освещения:"))
        self.std_combo = QComboBox()
        self.std_combo.addItems(['D65', 'D50', 'E'])
        top.addWidget(self.std_combo)

        top.addSpacing(20)
        top.addWidget(QLabel("Стратегия выхода:"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(['clip', 'scale'])
        top.addWidget(self.strategy_combo)

        top.addStretch()
        self.pick_btn = QPushButton("Выбрать цвет из палитры")
        top.addWidget(self.pick_btn)

        self.info_btn = QPushButton("ℹ Информация")
        top.addWidget(self.info_btn)
        main_layout.addLayout(top)

        self.color_sample = QFrame()
        self.color_sample.setFixedHeight(700)
        self.color_sample.setFrameShape(QFrame.Box)
        self.color_sample.setAutoFillBackground(True)
        main_layout.addWidget(self.color_sample)

        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: #b35c00;")
        main_layout.addWidget(self.warning_label)

        models_layout = QHBoxLayout()
        for model in ('RGB', 'XYZ', 'HSV'):
            models_layout.addWidget(self._create_model_group(model))
        main_layout.addLayout(models_layout)

    def _create_model_group(self, model):
        group = QGroupBox(model)
        layout = QVBoxLayout(group)

        for label in MODEL_LABELS[model]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label + ":"))
            lo, hi = CHANNEL_RANGES[(model, label)]
            slider = GradientSlider(minimum=lo, maximum=hi, color_at=None)
            row.addWidget(slider)

            inp = QLineEdit()
            inp.setFixedWidth(70)
            inp.setText("0")
            row.addWidget(inp)

            layout.addLayout(row)
            key = (model, label)
            self.sliders[key] = slider
            self.inputs[key] = inp

        # третий способ задания цвета для каждой модели: своя кнопка выбора из палитры
        pick_row = QHBoxLayout()
        pick_row.addStretch()
        btn = QPushButton("Из палитры…")
        btn.clicked.connect(self._pick_color)
        pick_row.addWidget(btn)
        layout.addLayout(pick_row)

        return group

    # ------------------------------------------------------------- signals
    def _connect_signals(self):
        for model, labels in MODEL_LABELS.items():
            for idx, label in enumerate(labels):
                key = (model, label)
                slider = self.sliders[key]
                inp = self.inputs[key]
                slider.valueChanged.connect(lambda val, m=model, i=idx: self._on_slider(m, i))
                inp.returnPressed.connect(lambda m=model, i=idx: self._on_input(m, i))

        self.std_combo.currentTextChanged.connect(self.vm.set_standard)
        self.strategy_combo.currentTextChanged.connect(self.vm.set_strategy)
        self.pick_btn.clicked.connect(self._pick_color)
        self.info_btn.clicked.connect(self._show_info)

    # --------------------------------------------------------- ui -> model
    def _read_channels(self, model):
        labels = MODEL_LABELS[model]
        raw = [self.sliders[(model, l)].value() for l in labels]
        if model == 'RGB':
            return [v / 255.0 for v in raw]
        if model == 'XYZ':
            return [v / 100.0 for v in raw]
        if model == 'HSV':
            h, s, v = raw
            return [h, s / 100.0, v / 100.0]

    def _push_to_model(self, model, channels):
        if model == 'RGB':
            self.vm.set_rgb(*channels)
        elif model == 'XYZ':
            self.vm.set_xyz(*channels)
        elif model == 'HSV':
            self.vm.set_hsv(*channels)

    def _on_slider(self, model, idx):
        if self._updating_view:
            return
        self._push_to_model(model, self._read_channels(model))

    def _on_input(self, model, idx):
        if self._updating_view:
            return
        labels = MODEL_LABELS[model]
        try:
            text_val = float(self.inputs[(model, labels[idx])].text())
        except ValueError:
            return
        channels = self._read_channels(model)
        if model == 'RGB':
            channels[idx] = text_val / 255.0
        elif model == 'XYZ':
            channels[idx] = text_val / 100.0
        elif model == 'HSV':
            channels[idx] = text_val if idx == 0 else text_val / 100.0
        self._push_to_model(model, channels)

    def _pick_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.vm.set_rgb(color.redF(), color.greenF(), color.blueF())

    def _show_info(self):
        text = (
            "<h3>Лабораторная работа 1 — Цветовые модели (Вариант 8)</h3>"
            "<p>Приложение конвертирует цвет между тремя моделями "
            "<b>RGB</b>, <b>XYZ</b> и <b>HSV</b>. Все формулы перевода рассчитаны вручную, "
            "без сторонних библиотек цветовой конвертации.</p>"
            "<h4>Как задать цвет</h4>"
            "<ul>"
            "<li><b>Ползунок</b> — плавно двигайте компоненту нужной модели.</li>"
            "<li><b>Поле ввода</b> — впишите точное число и нажмите Enter.</li>"
            "<li><b>Палитра</b> — кнопка «Из палитры…» в каждой группе или общая кнопка сверху "
            "открывает стандартный диалог выбора цвета Windows/Qt.</li>"
            "</ul>"
            "<p>При изменении значения в любой модели два других представления "
            "пересчитываются автоматически.</p>"
            "<h4>Стандарт освещения</h4>"
            "<p>D65 (дневной свет, sRGB), D50 (полиграфия) или E (равноэнергетический источник) — "
            "матрица перехода RGB↔XYZ пересчитывается на лету методом адаптации Брэдфорда. "
            "Смена стандарта не меняет текущий RGB-цвет, а меняет то, какими координатами XYZ "
            "он описывается.</p>"
            "<h4>Стратегия выхода за диапазон</h4>"
            "<p><b>Clip</b> — значение просто обрезается до границ [0, 1] (или [0, 255]).<br>"
            "<b>Scale</b> — весь диапазон пропорционально сжимается, чтобы уместить цвет "
            "в допустимые границы.</p>"
            "<p>Если при переводе (например, из XYZ в RGB) координата вышла за допустимый диапазон, "
            "под образцом цвета появляется предупреждение о том, что применена коррекция.</p>"
        )
        QMessageBox.information(self, "Информация о лабораторной работе", text)

    # --------------------------------------------------------- model -> ui
    def _refresh_view(self):
        self._updating_view = True

        r, g, b = self.vm.get_rgb()
        x, y, z = self.vm.get_xyz()
        h, s, v = self.vm.get_hsv()

        self._set_channel('RGB', 'R', r * 255)
        self._set_channel('RGB', 'G', g * 255)
        self._set_channel('RGB', 'B', b * 255)

        self._set_channel('XYZ', 'X', x * 100, fmt=f"{x:.3f}")
        self._set_channel('XYZ', 'Y', y * 100, fmt=f"{y:.3f}")
        self._set_channel('XYZ', 'Z', z * 100, fmt=f"{z:.3f}")

        self._set_channel('HSV', 'H', h, fmt=f"{h:.0f}")
        self._set_channel('HSV', 'S', s * 100, fmt=f"{s:.2f}")
        self._set_channel('HSV', 'V', v * 100, fmt=f"{v:.2f}")

        self._update_all_gradients(r, g, b, h, s, v)

        qcolor = QColor.fromRgbF(*self._clamped(r, g, b))
        pal = self.color_sample.palette()
        pal.setColor(QPalette.Window, qcolor)
        self.color_sample.setPalette(pal)

        if self.vm.is_out_of_gamut():
            self.warning_label.setText(
                "⚠ Цвет вне диапазона модели — применена коррекция (%s)." % self.strategy_combo.currentText()
            )
        else:
            self.warning_label.setText("")

        self._updating_view = False

    @staticmethod
    def _clamped(r, g, b):
        return max(0.0, min(1.0, r)), max(0.0, min(1.0, g)), max(0.0, min(1.0, b))

    def _set_channel(self, model, label, raw_value, fmt=None):
        key = (model, label)
        slider = self.sliders[key]
        slider.setValue(raw_value)
        self.inputs[key].setText(fmt if fmt is not None else str(int(round(raw_value))))

    # -------------------------------------------------- динамические градиенты
    def _update_all_gradients(self, r, g, b, h, s, v):
        # RGB: под каждым слайдером — как изменится цвет при сдвиге именно этого канала
        self.sliders[('RGB', 'R')].set_color_at(lambda val: QColor.fromRgbF(*self._clamped(val / 255.0, g, b)))
        self.sliders[('RGB', 'G')].set_color_at(lambda val: QColor.fromRgbF(*self._clamped(r, val / 255.0, b)))
        self.sliders[('RGB', 'B')].set_color_at(lambda val: QColor.fromRgbF(*self._clamped(r, g, val / 255.0)))

        # HSV
        self.sliders[('HSV', 'H')].set_color_at(lambda val: QColor.fromRgbF(*self._clamped(*hsv_to_rgb(val, s, v))))
        self.sliders[('HSV', 'S')].set_color_at(lambda val: QColor.fromRgbF(*self._clamped(*hsv_to_rgb(h, val / 100.0, v))))
        self.sliders[('HSV', 'V')].set_color_at(lambda val: QColor.fromRgbF(*self._clamped(*hsv_to_rgb(h, s, val / 100.0))))

        # XYZ: используем текущую обратную матрицу модели (зависит от выбранного стандарта)
        Minv = self.vm.model._Minv
        xv, yv, zv = self.vm.get_xyz()
        self.sliders[('XYZ', 'X')].set_color_at(lambda val: QColor.fromRgbF(*self._clamped(*xyz_to_rgb(val / 100.0, yv, zv, Minv))))
        self.sliders[('XYZ', 'Y')].set_color_at(lambda val: QColor.fromRgbF(*self._clamped(*xyz_to_rgb(xv, val / 100.0, zv, Minv))))
        self.sliders[('XYZ', 'Z')].set_color_at(lambda val: QColor.fromRgbF(*self._clamped(*xyz_to_rgb(xv, yv, val / 100.0, Minv))))