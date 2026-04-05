"""EMT 正/反演一致性简单测试。"""
from __future__ import annotations

import unittest

from grin import emt


class TestEMT(unittest.TestCase):
    def test_mg_endpoints(self):
        em, ei = 2.8, 1.0
        e0 = emt.epsilon_eff_maxwell_garnett(em, ei, 0.0)
        e1 = emt.epsilon_eff_maxwell_garnett(em, ei, 1.0)
        self.assertAlmostEqual(e0, em, places=5)
        self.assertAlmostEqual(e1, ei, places=5)

    def test_roundtrip(self):
        em, ei = 2.8, 1.0
        for vf in (0.1, 0.35, 0.72, 0.95):
            eps = emt.epsilon_eff_from_solid_vf(em, ei, vf)
            vf2 = emt.invert_vf_solid_for_epsilon(eps, em, ei, tol=1e-5)
            self.assertAlmostEqual(vf, vf2, places=4)


if __name__ == "__main__":
    unittest.main()
