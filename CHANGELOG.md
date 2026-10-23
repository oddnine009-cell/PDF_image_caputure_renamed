# Changelog

## 0.4.0 — 2026-10-23

首个公开版本。

**核心**

- 三态判定（可直接用 / 待复核 / 失败），失败项绝不套用「最佳猜测」
- 花名册闭集匹配：编辑距离 + 形近字代价 + 拼音兜底（可选依赖）+ margin 防歧义
- 命名模板、Windows 非法字符清洗、重名自动加序号
- 计划落盘 `plan.json` + 执行 `manifest.jsonl` + `rollback` 可整体撤回

**识别**

- `winocr`：Windows 自带 `Windows.Data.Pdf` + `Windows.Media.Ocr`，零依赖、离线
- 双尺度渲染（1200 / 1400）取并集，缓解同页不同宽度识别结果抖动
- `baidu` / `paddle` / `textlayer` / 旁车 `json` 多种后端
- 视觉兜底：`deepseek-flash` 读姓名区截图，输出仍走名单匹配

**网页版**

- 拖拽上传 + 首页缩略图 + 逐个删除 / 全部清空
- 页面上拖框选姓名区域，自动定位「姓名」行（框会向右留 30% 余量）
- 结果表点候选直接填入、名单下拉补全
- 一键生成重命名后的 zip
- `--demo` 载入自带样例，`?demo=1` 直接跑一遍

**工具**

- `tools/make_sample_pdfs.py` 生成模拟扫描件（Windows）
- `tools/make_demo_data.py` 纯 JSON 演示，不依赖 OCR
- `tools/mock_vision.py` 无 Key 时验证视觉链路
- `tools/smoke_web.py` 上传→识别→打包的端到端自检
