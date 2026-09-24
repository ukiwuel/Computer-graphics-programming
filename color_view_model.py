from PyQt5.QtCore import QObject, pyqtSignal
from color_models import ColorModel

class ColorViewModel(QObject):
    colorChanged = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._model = ColorModel()

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
        return self._model