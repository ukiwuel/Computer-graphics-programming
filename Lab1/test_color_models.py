# test_color_models.py
import unittest
from color_models import (rgb_to_xyz, xyz_to_rgb, rgb_to_hsv, hsv_to_rgb,
                           get_matrices_for_standard, clamp_rgb, scale_rgb,
                           ColorModel)


class TestRgbHsv(unittest.TestCase):
    def test_rgb_to_hsv_red(self):
        H, S, V = rgb_to_hsv(1.0, 0.0, 0.0)
        self.assertAlmostEqual(H, 0.0)
        self.assertAlmostEqual(S, 1.0)
        self.assertAlmostEqual(V, 1.0)

    def test_hsv_to_rgb_red(self):
        r, g, b = hsv_to_rgb(0.0, 1.0, 1.0)
        self.assertAlmostEqual(r, 1.0)
        self.assertAlmostEqual(g, 0.0)
        self.assertAlmostEqual(b, 0.0)

    def test_hsv_roundtrip(self):
        r, g, b = 0.2, 0.7, 0.4
        H, S, V = rgb_to_hsv(r, g, b)
        r2, g2, b2 = hsv_to_rgb(H, S, V)
        self.assertAlmostEqual(r, r2, places=5)
        self.assertAlmostEqual(g, g2, places=5)
        self.assertAlmostEqual(b, b2, places=5)


class TestXyz(unittest.TestCase):
    def test_rgb_xyz_roundtrip(self):
        M, Minv, _ = get_matrices_for_standard('D65')
        r, g, b = 0.5, 0.3, 0.8
        x, y, z = rgb_to_xyz(r, g, b, M)
        r2, g2, b2 = xyz_to_rgb(x, y, z, Minv)
        self.assertAlmostEqual(r, r2, places=5)
        self.assertAlmostEqual(g, g2, places=5)
        self.assertAlmostEqual(b, b2, places=5)

    def test_matrices_differ_by_standard(self):
        M65, _, _ = get_matrices_for_standard('D65')
        M50, _, _ = get_matrices_for_standard('D50')
        self.assertNotAlmostEqual(M65[0][0], M50[0][0], places=4)

    def test_white_reference_maps_to_white_xyz(self):
        # RGB(1,1,1) в стандарте D65 должен давать XYZ = белая точка D65
        M, _, white = get_matrices_for_standard('D65')
        x, y, z = rgb_to_xyz(1.0, 1.0, 1.0, M)
        self.assertAlmostEqual(x, white[0], places=3)
        self.assertAlmostEqual(y, white[1], places=3)
        self.assertAlmostEqual(z, white[2], places=3)


class TestStrategies(unittest.TestCase):
    def test_clipping(self):
        (cr, cg, cb), out = clamp_rgb(1.2, -0.1, 0.5)
        self.assertAlmostEqual(cr, 1.0)
        self.assertAlmostEqual(cg, 0.0)
        self.assertAlmostEqual(cb, 0.5)
        self.assertTrue(out)

    def test_clipping_in_range_no_warning(self):
        (cr, cg, cb), out = clamp_rgb(0.2, 0.4, 0.5)
        self.assertFalse(out)

    def test_scaling(self):
        (sr, sg, sb), out = scale_rgb(1.2, -0.1, 0.5)
        self.assertAlmostEqual(sr, 1.0)
        self.assertAlmostEqual(sg, 0.0)
        self.assertAlmostEqual(sb, 0.6 / 1.3, places=5)
        self.assertTrue(out)


class TestColorModel(unittest.TestCase):
    def test_model_red(self):
        model = ColorModel()
        model.set_rgb(1.0, 0.0, 0.0)
        h, s, v = model.get_hsv()
        self.assertAlmostEqual(h, 0.0)
        self.assertAlmostEqual(s, 1.0)
        self.assertAlmostEqual(v, 1.0)

    def test_model_out_of_gamut_flag(self):
        model = ColorModel()
        model.set_strategy('clip')
        model.set_xyz(1.5, 0.1, 0.1)  # заведомо даёт RGB вне [0,1]
        self.assertTrue(model.out_of_gamut)

    def test_model_in_gamut_no_flag(self):
        model = ColorModel()
        model.set_rgb(0.5, 0.5, 0.5)
        self.assertFalse(model.out_of_gamut)

    def test_model_standard_switch_changes_xyz(self):
        model = ColorModel()
        model.set_rgb(0.5, 0.2, 0.7)
        model.set_standard('D65')
        xyz_d65 = model.get_xyz()
        model.set_standard('D50')
        xyz_d50 = model.get_xyz()
        self.assertNotAlmostEqual(xyz_d65[0], xyz_d50[0], places=3)


if __name__ == '__main__':
    unittest.main()