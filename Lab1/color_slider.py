# color_slider.py
# Слой View: слайдер с динамическим градиентом под ним.
# Градиент строится через переданную функцию color_at(value) -> QColor,
# что позволяет использовать один и тот же виджет для RGB, XYZ, HSV, LAB, CMYK.
from PyQt5.QtWidgets import QWidget, QSlider, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QPainter, QLinearGradient

class GradientSlider(QWidget):
    def __init__(self, minimum=0, maximum=255, color_at=None, samples=12, parent=None):
        super().__init__(parent)
        self._color_at = color_at  # callable(value:int) -> QColor
        self._samples = samples

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(minimum, maximum)

        self.gradient_label = QLabel()
        self.gradient_label.setFixedHeight(12)
        self.gradient_label.setMinimumWidth(100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.gradient_label)
        layout.addWidget(self.slider)

    def set_color_at(self, fn):
        """Обновить функцию расчёта цвета вдоль трека (например, когда изменились другие каналы)."""
        self._color_at = fn
        self.update_gradient()

    def update_gradient(self):
        if self._color_at is None or self.gradient_label.width() <= 0:
            return
        w, h = self.gradient_label.width(), self.gradient_label.height()
        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        grad = QLinearGradient(0, 0, w, 0)
        lo, hi = self.slider.minimum(), self.slider.maximum()
        n = max(2, self._samples)
        for i in range(n):
            frac = i / (n - 1)
            val = lo + frac * (hi - lo)
            try:
                color = self._color_at(val)
            except Exception:
                color = None
            if color is not None:
                grad.setColorAt(frac, color)
        painter.fillRect(pixmap.rect(), grad)
        painter.end()
        self.gradient_label.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_gradient()

    def value(self):
        return self.slider.value()

    def setValue(self, val):
        self.slider.setValue(int(val))

    def minimum(self):
        return self.slider.minimum()

    def maximum(self):
        return self.slider.maximum()

    @property
    def valueChanged(self):
        return self.slider.valueChanged


# Оставлен для обратной совместимости под старым именем, используемым ранее для RGB-слайдеров.
ColorSlider = GradientSlider