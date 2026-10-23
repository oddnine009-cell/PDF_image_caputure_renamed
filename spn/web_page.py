"""网页界面（HTML/CSS/JS 全内联，不需要构建步骤）。"""

PAGE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>作业 PDF 按姓名自动命名</title>
<style>
:root{--bg:#f6f6f3;--card:#fff;--line:#e2e2dd;--ink:#1b1b19;--muted:#83837c;
--ok:#2f7a4f;--review:#b06a12;--fail:#a33b3b;--sel:#2f6fd0}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.55 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
header{padding:28px 36px 8px}
h1{font-size:20px;margin:0 0 6px;font-weight:650}
.sub{color:var(--muted);font-size:12.5px}
main{display:grid;grid-template-columns:320px 1fr;gap:20px;padding:20px 36px 96px;align-items:start}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.card + .card{margin-top:16px}
h2{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 10px;font-weight:600}
textarea{width:100%;height:132px;resize:vertical;font:13px/1.6 ui-monospace,Consolas,monospace;
padding:10px;border:1px solid var(--line);border-radius:8px;background:#fcfcfa}
input[type=text],select{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:8px;
font:inherit;background:#fcfcfa}
label.field{display:block;margin:12px 0 0}
label.field span{display:block;font-size:12px;color:var(--muted);margin-bottom:5px}
#drop{border:1.5px dashed #cfcfc7;border-radius:12px;padding:22px 14px;text-align:center;
color:var(--muted);cursor:pointer;transition:.15s;background:#fcfcfa}
#drop.hot{border-color:var(--ink);background:#f2f2ee;color:var(--ink)}
#drop b{display:block;color:var(--ink);font-size:14px;margin-bottom:4px}
.row{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
button{font:inherit;padding:9px 16px;border-radius:9px;border:1px solid var(--line);
background:#fff;cursor:pointer;transition:.15s}
button:hover{border-color:#bdbdb5}
button.primary{background:var(--ink);color:#fff;border-color:var(--ink)}
button.primary:disabled{opacity:.35;cursor:not-allowed}
button.small{padding:5px 10px;font-size:12.5px;border-radius:7px}
table{border-collapse:collapse;width:100%}
th{font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);font-weight:600;background:#fbfbf9}
td{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:middle}
tr:last-child td{border-bottom:0}
tr.review td{background:#fffdf5}
tr.fail td{background:#fdf8f8}
.thumb{width:120px;height:64px;object-fit:cover;border-radius:6px;border:1px solid var(--line);
background:#fafaf8;display:block}
.thumb.empty{display:flex;align-items:center;justify-content:center;font-size:11px;color:var(--muted)}
.file{font-size:12.5px;color:var(--muted);word-break:break-all}
.badge{display:inline-block;padding:2px 9px;border-radius:99px;font-size:11.5px;font-weight:600}
.b-ok{background:#eaf4ee;color:var(--ok)}
.b-review{background:#fdf1dd;color:var(--review)}
.b-fail{background:#fbeaea;color:var(--fail)}
.b-ai{background:#eaf0fb;color:#2f5f9e;margin-left:4px}
.chk{display:flex;gap:8px;align-items:center;font-size:13px;cursor:pointer;user-select:none}
.chk input{width:15px;height:15px;margin:0;accent-color:var(--ink)}
input.name{width:130px;padding:6px 9px;border:1px solid var(--line);border-radius:7px;font:inherit}
input.name:focus{outline:2px solid #cdd9f8;border-color:#9fb4e8}
input.name.flash{background:#eef4ff;border-color:var(--sel)}
.cand{display:inline-flex;gap:5px;align-items:center;border:1px solid var(--line);background:#fff;
border-radius:99px;padding:2px 9px;font-size:12px;margin:2px 3px 2px 0;cursor:pointer;
font-family:inherit;line-height:1.5;transition:.12s}
.cand span{color:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.cand:hover{border-color:var(--sel);color:var(--sel);background:#f7faff}
.score{font-variant-numeric:tabular-nums}
.cands{font-size:12px;color:var(--muted);max-width:180px}
.empty-state{color:var(--muted);text-align:center;padding:48px 20px;background:#fbfbf9;
border:1px dashed var(--line);border-radius:10px}
.bar{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid var(--line);
padding:12px 36px;display:flex;gap:14px;align-items:center;box-shadow:0 -2px 14px rgba(0,0,0,.05)}
.bar .grow{flex:1;color:var(--muted);font-size:12.5px}
code{background:#f1f1ec;padding:1px 5px;border-radius:4px;font-size:12px}
.note{font-size:12px;color:var(--muted);margin-top:10px;line-height:1.6}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}
.hidden{display:none !important}
.head{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.head h2{margin:0}
.head .grow{flex:1}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(102px,1fr));gap:11px}
.fcard{position:relative;border:1px solid var(--line);border-radius:9px;overflow:hidden;
background:#fff;cursor:pointer;transition:.12s}
.fcard:hover{border-color:#bdbdb5;transform:translateY(-1px)}
.fcard.ref{border-color:var(--sel);box-shadow:0 0 0 2px rgba(47,111,208,.22)}
.fcard img{width:100%;aspect-ratio:1/1.41;object-fit:cover;display:block;background:#fafaf8}
.fcard .ph{width:100%;aspect-ratio:1/1.41;display:flex;align-items:center;justify-content:center;
background:#fafaf8;color:var(--muted);font-size:11px}
.fcard .nm{font-size:11px;padding:4px 6px 5px;color:var(--muted);white-space:nowrap;
overflow:hidden;text-overflow:ellipsis;border-top:1px solid #f0f0ec}
.fcard .x{position:absolute;top:5px;right:5px;width:20px;height:20px;border-radius:50%;
background:rgba(24,24,22,.62);color:#fff;border:0;padding:0;font-size:12px;line-height:20px;
cursor:pointer;opacity:0;transition:.12s}
.fcard:hover .x{opacity:1}
.fcard .x:hover{background:#b0382f}
.fcard .pg{position:absolute;top:5px;left:5px;background:rgba(24,24,22,.62);color:#fff;
font-size:10px;padding:1px 5px;border-radius:4px}
.fcard .ref-tag{position:absolute;bottom:26px;left:5px;background:var(--sel);color:#fff;
font-size:9.5px;padding:1px 5px;border-radius:4px}

.modal{position:fixed;inset:0;background:rgba(20,20,18,.5);display:flex;
align-items:center;justify-content:center;padding:22px;z-index:50}
.modal-card{background:var(--card);border-radius:14px;width:min(900px,100%);max-height:94vh;
display:flex;flex-direction:column;overflow:hidden;box-shadow:0 18px 60px rgba(0,0,0,.28)}
.modal-head{padding:18px 22px 12px;border-bottom:1px solid var(--line)}
.modal-head h3{margin:0 0 5px;font-size:16px}
.modal-head p{margin:0;color:var(--muted);font-size:12.5px}
.stage{position:relative;overflow:auto;padding:16px 22px;background:#f0f0ec;flex:1;min-height:220px}
.stage img{display:block;width:100%;height:auto;user-select:none;-webkit-user-drag:none;
border:1px solid var(--line);border-radius:4px;background:#fff}
.box{position:absolute;border:2px solid var(--sel);background:rgba(47,111,208,.13);
border-radius:2px;pointer-events:none}
.modal-foot{display:flex;gap:10px;align-items:center;padding:14px 22px;border-top:1px solid var(--line)}
.modal-foot .grow{flex:1;color:var(--muted);font-size:12.5px}
</style></head>
<body>
<header>
  <h1>作业 PDF 按手写姓名自动命名</h1>
  <div class="sub">本地运行 · 不上传云端 · 识别在你自己电脑上完成</div>
</header>

<main>
  <div>
    <div class="card">
      <h2>1 · 添加文件</h2>
      <div id="drop"><b>拖进来，或点击选择</b>支持多选 PDF，可随时增删</div>
      <input id="picker" type="file" accept="application/pdf" multiple hidden>
      <div class="row"><button id="loadDemo" class="small hidden">载入示例</button></div>
    </div>

    <div class="card">
      <h2>2 · 班级名单</h2>
      <textarea id="roster" placeholder="每行一个姓名，例如：&#10;张三&#10;李四&#10;欧阳修"></textarea>
      <datalist id="rosterList"></datalist>
      <div class="note">名单是准确率的关键：识别结果只会往名单上靠，靠不上就进「复核」。</div>

      <label class="field"><span>识别引擎</span>
        <select id="ocr">
          <option value="auto">自动（Windows 自带 OCR）</option>
          <option value="winocr">Windows 自带（强制）</option>
          <option value="json">同名 .ocr.json</option>
        </select>
      </label>

      <label class="field">
        <span>姓名区域（不用手填，点按钮框一下）</span>
        <input id="region" type="text" placeholder="留空 = 整页识别">
      </label>
      <div class="row">
        <button id="pickBtn" class="small">在页面上框选…</button>
        <button id="clearRegion" class="small">清除</button>
      </div>
    </div>

    <div class="card">
      <h2>3 · 疑难件复核</h2>
      <label class="chk"><input type="checkbox" id="useVision"> 用 DeepSeek 视觉模型再读一遍</label>
      <div class="note">只对「未识别」和低置信度的文件调用，每次一张姓名区域截图。
        模型只负责认字，最终仍然过名单匹配，不会直接决定文件名。</div>
      <label class="field hidden" id="keyField">
        <span>DEEPSEEK_API_KEY</span>
        <input id="visionKey" type="password" placeholder="留空则用环境变量" autocomplete="off">
      </label>
    </div>
  </div>

  <div>
    <div class="card">
      <div class="head">
        <h2>待识别文件</h2>
        <span class="grow"></span>
        <span class="mono" id="count" style="color:var(--muted);font-size:12px"></span>
        <button id="clearAll" class="small hidden">全部删除</button>
      </div>
      <div id="filesEmpty" class="empty-state">还没有文件。拖入 PDF 后这里会出现缩略图，<br>点缩略图可指定用哪一页来框选姓名区域。</div>
      <div id="grid" class="grid"></div>
    </div>

    <div id="resultsCard" class="card hidden">
      <div class="head">
        <h2>识别结果</h2>
        <span class="grow"></span>
        <span class="mono" id="summary" style="color:var(--muted);font-size:12px"></span>
      </div>
      <table><thead><tr>
        <th style="width:34px">#</th><th>预览</th><th>文件</th><th>状态</th>
        <th>姓名（可改）</th><th>置信度</th><th>候选</th>
      </tr></thead><tbody id="tb"></tbody></table>
    </div>
  </div>
</main>

<div class="bar">
  <button id="start" class="primary" disabled>开始识别</button>
  <button id="apply" disabled>生成压缩包</button>
  <div class="grow" id="status"></div>
</div>

<div id="modal" class="modal hidden">
  <div class="modal-card">
    <div class="modal-head">
      <h3>框出「姓名」所在的位置</h3>
      <p>在下面的页面上按住鼠标拖一个框，把「姓名」两个字和后面写的名字一起圈进去。
         所有同学通常在同一条横线上，所以整批文件共用这一个框。</p>
    </div>
    <div class="stage" id="stage">
      <img id="page" alt="">
      <div id="box" class="box hidden"></div>
    </div>
    <div class="modal-foot">
      <span class="grow mono" id="coords">正在渲染页面…</span>
      <button id="cancelPick">取消</button>
      <button id="skipRegion">整页识别</button>
      <button id="useRegion" class="primary" disabled>用这个区域</button>
    </div>
  </div>
</div>

<script>
const $ = s => document.querySelector(s);
let session = null, files = [], rows = [], refFid = null;
let busy = false, regionSkipped = false, stale = false;
let pickResolve = null, selRect = null;

/* ---------------- 上传 / 管理 ---------------- */
$("#drop").onclick = () => $("#picker").click();
$("#picker").onchange = e => { addFiles([...e.target.files]); e.target.value = ""; };

["dragenter","dragover"].forEach(t => $("#drop").addEventListener(t, e => {
  e.preventDefault(); $("#drop").classList.add("hot");
}));
["dragleave","drop"].forEach(t => $("#drop").addEventListener(t, e => {
  e.preventDefault(); $("#drop").classList.remove("hot");
}));
$("#drop").addEventListener("drop", e => addFiles([...e.dataTransfer.files]));

function say(msg){ $("#status").textContent = msg; }

function visionMode(){ return $("#useVision").checked ? "auto" : "off"; }
function visionPayload(){
  return {vision: visionMode(), vision_key: $("#visionKey").value};
}

$("#useVision").onchange = () => {
  $("#keyField").classList.toggle("hidden", !$("#useVision").checked);
  markStale();
};

async function ensureSession(){
  if(session) return session;
  const r = await fetch("/api/session", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({roster: $("#roster").value, ocr: $("#ocr").value, ...visionPayload()})});
  const d = await r.json();
  if(!r.ok) throw new Error(d.error || "创建会话失败");
  session = d.session;
  return session;
}

async function addFiles(list){
  const pdfs = list.filter(f => f.name.toLowerCase().endsWith(".pdf"));
  if(!pdfs.length) return;
  markStale();
  busy = true; $("#start").disabled = true;
  try{
    await ensureSession();
    for(let i=0;i<pdfs.length;i++){
      say(`上传中 ${i+1}/${pdfs.length}：${pdfs[i].name}`);
      const fd = new FormData();
      fd.append("session", session);
      fd.append("file", pdfs[i], pdfs[i].name);
      const r = await fetch("/api/upload", {method:"POST", body:fd});
      const d = await r.json();
      if(!r.ok) throw new Error(d.error || "上传失败");
      files.push(d);
      if(!refFid) refFid = d.fid;
      renderFiles();
    }
    say(`已添加，共 ${files.length} 份`);
  }catch(e){
    say("出错：" + e.message);
  }finally{
    busy = false;
    updateButtons();
  }
}

/* ---------------- 示例数据 ---------------- */
async function loadDemoAndRun(){
  const info = await (await fetch("/api/demo")).json();
  if(!info.files || !info.files.length) throw new Error("没有示例文件");
  if(info.roster && info.roster.length){
    $("#roster").value = info.roster.join("\n");
    syncRosterList();
  }
  const list = [];
  for(const f of info.files){
    const blob = await (await fetch(f.url)).blob();
    list.push(new File([blob], f.name, {type: "application/pdf"}));
  }
  await addFiles(list);

  const prev = await (await fetch("/api/preview", {method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({session, fid: refFid})})).json();
  let region = "";
  if(prev.region){
    region = prev.region.map(v => v.toFixed(3)).join(",");
    $("#region").value = region;
  }
  await runScan(region, $("#roster").value.trim());
}

async function removeFile(fid){
  const r = await fetch("/api/delete", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({session, fid})});
  const d = await r.json();
  if(!r.ok) return say("删除失败：" + (d.error || ""));
  files = files.filter(f => f.fid !== fid);
  if(refFid === fid) refFid = files.length ? files[0].fid : null;
  markStale();
  renderFiles();
}

function renderFiles(){
  const grid = $("#grid");
  grid.innerHTML = "";
  $("#filesEmpty").classList.toggle("hidden", files.length > 0);
  $("#clearAll").classList.toggle("hidden", files.length === 0);
  $("#count").textContent = files.length ? `${files.length} 份 · ${(files.reduce((a,f)=>a+f.size,0)/1048576).toFixed(1)} MB` : "";

  for(const f of files){
    const card = document.createElement("div");
    card.className = "fcard" + (f.fid === refFid ? " ref" : "");
    card.title = f.name + "（点击设为框选基准）";
    card.innerHTML =
      (f.thumb ? `<img src="data:image/jpeg;base64,${f.thumb}" alt="">`
               : `<div class="ph">无预览</div>`) +
      `<span class="pg">${f.pages}页</span>` +
      `<button class="x" title="删除">×</button>` +
      (f.fid === refFid ? `<span class="ref-tag">框选基准</span>` : "") +
      `<div class="nm">${escapeHtml(f.name)}</div>`;
    card.onclick = e => {
      if(e.target.classList.contains("x")) return;
      refFid = f.fid; renderFiles();
      say(`已选「${f.name}」作为框选基准页`);
    };
    card.querySelector(".x").onclick = async e => {
      e.stopPropagation();
      await removeFile(f.fid);
    };
    grid.appendChild(card);
  }
  updateButtons();
}

function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function updateButtons(){
  $("#start").disabled = busy || files.length === 0;
  $("#apply").disabled = busy || rows.length === 0;
}

function markStale(){
  if(!rows.length) return;
  rows = []; stale = true;
  $("#resultsCard").classList.add("hidden");
  $("#apply").disabled = true;
}

$("#clearAll").onclick = async () => {
  if(!files.length) return;
  if(!confirm(`删除全部 ${files.length} 份文件？`)) return;
  for(const f of [...files]) await removeFile(f.fid);
  say("已清空");
};

/* ---------------- 框选 ---------------- */
function fmt(r){ return r.map(v => v.toFixed(3)).join(","); }

function setBox(rect){
  const img = $("#page"), box = $("#box"), st = $("#stage");
  if(!img.naturalWidth) return;
  const ir = img.getBoundingClientRect(), sr = st.getBoundingClientRect();
  const ox = ir.left - sr.left + st.scrollLeft;
  const oy = ir.top - sr.top + st.scrollTop;
  selRect = rect;
  box.style.left = (ox + rect[0] * ir.width) + "px";
  box.style.top = (oy + rect[1] * ir.height) + "px";
  box.style.width = ((rect[2]-rect[0]) * ir.width) + "px";
  box.style.height = ((rect[3]-rect[1]) * ir.height) + "px";
  box.classList.remove("hidden");
}

function clearBox(){ selRect = null; $("#box").classList.add("hidden"); }

function openPicker(fid){
  return new Promise(async resolve => {
    pickResolve = resolve;
    $("#modal").classList.remove("hidden");
    $("#useRegion").disabled = true;
    $("#coords").textContent = "正在渲染页面…";
    clearBox();
    try{
      await ensureSession();
      // 名单可能刚被改过，自动定位要用最新的名单
      await fetch("/api/config", {method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({session, roster: $("#roster").value,
                              region: $("#region").value, ocr: $("#ocr").value, ...visionPayload()})});
      const r = await fetch("/api/preview", {method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({session, fid})});
      const d = await r.json();
      if(!r.ok) throw new Error(d.error || "预览失败");
      const img = $("#page");
      img.src = "data:image/jpeg;base64," + d.image;
      await new Promise(res => { if(img.complete) res(); else { img.onload = res; img.onerror = res; } });
      if(d.region){
        setBox(d.region);
        $("#coords").textContent = fmt(d.region) + "  ← 自动定位，可拖动重框";
        $("#useRegion").disabled = false;
        const b = $("#box");
        if(b.scrollIntoView) b.scrollIntoView({block:"center", behavior:"smooth"});
      }else{
        $("#coords").textContent = "没自动找到姓名，请在上面按住鼠标拖一个框";
      }
    }catch(e){
      $("#coords").textContent = "预览失败：" + e.message + "（可直接点「整页识别」）";
    }
  });
}

function finishPick(val){
  $("#modal").classList.add("hidden");
  const f = pickResolve; pickResolve = null;
  if(f) f(val);
}

$("#useRegion").onclick = () => finishPick(selRect ? fmt(selRect) : "");
$("#skipRegion").onclick = () => finishPick("");
$("#cancelPick").onclick = () => finishPick(null);

let dragging = false, dragStart = null;
const stage = $("#stage");

function ptToRegion(ax, ay, bx, by){
  const ir = $("#page").getBoundingClientRect();
  let x0 = (Math.min(ax,bx) - ir.left) / ir.width;
  let x1 = (Math.max(ax,bx) - ir.left) / ir.width;
  let y0 = (Math.min(ay,by) - ir.top) / ir.height;
  let y1 = (Math.max(ay,by) - ir.top) / ir.height;
  const clamp = v => Math.min(1, Math.max(0, v));
  return [clamp(x0), clamp(y0), clamp(x1), clamp(y1)].map(v => Math.round(v*1000)/1000);
}

stage.addEventListener("mousedown", e => {
  if(!$("#page").naturalWidth) return;
  dragging = true; dragStart = [e.clientX, e.clientY];
  $("#box").classList.remove("hidden");
  setBox(ptToRegion(e.clientX, e.clientY, e.clientX, e.clientY));
  e.preventDefault();
});

window.addEventListener("mousemove", e => {
  if(!dragging) return;
  setBox(ptToRegion(dragStart[0], dragStart[1], e.clientX, e.clientY));
});

window.addEventListener("mouseup", e => {
  if(!dragging) return;
  dragging = false;
  const r = ptToRegion(dragStart[0], dragStart[1], e.clientX, e.clientY);
  const narrow = (r[2]-r[0]) < 0.02 || (r[3]-r[1]) < 0.01;
  if(narrow){ clearBox(); $("#coords").textContent = "框太小了，再拖大一点"; $("#useRegion").disabled = true; return; }
  setBox(r);
  $("#coords").textContent = fmt(r);
  $("#useRegion").disabled = false;
});

$("#pickBtn").onclick = async () => {
  if(!files.length){ alert("先添加一个 PDF，我才能渲染页面给你框。"); return; }
  const picked = await openPicker(refFid || files[0].fid);
  if(picked === null) return;
  $("#region").value = picked;
  if(picked) say("已锁定姓名区域：" + picked);
};

$("#clearRegion").onclick = () => {
  $("#region").value = "";
  regionSkipped = false;
  say("已清除区域，将整页识别");
};

/* ---------------- 识别 ---------------- */
function badge(s){
  const m = {ok:["b-ok","可直接用"], review:["b-review","需复核"], fail:["b-fail","未识别"]};
  const [c, t] = m[s] || ["b-fail", s];
  return `<span class="badge ${c}">${t}</span>`;
}
function rowHtml(r){
  const thumb = r.thumb
    ? `<img class="thumb" src="data:image/jpeg;base64,${r.thumb}" alt="">`
    : `<div class="thumb empty">无预览</div>`;
  const cands = (r.candidates||[]).map(c =>
      `<button class="cand" data-id="${r.id}" data-name="${escapeHtml(c.name)}" ` +
      `title="点击填入这个姓名">${escapeHtml(c.name)}<span>${c.score.toFixed(2)}</span></button>`
    ).join("") || "—";
  const ai = r.vision
    ? `<span class="badge b-ai" title="视觉模型读作：${escapeHtml(r.vision)}">AI</span>` : "";
  return `<tr class="${r.status}"><td>${r.id+1}</td><td>${thumb}</td>
    <td class="file">${escapeHtml(r.file)}</td><td>${badge(r.status)}${ai}</td>
    <td><input class="name" data-id="${r.id}" list="rosterList"
         value="${escapeHtml(r.name||"")}" placeholder="填姓名"></td>
    <td class="score">${r.score.toFixed(2)}</td>
    <td class="cands">${cands}</td></tr>`;
}

/* 点候选直接填入姓名 */
$("#tb").addEventListener("click", e => {
  const btn = e.target.closest(".cand");
  if(!btn) return;
  const inp = document.querySelector(`input.name[data-id="${btn.dataset.id}"]`);
  if(!inp) return;
  inp.value = btn.dataset.name;
  inp.classList.add("flash");
  setTimeout(() => inp.classList.remove("flash"), 700);
  inp.focus();
});

/* 名单同步到输入框的下拉补全 */
function syncRosterList(){
  const names = $("#roster").value.split("\n").map(s => s.trim()).filter(Boolean);
  $("#rosterList").innerHTML = names.map(n => `<option value="${escapeHtml(n)}"></option>`).join("");
}
$("#roster").addEventListener("input", syncRosterList);
syncRosterList();

/* 演示模式：服务端 --demo 时可用；?demo=1 直接跑一遍（也用来截图） */
$("#loadDemo").onclick = async () => {
  if(busy) return;
  busy = true; $("#loadDemo").disabled = true;
  try{ await loadDemoAndRun(); }
  catch(e){ say("示例加载失败：" + e.message); }
  finally{ busy = false; $("#loadDemo").disabled = false; }
};

(async () => {
  try{
    const r = await fetch("/api/demo");
    if(!r.ok) return;
    const d = await r.json();
    if(!d.files || !d.files.length) return;
    const btn = $("#loadDemo");
    btn.textContent = `载入示例（${d.files.length} 份）`;
    btn.classList.remove("hidden");
    if(location.search.includes("demo=1")){
      btn.disabled = true;
      busy = true;
      try{ await loadDemoAndRun(); }
      finally{ busy = false; btn.disabled = false; }
    }
  }catch(e){ /* 演示模式未开启，忽略 */ }
})();

async function pushConfig(roster, region){
  await fetch("/api/config", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({session, roster, region, ocr: $("#ocr").value, ...visionPayload()})});
}

async function runScan(region, roster){
  await ensureSession();
  await pushConfig(roster, region);

  say(`识别中 0/${files.length}…`);
  rows = [];
  const resp = await fetch("/api/scan", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({session})});
  const d = await resp.json();
  if(!resp.ok) throw new Error(d.error || "识别失败");
  rows = d.rows;

  $("#tb").innerHTML = rows.map(rowHtml).join("");
  $("#resultsCard").classList.remove("hidden");
  const ok = rows.filter(r=>r.status==="ok").length;
  const rev = rows.filter(r=>r.status==="review").length;
  const bad = rows.filter(r=>r.status==="fail").length;
  $("#summary").textContent = `可用 ${ok} · 复核 ${rev} · 未识别 ${bad}`;
  say(`完成：可用 ${ok} · 复核 ${rev} · 未识别 ${bad}。改好名字后点「生成压缩包」。`);
  $("#apply").disabled = false;
}

$("#start").onclick = async () => {
  if(busy || !files.length) return;
  const roster = $("#roster").value.trim();
  if(roster.split(/\n/).filter(x => x.trim()).length < 2){
    alert("请先在左边填班级名单（至少 2 个姓名）——没有名单，识别结果无法收敛。");
    return;
  }

  busy = true; $("#start").disabled = true; $("#apply").disabled = true;
  try{
    await ensureSession();
    let region = $("#region").value.trim();
    await pushConfig(roster, region);

    if(!region && !regionSkipped){
      const picked = await openPicker(refFid || files[0].fid);
      if(picked === null) return;
      region = picked;
      if(region){ $("#region").value = region; }
      else regionSkipped = true;
    }

    await runScan(region, roster);
  }catch(e){
    say("出错：" + e.message);
  }finally{
    busy = false;
    $("#start").disabled = files.length === 0;
    $("#start").textContent = "重新识别";
  }
};

$("#apply").onclick = async () => {
  if(!session || busy) return;
  const corrections = {};
  document.querySelectorAll("input.name").forEach(i => {
    const v = i.value.trim();
    if(v) corrections[i.dataset.id] = v;
  });
  say("生成中…");
  try{
    const r = await fetch("/api/apply", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({session, corrections})});
    const d = await r.json();
    if(!r.ok) throw new Error(d.error || "生成失败");
    say(`已生成 ${d.count} 个文件，开始下载…`);
    window.location.href = d.url;
  }catch(e){
    say("出错：" + e.message);
  }
};
</script>
</body></html>
"""
