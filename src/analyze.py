"""评论分析：去重累积、投诉分类、日统计、p控制图预警、版本回归检验。

输入：data/raw/最新快照 + data/reviews.csv（历史累积）
产出：data/reviews.csv（按review_id覆盖合并）、data/daily_stats.json

统计口径：
- 负面 = 1-2星
- 预警：p控制图，基线=该App近28天负面率均值，UCL = p̄+3σ，当日n>=5且负面>=3才触发
- 版本回归：新旧版本各>=20条评论，两比例z检验（双侧）

用法：python src/analyze.py（先跑fetch_reviews.py）
"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
REVIEWS_CSV = PROJECT_ROOT / "data" / "reviews.csv"
STATS_JSON = PROJECT_ROOT / "data" / "daily_stats.json"

NEG_MAX_RATING = 2          # 1-2星记为负面
# 文字评论量级小（个位数/周），预警用近7天合并样本对前84天基线，不做日粒度
ALERT_WINDOW_DAYS = 7
ALERT_MIN_N = 5             # 窗口样本下限
ALERT_MIN_NEG = 3           # 窗口负面数下限
BASELINE_DAYS = 84
BASELINE_MIN_N = 30
VERSION_MIN_N = 20          # 版本检验的每版样本下限

# 投诉类别词典：子串匹配（中文无需词边界），多标签，负面评论无命中则归「其他」
CATEGORIES: dict[str, list[str]] = {
    "闪退卡顿": ["闪退", "崩溃", "卡顿", "卡死", "打不开", "黑屏", "白屏", "加载不出",
                 "太卡", "很卡", "卡的", "闪一下"],
    "登录账号": ["登录", "登陆", "验证码", "注册", "账号", "封号", "注销"],
    "支付下单": ["支付", "付款", "付不了", "下单", "订单", "扣款", "扣了", "退款",
                 "退钱", "充值", "余额"],
    "优惠与价格": ["优惠券", "领券", "优惠", "涨价", "价格", "太贵", "变贵", "虚假",
                   "套路", "诱导", "杀熟"],
    "配送履约": ["配送", "外卖", "骑手", "送达", "超时", "送错", "洒了", "漏了"],
    "门店与出品": ["门店", "店员", "做错", "口感", "难喝", "味道", "品质", "分量"],
    "客服售后": ["客服", "投诉", "不处理", "没人处理", "敷衍", "推诿", "申诉"],
    "广告推送": ["广告", "弹窗", "推送", "骚扰", "短信"],
    "会员与隐私": ["自动续费", "会员", "隐私", "权限", "个人信息"],
}

CSV_FIELDS = ["review_id", "app_id", "app_name", "date", "rating", "version",
              "cats", "title", "content"]


def classify(text: str) -> list[str]:
    hits = [cat for cat, kws in CATEGORIES.items() if any(k in text for k in kws)]
    return hits or ["其他"]


def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


def two_prop_ztest(neg1: int, n1: int, neg2: int, n2: int) -> tuple[float, float] | None:
    """组1 vs 组2 负面率两比例z检验。返回(z, 双侧p)，退化场景返回None。"""
    if n1 == 0 or n2 == 0:
        return None
    p_pool = (neg1 + neg2) / (n1 + n2)
    if p_pool <= 0 or p_pool >= 1:
        return None
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (neg1 / n1 - neg2 / n2) / se
    p = 2 * (1 - norm_cdf(abs(z)))
    return z, p


def load_existing() -> dict[str, dict]:
    if not REVIEWS_CSV.exists():
        return {}
    with open(REVIEWS_CSV, encoding="utf-8-sig", newline="") as f:
        return {r["review_id"]: r for r in csv.DictReader(f)}


def merge_snapshot(rows: dict[str, dict]) -> tuple[dict[str, dict], int, list[dict]]:
    snaps = sorted(RAW_DIR.glob("*.json"))
    if not snaps:
        raise SystemExit("data/raw/ 为空，先跑 fetch_reviews.py")
    snap = json.loads(snaps[-1].read_text(encoding="utf-8"))
    new_count = 0
    for app_id, blob in snap["apps"].items():
        for r in blob["reviews"]:
            text = f"{r['title']} {r['content']}"
            row = {
                "review_id": r["review_id"],
                "app_id": app_id,
                "app_name": blob["name"],
                "date": r["date"],
                "rating": str(r["rating"]),
                "version": r["version"],
                "cats": "|".join(classify(text)) if r["rating"] <= NEG_MAX_RATING else "",
                "title": r["title"].replace("\n", " ").strip(),
                "content": r["content"].replace("\n", " ").strip(),
            }
            if r["review_id"] not in rows:
                new_count += 1
            rows[r["review_id"]] = row     # 评论可被作者修改，按最新覆盖
    return rows, new_count, snap.get("failed_apps", [])


def build_stats(rows: dict[str, dict]) -> dict:
    apps: dict[str, str] = {}
    daily: dict[str, dict[str, dict]] = {}
    cats_by_app: dict[str, dict[str, int]] = {}

    for r in rows.values():
        apps[r["app_id"]] = r["app_name"]
        d = daily.setdefault(r["date"], {}).setdefault(
            r["app_id"], {"n": 0, "neg": 0, "rating_sum": 0})
        d["n"] += 1
        d["rating_sum"] += int(r["rating"])
        if int(r["rating"]) <= NEG_MAX_RATING:
            d["neg"] += 1
            for c in r["cats"].split("|"):
                cats_by_app.setdefault(r["app_name"], {})[c] = \
                    cats_by_app.setdefault(r["app_name"], {}).get(c, 0) + 1

    return {"apps": apps, "daily": daily, "cats_by_app": cats_by_app}


def check_alerts(stats: dict) -> list[dict]:
    """p控制图预警：近7天合并样本 vs 前84天基线，锚定全局最新日期。

    锚定全局最新日期而非单App最后活跃日期，避免长期沉默的App
    拿几个月前的旧数据当「当前窗口」误报。
    """
    from datetime import datetime, timedelta

    alerts = []
    dates = sorted(stats["daily"].keys())
    if not dates:
        return alerts
    end = datetime.strptime(dates[-1], "%Y-%m-%d")
    win_start = (end - timedelta(days=ALERT_WINDOW_DAYS - 1)).strftime("%Y-%m-%d")
    base_start = (end - timedelta(days=ALERT_WINDOW_DAYS + BASELINE_DAYS - 1)).strftime("%Y-%m-%d")

    for app_id, name in stats["apps"].items():
        win_n = win_neg = base_n = base_neg = 0
        for d in dates:
            if d < base_start:
                continue
            day = stats["daily"][d].get(app_id)
            if not day:
                continue
            if d >= win_start:
                win_n += day["n"]; win_neg += day["neg"]
            else:
                base_n += day["n"]; base_neg += day["neg"]
        if win_n < ALERT_MIN_N or win_neg < ALERT_MIN_NEG or base_n < BASELINE_MIN_N:
            continue
        p_bar = base_neg / base_n
        if p_bar <= 0 or p_bar >= 1:
            continue
        ucl = p_bar + 3 * math.sqrt(p_bar * (1 - p_bar) / win_n)
        rate = win_neg / win_n
        if rate > ucl:
            alerts.append({
                "window": f"{win_start} ~ {dates[-1]}", "app": name,
                "neg_rate": round(rate, 4), "baseline": round(p_bar, 4),
                "ucl": round(ucl, 4), "n": win_n, "neg": win_neg,
            })
    return alerts


def enrich_alerts(alerts: list[dict], rows: dict[str, dict]) -> list[dict]:
    """给预警补充窗口内负面评论的Top3投诉类别（异动归因）。"""
    for a in alerts:
        start, end = a["window"].split(" ~ ")
        counts: dict[str, int] = {}
        for r in rows.values():
            if (r["app_name"] == a["app"] and start <= r["date"] <= end
                    and int(r["rating"]) <= NEG_MAX_RATING):
                for c in r["cats"].split("|"):
                    counts[c] = counts.get(c, 0) + 1
        a["top_cats"] = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
    return alerts


def version_tests(rows: dict[str, dict]) -> list[dict]:
    """每App取评论量达标的最新两个版本做负面率回归检验。"""
    by_app: dict[str, dict[str, list[dict]]] = {}
    for r in rows.values():
        by_app.setdefault(r["app_name"], {}).setdefault(r["version"], []).append(r)

    results = []
    for app, versions in by_app.items():
        qualified = {v: rs for v, rs in versions.items() if len(rs) >= VERSION_MIN_N}
        if len(qualified) < 2:
            continue
        # 版本按首条评论日期排序，取最新两个
        ordered = sorted(qualified, key=lambda v: min(r["date"] for r in qualified[v]))
        new_v, old_v = ordered[-1], ordered[-2]
        neg = lambda rs: sum(1 for r in rs if int(r["rating"]) <= NEG_MAX_RATING)  # noqa: E731
        n_new, neg_new = len(qualified[new_v]), neg(qualified[new_v])
        n_old, neg_old = len(qualified[old_v]), neg(qualified[old_v])
        t = two_prop_ztest(neg_new, n_new, neg_old, n_old)
        if t is None:
            continue
        z, p = t
        results.append({
            "app": app, "new_version": new_v, "old_version": old_v,
            "n_new": n_new, "neg_rate_new": round(neg_new / n_new, 4),
            "n_old": n_old, "neg_rate_old": round(neg_old / n_old, 4),
            "z": round(z, 2), "p": round(p, 4), "significant": p < 0.05,
        })
    return results


def main() -> None:
    rows = load_existing()
    rows, new_count, failed = merge_snapshot(rows)

    ordered = sorted(rows.values(), key=lambda r: (r["date"], r["app_id"]))
    REVIEWS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEWS_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(ordered)

    stats = build_stats(rows)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "new_today": new_count,
        "total_reviews": len(rows),
        "failed_apps": failed,
        **stats,
        "alerts": enrich_alerts(check_alerts(stats), rows),
        "version_tests": version_tests(rows),
    }
    STATS_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"累计{len(rows)}条（新增{new_count}），预警{len(out['alerts'])}个，"
          f"版本检验{len(out['version_tests'])}组 -> {STATS_JSON}")


if __name__ == "__main__":
    main()
