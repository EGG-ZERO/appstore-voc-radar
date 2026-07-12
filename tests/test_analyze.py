"""统计与分类逻辑自测：python tests/test_analyze.py"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analyze import classify, two_prop_ztest, check_alerts  # noqa: E402


class TestClassify(unittest.TestCase):
    def test_single_hit(self):
        self.assertIn("闪退卡顿", classify("一打开就闪退，根本用不了"))

    def test_multi_label(self):
        cats = classify("支付完闪退了，钱扣了订单没了")
        self.assertIn("支付下单", cats)
        self.assertIn("闪退卡顿", cats)

    def test_fallback_other(self):
        self.assertEqual(classify("非常一般般"), ["其他"])


class TestZTest(unittest.TestCase):
    def test_known_value(self):
        # p1=10% vs p2=15%, n=1000/1000 -> z约-3.38, p约0.0007
        z, p = two_prop_ztest(100, 1000, 150, 1000)
        self.assertAlmostEqual(z, -3.38, delta=0.02)
        self.assertLess(p, 0.001)

    def test_no_diff(self):
        z, p = two_prop_ztest(50, 500, 50, 500)
        self.assertAlmostEqual(z, 0.0, delta=1e-9)
        self.assertAlmostEqual(p, 1.0, delta=1e-9)

    def test_degenerate_all_negative(self):
        self.assertIsNone(two_prop_ztest(10, 10, 20, 20))

    def test_degenerate_empty(self):
        self.assertIsNone(two_prop_ztest(0, 0, 5, 10))


class TestAlerts(unittest.TestCase):
    @staticmethod
    def _stats(win_n, win_neg, base_rate=0.1):
        """基线：窗口前84天每天1条（负面按base_rate间隔），窗口：最近7天集中win_n条。"""
        from datetime import datetime, timedelta
        end = datetime(2026, 7, 12)
        daily = {}
        for i in range(7, 7 + 84):     # 基线84天
            d = (end - timedelta(days=i)).strftime("%Y-%m-%d")
            neg = 1 if i % round(1 / base_rate) == 0 else 0
            daily[d] = {"a1": {"n": 1, "neg": neg, "rating_sum": 4}}
        # 窗口7天：全堆在最后一天，检验的是合并样本
        daily[end.strftime("%Y-%m-%d")] = {
            "a1": {"n": win_n, "neg": win_neg, "rating_sum": 10}}
        return {"apps": {"a1": "测试App"}, "daily": daily}

    def test_spike_triggers(self):
        # 基线约10%，窗口20条14负面=70%，远超UCL，必须报警
        alerts = check_alerts(self._stats(20, 14))
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["app"], "测试App")

    def test_normal_window_silent(self):
        alerts = check_alerts(self._stats(20, 3))   # 15%，在3σ内
        self.assertEqual(alerts, [])

    def test_small_sample_guard(self):
        # 窗口只有3条全负面，样本不足不报警
        alerts = check_alerts(self._stats(3, 3))
        self.assertEqual(alerts, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
