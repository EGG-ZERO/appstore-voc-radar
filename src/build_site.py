"""渲染静态看板页（ECharts暗色主题）-> docs/index.html

数据源：data/daily_stats.json
用法：python src/build_site.py（先跑analyze.py）
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATS_JSON = PROJECT_ROOT / "data" / "daily_stats.json"
OUT = PROJECT_ROOT / "docs" / "index.html"

REPO_URL = "https://github.com/EGG-ZERO/appstore-voc-radar"
# 文字评论量级为个位数/周，日粒度不成立：28天滚动、每周取点、约18个月窗口
ROLL_DAYS = 28
SAMPLE_STEP = 7
SAMPLES = 78
ROLL_MIN_N = 8          # 滚动窗口样本下限，低于则断点


def rolling_series(stats: dict) -> dict:
    """28天滚动负面率与平均分，每周采样一个点，样本不足断点(null)。"""
    daily = stats["daily"]
    all_dates = sorted(daily.keys())
    end = datetime.strptime(all_dates[-1], "%Y-%m-%d")
    sample_dates = [end - timedelta(days=i * SAMPLE_STEP)
                    for i in range(SAMPLES - 1, -1, -1)]

    neg_series, rating_series = {}, {}
    for app_id, name in stats["apps"].items():
        neg_pts, rating_pts = [], []
        for cur in sample_dates:
            n = neg = rsum = 0
            for k in range(ROLL_DAYS):
                key = (cur - timedelta(days=k)).strftime("%Y-%m-%d")
                day = daily.get(key, {}).get(app_id)
                if day:
                    n += day["n"]; neg += day["neg"]; rsum += day["rating_sum"]
            if n >= ROLL_MIN_N:
                neg_pts.append(round(neg / n * 100, 1))
                rating_pts.append(round(rsum / n, 2))
            else:
                neg_pts.append(None)
                rating_pts.append(None)
        neg_series[name] = neg_pts
        rating_series[name] = rating_pts
    return {"dates": [d.strftime("%Y-%m-%d") for d in sample_dates],
            "neg": neg_series, "rating": rating_series}


def build_payload() -> dict:
    stats = json.loads(STATS_JSON.read_text(encoding="utf-8"))
    trend = rolling_series(stats)

    cat_totals: dict[str, int] = {}
    for cats in stats["cats_by_app"].values():
        for c, n in cats.items():
            cat_totals[c] = cat_totals.get(c, 0) + n
    # 按总量降序，「其他」固定末位
    cat_names = sorted([c for c in cat_totals if c != "其他"],
                       key=lambda c: -cat_totals[c])
    if "其他" in cat_totals:
        cat_names.append("其他")
    apps = list(stats["apps"].values())
    cat_matrix = {a: [stats["cats_by_app"].get(a, {}).get(c, 0) for c in cat_names]
                  for a in apps}

    sig = sum(1 for t in stats["version_tests"] if t["significant"])
    return {
        "updated": stats["generated_at"][:16].replace("T", " ") + " UTC",
        "kpis": {
            "total": stats["total_reviews"],
            "new_today": stats["new_today"],
            "alerts": len(stats["alerts"]),
            "apps": len(stats["apps"]),
            "sig": f"{sig}/{len(stats['version_tests'])}",
        },
        "alerts": stats["alerts"],
        "trend": trend,
        "cats": {"names": cat_names, "apps": apps, "matrix": cat_matrix},
        "versions": stats["version_tests"],
        "failed": [f["name"] for f in stats.get("failed_apps", [])],
    }


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>竞品用户反馈监测雷达 · 咖啡茶饮类目</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
:root{
  --bg-primary:#0E131D; --bg-secondary:#161D2B; --bg-tertiary:#0B0F17;
  --text-primary:#E8EDF5; --text-secondary:#9AA6B8; --text-muted:#5F6B7D;
  --border:#232D3F; --accent:#4C8DFF;
  --danger:#E5604C; --success:#3FB27F; --warning:#E0A63C;
  --radius:12px;
}
*{margin:0;box-sizing:border-box}
body{background:var(--bg-primary);color:var(--text-primary);
  font:14px/1.6 "Microsoft YaHei",system-ui,sans-serif;padding:32px 24px 48px}
.wrap{max-width:1160px;margin:0 auto}
h1{font-size:24px;font-weight:700}
.sub{color:var(--text-secondary);font-size:13px;margin:6px 0 24px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:16px}
.kpi{background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius);padding:16px 18px}
.kpi .label{color:var(--text-muted);font-size:12px}
.kpi .value{font-size:30px;font-weight:700;margin-top:2px}
.kpi .value.warn{color:var(--danger)}
.alertbar{border-radius:var(--radius);padding:14px 18px;margin-bottom:24px;font-size:13px}
.alertbar.ok{background:var(--bg-secondary);border:1px solid var(--border);color:var(--text-secondary)}
.alertbar.bad{background:rgba(229,96,76,.12);border:1px solid var(--danger)}
.alertbar.bad b{color:var(--danger)}
.card{background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius);
  padding:20px;margin-bottom:20px}
.card h2{font-size:16px;font-weight:600;margin-bottom:4px}
.card .note{color:var(--text-muted);font-size:12px;margin-bottom:12px}
.chart{width:100%;height:320px}
#catChart{height:380px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{color:var(--text-secondary);font-weight:600;text-align:left;padding:8px 10px;border-bottom:1px solid var(--border)}
td{padding:9px 10px;border-bottom:1px solid var(--border)}
tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px}
.badge.worse{background:rgba(229,96,76,.15);color:var(--danger)}
.badge.better{background:rgba(63,178,127,.15);color:var(--success)}
.badge.flat{background:rgba(154,166,184,.12);color:var(--text-secondary)}
.mono{font-variant-numeric:tabular-nums}
footer{color:var(--text-muted);font-size:12px;line-height:1.9;margin-top:8px}
footer a{color:var(--accent);text-decoration:none}
@media (max-width:640px){body{padding:20px 12px 32px}.chart{height:260px}}
</style>
</head>
<body>
<div class="wrap">
  <h1>竞品用户反馈监测雷达 <span style="color:var(--text-muted);font-weight:400;font-size:15px">咖啡茶饮类目 · App Store中国区</span></h1>
  <div class="sub">每日自动更新 · 最近更新 <span id="updated"></span> · 负面=1-2星 · 评论样本有幸存者偏差，趋势与横向对比有效，绝对值不代表全体用户</div>

  <div class="kpis">
    <div class="kpi"><div class="label">累计追踪评论</div><div class="value" id="k-total"></div></div>
    <div class="kpi"><div class="label">本次新增</div><div class="value" id="k-new"></div></div>
    <div class="kpi"><div class="label">负面率异动预警</div><div class="value" id="k-alerts"></div></div>
    <div class="kpi"><div class="label">监测App</div><div class="value" id="k-apps"></div></div>
    <div class="kpi"><div class="label">版本回归显著</div><div class="value" id="k-sig"></div></div>
  </div>

  <div id="alertbar"></div>

  <div class="card">
    <h2>负面率趋势（28天滚动 · 周采样）</h2>
    <div class="note">文字评论量级为个位数/周，日粒度噪声过大，故用28天滚动窗口；窗口样本不足8条断开显示</div>
    <div id="negChart" class="chart"></div>
  </div>

  <div class="card">
    <h2>平均评分趋势（28天滚动 · 周采样）</h2>
    <div class="note">与负面率互为印证：评分降而负面率未动，通常是3星中评增多</div>
    <div id="ratingChart" class="chart"></div>
  </div>

  <div class="card">
    <h2>投诉类别 × 竞品对比</h2>
    <div class="note">负面评论的关键词词典多标签分类，透明可复核，存在少量噪声</div>
    <div id="catChart" class="chart"></div>
  </div>

  <div class="card">
    <h2>版本回归检验（发版质量）</h2>
    <div class="note">同App最新两个评论量≥20的版本，负面率两比例z检验，双侧α=0.05</div>
    <table id="vtable">
      <thead><tr><th>App</th><th>版本对比</th><th class="mono">负面率变化</th><th class="mono">z</th><th class="mono">p</th><th>判定</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <footer>
    口径：数据源为苹果iTunes customerreviews公开RSS（仅iOS，每App每次最多约500条最新文字评论，历史随运行累积）。
    投诉分类为关键词规则匹配；预警为p控制图（近7天窗口对前84天基线，UCL=p̄+3σ，小样本保护n≥5且负面≥3）。
    <br>代码与数据：<a href="__REPO__" target="_blank" rel="noopener">__REPO__</a> · 姊妹项目：<a href="https://egg-zero.github.io/da-job-radar/" target="_blank" rel="noopener">数据岗位需求雷达</a>
  </footer>
</div>

<script>
const D = __DATA__;
const COLORS = ["#4C8DFF","#3FB27F","#E0A63C","#E5604C","#B08CFF"];
const AXIS = {axisLine:{lineStyle:{color:"#232D3F"}},axisLabel:{color:"#9AA6B8"},
  splitLine:{lineStyle:{color:"#1A2232"}}};

document.getElementById("updated").textContent = D.updated;
document.getElementById("k-total").textContent = D.kpis.total.toLocaleString();
document.getElementById("k-new").textContent = "+" + D.kpis.new_today.toLocaleString();
const ka = document.getElementById("k-alerts");
ka.textContent = D.kpis.alerts;
if (D.kpis.alerts > 0) ka.classList.add("warn");
document.getElementById("k-apps").textContent = D.kpis.apps;
document.getElementById("k-sig").textContent = D.kpis.sig;

const bar = document.getElementById("alertbar");
if (D.alerts.length === 0) {
  bar.innerHTML = '<div class="alertbar ok">控制图状态：各App近7天负面率均在控制限内（基线前84天），无异动预警' +
    (D.failed.length ? '（抓取失败：' + D.failed.join('、') + '）' : '') + '</div>';
} else {
  bar.innerHTML = D.alerts.map(a =>
    '<div class="alertbar bad"><b>预警</b> ' + a.window + ' <b>' + a.app + '</b> 负面率 ' +
    (a.neg_rate*100).toFixed(1) + '%（基线 ' + (a.baseline*100).toFixed(1) + '%，UCL ' +
    (a.ucl*100).toFixed(1) + '%，n=' + a.n + '）主要投诉：' +
    a.top_cats.map(c => c[0] + '×' + c[1]).join('、') + '</div>').join('');
}

function lineChart(id, series, fmt) {
  const chart = echarts.init(document.getElementById(id));
  chart.setOption({
    backgroundColor: "transparent",
    tooltip: {trigger: "axis", backgroundColor: "#161D2B", borderColor: "#232D3F",
      textStyle: {color: "#E8EDF5"}, valueFormatter: v => v == null ? "样本不足" : fmt(v)},
    legend: {textStyle: {color: "#9AA6B8"}, top: 0, icon: "roundRect"},
    grid: {left: 48, right: 16, top: 36, bottom: 28},
    xAxis: {type: "category", data: D.trend.dates, ...AXIS},
    yAxis: {type: "value", ...AXIS},
    series: Object.entries(series).map(([name, data], i) => ({
      name, type: "line", data, connectNulls: false, showSymbol: false,
      lineStyle: {width: 2}, itemStyle: {color: COLORS[i % COLORS.length]},
    })),
  });
  window.addEventListener("resize", () => chart.resize());
}
lineChart("negChart", D.trend.neg, v => v + "%");
lineChart("ratingChart", D.trend.rating, v => v + "分");

const catChart = echarts.init(document.getElementById("catChart"));
catChart.setOption({
  backgroundColor: "transparent",
  tooltip: {trigger: "axis", axisPointer: {type: "shadow"}, backgroundColor: "#161D2B",
    borderColor: "#232D3F", textStyle: {color: "#E8EDF5"}},
  legend: {textStyle: {color: "#9AA6B8"}, top: 0, icon: "roundRect"},
  grid: {left: 88, right: 24, top: 36, bottom: 28},
  xAxis: {type: "value", ...AXIS},
  yAxis: {type: "category", data: [...D.cats.names].reverse(), ...AXIS},
  series: D.cats.apps.map((app, i) => ({
    name: app, type: "bar", stack: "total",
    data: [...D.cats.matrix[app]].reverse(),
    itemStyle: {color: COLORS[i % COLORS.length]},
    barMaxWidth: 22,
  })),
});
window.addEventListener("resize", () => catChart.resize());

const tbody = document.querySelector("#vtable tbody");
tbody.innerHTML = D.versions.map(t => {
  const worse = t.neg_rate_new > t.neg_rate_old;
  const badge = !t.significant ? '<span class="badge flat">无显著变化</span>'
    : worse ? '<span class="badge worse">显著恶化</span>'
            : '<span class="badge better">显著改善</span>';
  return '<tr><td>' + t.app + '</td>' +
    '<td class="mono">' + t.old_version + ' → ' + t.new_version + '</td>' +
    '<td class="mono">' + (t.neg_rate_old*100).toFixed(1) + '% → ' + (t.neg_rate_new*100).toFixed(1) +
    '%（n=' + t.n_old + '/' + t.n_new + '）</td>' +
    '<td class="mono">' + t.z.toFixed(2) + '</td><td class="mono">' + t.p.toFixed(4) + '</td>' +
    '<td>' + badge + '</td></tr>';
}).join('') || '<tr><td colspan="6" style="color:var(--text-muted)">暂无评论量达标的版本对（每版需≥20条）</td></tr>';
</script>
</body>
</html>
"""


def main() -> None:
    payload = build_payload()
    html = TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False)) \
                   .replace("__REPO__", REPO_URL)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"看板已渲染: {OUT}")


if __name__ == "__main__":
    main()
