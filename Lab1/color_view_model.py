# color_view_model.py
# Слой ViewModel/Controller: берёт события от View, вызывает Model, оповещает View сигналом.
from PyQt5.QtCore import QObject, pyqtSignal
from color_models import ColorModel

class ColorViewModel(QObject):
    colorChanged = pyqtSignal()  # View перечитывает все значения после этого сигнала

    def __init__(self):
        super().__init__()
        self._model = ColorModel()

    # ---- команды от View ----
    def set_rgb(self, r, g, b):
        self._model.set_rgb(r, g, b)
        self.colorChanged.emit()

    def set_xyz(self, x, y, z):
        self._model.set_xyz(x, y, z)
        self.colorChanged.emit()

    def set_hsv(self, h, s, v):
        self._model.set_hsv(h, s, v)
        self.colorChanged.emit()

    def set_standard(self, standard):
        self._model.set_standard(standard)
        self.colorChanged.emit()

    def set_strategy(self, strategy):
        self._model.set_strategy(strategy)
        self.colorChanged.emit()

    # ---- запросы от View ----
    def get_rgb(self):
        return self._model.get_rgb()

    def get_xyz(self):
        return self._model.get_xyz()

    def get_hsv(self):
        return self._model.get_hsv()

    def is_out_of_gamut(self):
        return self._model.out_of_gamut

    @property
    def model(self):
        """Доступ к внутренней модели, когда View нужны матрицы (для градиентов XYZ)."""
        return self._model