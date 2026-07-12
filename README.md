# 竞品用户反馈监测雷达（App Store VOC Radar）

## 做什么

每日自动监测咖啡茶饮类目5个头部App（瑞幸咖啡、星巴克中国、库迪咖啡、蜜雪冰城、喜茶GO）的App Store中国区用户评论，做产品数据运营视角的VOC（用户之声）监控：

1. **大盘监控**：各App评分与负面率的日趋势
2. **异动预警**：负面率p控制图（3σ），突破控制限自动报警并归因到投诉类别
3. **版本回归检测**：发版后vs发版前负面率两比例z检验，识别「这次发版是不是发坏了」
4. **竞品对比**：投诉类别×App交叉对比（谁的支付投诉多、谁的版本质量稳）

产出：GitHub Pages在线看板 + Excel周报 + 逐日累积数据。GitHub Actions每日北京时间06:50自动运行。

作品集定位：演示数据分析在产品运营中最常见的工作形态——监控大盘、异动报警、发版质量回归、竞品对标。区别于一次性静态分析，这是一条持续运转的监测管线。

## 怎么跑

本地单次运行（管线本体仅标准库，Excel导出需openpyxl）：

```bash
python src/fetch_reviews.py    # 抓5个App评论RSS -> data/raw/当日.json
python src/analyze.py          # 去重累积+分类+日统计+预警+版本检验 -> data/reviews.csv, daily_stats.json
python src/export_excel.py     # Excel周报 -> reports/竞品VOC周报.xlsx
python src/build_site.py       # 渲染看板 -> docs/index.html
python tests/test_analyze.py   # 统计逻辑自测（z检验/控制图/分类词典）
```

## 目录结构

```
├── src/
│   ├── fetch_reviews.py   # App Store评论RSS抓取，单App失败不拖垮整体
│   ├── analyze.py         # 分类词典/日统计/p控制图预警/版本两比例检验
│   ├── export_excel.py    # Excel周报（概览KPI/评论明细/竞品交叉）
│   └── build_site.py      # 静态看板渲染（ECharts）
├── tests/test_analyze.py  # 统计与分类逻辑的单元自测
├── data/
│   ├── raw/               # 每日原始快照
│   ├── reviews.csv        # 去重累积的评论明细（按review_id覆盖更新）
│   └── daily_stats.json   # 逐日统计+预警记录+版本检验结果
├── reports/               # Excel周报
├── docs/index.html        # 看板页（GitHub Pages发布目录）
└── .github/workflows/update.yml   # 每日定时管线
```

## 数据源与口径（如实声明）

- 数据源：苹果iTunes customerreviews RSS（公开feed，免key）。每App每次最多拿到最近约500条文字评论，历史随运行累积
- **负面定义**：1-2星为负面，3星中性，4-5星正面
- **幸存者偏差**：写评论的用户不满比例天然偏高，趋势与横向对比有效，绝对值不代表全体用户
- **仅iOS**：不含安卓渠道，不代表全量用户
- 投诉分类是关键词词典匹配，透明可复核，有少量噪声（多标签允许）
- 评论时间为App Store反馈的时间戳（太平洋时区日期），全库口径一致
- RSS是公开feed但非苹果正式承诺的接口，可能限流或变动，管线做了单App容错

## 预警与检验逻辑

- **监控粒度由数据密度决定**：这些App的文字评论量级是个位数/周（评分很多但写文字的少），日粒度监控噪声过大不成立，因此趋势用28天滚动窗口周采样，预警用近7天合并样本
- **p控制图**：近7天合并样本对前84天基线，控制上限UCL = p̄ + 3·√(p̄(1-p̄)/n)，窗口n≥5且负面数≥3且负面率>UCL才报警（小样本保护）；窗口锚定全局最新日期，避免长期沉默App拿旧数据当「当前」
- **版本回归**：新旧版本各≥20条评论才检验（按版本聚合，不受日粒度限制），两比例z检验双侧p<0.05判定显著

## 依赖

- Python 3.10+（管线本体仅标准库）
- openpyxl（仅Excel导出）

## 备注

- 面板选择：瑞幸/星巴克评论量大（趋势稳定），库迪/蜜雪/喜茶GO量小（用于展示小样本保护），刻意保留这个组合
- 首次运行即回填历史：评论自带时间戳，第一次抓取就能画出过去数周的趋势线
- 前身项目da-job-radar（国际岗位监测）仍在运行，本项目复用其管线架构，监测对象换为中国消费业务
