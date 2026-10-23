"""人工复核页：一张本地 HTML，看图 + 改名字 + 导出 corrections.csv。"""

from __future__ import annotations

import html
import json
from pathlib import Path

from .plan import PlanEntry

_CSS = """
:root{--bg:#f7f7f5;--card:#fff;--line:#e3e3df;--ink:#1d1d1b;--muted:#8a8a83;
--ok:#2f7a4f;--review:#b06a12;--fail:#a33b3b}
*{box-sizing:border-box}
body{margin:0;padding:28px 32px 80px;background:var(--bg);color:var(--ink);
font:14px/1.5 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
h1{font-size:19px;font-weight:600;margin:0 0 4px}
.sub{color:var(--muted);font-size:12.5px;margin-bottom:20px}
.bar{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid var(--line);
padding:12px 32px;display:flex;gap:14px;align-items:center;box-shadow:0 -2px 12px rgba(0,0,0,.05)}
button{font:inherit;padding:8px 16px;border-radius:7px;border:1px solid var(--line);
background:#fff;cursor:pointer}
button.primary{background:var(--ink);color:#fff;border-color:var(--ink)}
table{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);
border-radius:10px;overflow:hidden}
th{font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);font-weight:600}
td{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:middle}
tr:last-child td{border-bottom:0}
tr.review td{background:#fffdf6}
tr.fail td{background:#fdf7f7}
.thumb{width:132px;height:74px;object-fit:cover;border-radius:6px;border:1px solid var(--line);
background:#fafaf8;display:block}
.thumb.empty{display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:11px}
.file{font-size:12.5px;color:var(--muted);word-break:break-all;max-width:280px}
.badge{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11.5px;font-weight:600}
.b-ok{background:#eaf4ee;color:var(--ok)}
.b-review{background:#fdf1dd;color:var(--review)}
.b-fail{background:#fbeaea;color:var(--fail)}
input.corr{font:inherit;padding:7px 10px;border:1px solid var(--line);border-radius:7px;width:140px}
input.corr:focus{outline:2px solid #c9d8ff;border-color:#9ab}
.score{font-variant-numeric:tabular-nums;font-size:13px}
.cands{font-size:12px;color:var(--muted)}
details summary{cursor:pointer;color:var(--muted);font-size:12px}
"""

_JS = r"""
function collect(){
  const rows=[["src","name"]];
  document.querySelectorAll("input.corr").forEach(i=>{
    const v=i.value.trim();
    // 只导出「人改过」的行：没动过的沿用计划里的判断，失败项留空也不算数
    if(v && v !== i.dataset.orig) rows.push([i.dataset.src,v]);
  });
  return rows;
}
function csvEsc(s){return '"'+String(s).replace(/"/g,'""')+'"'}
document.getElementById("dl").addEventListener("click",()=>{
  const csv=collect().map(r=>r.map(csvEsc).join(",")).join("\r\n");
  const blob=new Blob(["\ufeff"+csv],{type:"text/csv;charset=utf-8"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob); a.download="corrections.csv"; a.click();
  URL.revokeObjectURL(a.href);
});
document.getElementById("copy").addEventListener("click",async()=>{
  const csv=collect().map(r=>r.map(csvEsc).join(",")).join("\r\n");
  try{ await navigator.clipboard.writeText(csv); alert("已复制 CSV 到剪贴板"); }
  catch(e){ alert("复制失败，请用「下载 CSV」"); }
});
"""


def _row(e: PlanEntry, idx: int) -> str:
    e_src = html.escape(e.src, quote=True)
    e_file = html.escape(Path(e.src).name)
    badge = {"ok": "b-ok", "review": "b-review", "fail": "b-fail"}.get(e.status, "b-fail")
    label = {"ok": "OK", "review": "复核", "fail": "失败"}.get(e.status, e.status)
    if e.crop:
        thumb = f'<img class="thumb" src="data:{e.crop_mime};base64,{e.crop}" alt="">'
    else:
        thumb = '<div class="thumb empty">无预览</div>'
    cands = " · ".join(
        f'{html.escape(c.get("name",""))} {c.get("score",0):.2f}' for c in e.candidates
    ) or html.escape(e.reason or "—")
    # 失败项故意留空：强制人工填，避免把没认出来的第一猜测当成结果导出去
    orig = "" if e.status == "fail" else (e.name or "")
    value = html.escape(orig, quote=True)
    reason = html.escape(e.error or e.reason or "", quote=True)
    return (
        f'<tr class="{e.status}"><td>{idx}</td><td>{thumb}</td>'
        f'<td class="file">{e_file}<br><span style="opacity:.6">{e.matched and "识别: " + html.escape(e.matched)}</span></td>'
        f'<td><span class="badge {badge}">{label}</span></td>'
        f'<td><input class="corr" data-src="{e_src}" data-orig="{value}" value="{value}" placeholder="填姓名"></td>'
        f'<td class="score">{e.score:.2f}</td>'
        f'<td class="cands">{cands}</td>'
        f'<td class="cands" style="max-width:220px">{reason}</td></tr>'
    )


def build_report(entries: list[PlanEntry], out_file: Path, meta: dict | None = None) -> Path:
    meta = meta or {}
    counts = {"ok": 0, "review": 0, "fail": 0}
    for e in entries:
        counts[e.status] = counts.get(e.status, 0) + 1
    rows = "\n".join(_row(e, i) for i, e in enumerate(entries, 1))
    head = (
        f"共 {len(entries)} 份 · OK {counts['ok']} · 待复核 {counts['review']} · "
        f"失败 {counts['fail']} · 模式 {html.escape(str(meta.get('mode', '-')))}"
    )
    doc = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>命名复核 · {len(entries)} 份</title><style>{_CSS}</style></head>
<body>
<h1>作业命名复核</h1>
<div class="sub">{head}</div>
<table><thead><tr>
<th style="width:36px">#</th><th>预览</th><th>原文件 / 识别结果</th><th>状态</th>
<th>姓名（可直接改）</th><th>置信度</th><th>候选</th><th>说明</th>
</tr></thead><tbody>{rows}</tbody></table>
<div class="bar">
  <button id="dl" class="primary">下载 corrections.csv</button>
  <button id="copy">复制到剪贴板</button>
  <span class="sub" style="margin:0">
    改完名字 → 下载 → <code>spn apply out/plan.json --corrections corrections.csv --yes --include-review</code>
  </span>
</div>
<script>{_JS}</script>
</body></html>"""
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(doc, encoding="utf-8")
    return out_file
