"""Standalone HTML viewer for knowledge graph exports."""

from __future__ import annotations

import html
import json
from typing import Any


def to_html_viewer(graph: dict[str, Any]) -> str:
    """Return a standalone canvas viewer for a Graphology payload."""
    graph_json = (
        json.dumps(graph, ensure_ascii=True, sort_keys=True)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    title = html.escape(str(graph.get("attributes", {}).get("name") or "TSA graph"))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  color-scheme: light;
  --bg: #f8fafc;
  --panel: #ffffff;
  --ink: #111827;
  --muted: #64748b;
  --line: #d1d5db;
  --accent: #2563eb;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; height: 100vh; overflow: hidden; font: 13px/1.4 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: var(--bg); }}
#app {{ display: grid; grid-template-columns: 320px 1fr; height: 100vh; min-width: 0; }}
aside {{ border-right: 1px solid var(--line); background: var(--panel); display: flex; flex-direction: column; min-width: 0; }}
header {{ padding: 14px 14px 10px; border-bottom: 1px solid var(--line); }}
h1 {{ margin: 0 0 8px; font-size: 15px; font-weight: 650; letter-spacing: 0; }}
.stats {{ color: var(--muted); display: grid; grid-template-columns: 1fr 1fr; gap: 4px 10px; }}
.controls {{ padding: 12px 14px; display: grid; gap: 10px; border-bottom: 1px solid var(--line); }}
label {{ display: grid; gap: 4px; color: var(--muted); font-size: 12px; }}
input, select, button {{ width: 100%; border: 1px solid var(--line); border-radius: 6px; padding: 8px 9px; background: #fff; color: var(--ink); font: inherit; }}
button {{ cursor: pointer; background: #f1f5f9; }}
button:hover {{ border-color: var(--accent); }}
#details {{ padding: 12px 14px; overflow: auto; min-height: 0; }}
#details h2 {{ margin: 0 0 8px; font-size: 14px; letter-spacing: 0; }}
.kv {{ display: grid; grid-template-columns: 82px 1fr; gap: 5px 8px; margin-bottom: 12px; }}
.kv span:nth-child(odd) {{ color: var(--muted); }}
.edge-list {{ display: grid; gap: 6px; }}
.edge-list div {{ border-top: 1px solid #eef2f7; padding-top: 6px; overflow-wrap: anywhere; }}
main {{ position: relative; min-width: 0; }}
canvas {{ width: 100%; height: 100%; display: block; background: radial-gradient(circle at 20% 20%, #ffffff 0, #f8fafc 36%, #eef2f7 100%); }}
#hint {{ position: absolute; left: 12px; bottom: 10px; color: var(--muted); background: rgba(255,255,255,0.88); border: 1px solid var(--line); border-radius: 6px; padding: 6px 8px; pointer-events: none; }}
@media (max-width: 760px) {{
  #app {{ grid-template-columns: 1fr; grid-template-rows: 260px 1fr; }}
  aside {{ border-right: 0; border-bottom: 1px solid var(--line); }}
  #details {{ display: none; }}
}}
</style>
</head>
<body>
<div id="app">
  <aside>
    <header>
      <h1>TSA Knowledge Graph</h1>
      <div class="stats" id="stats"></div>
    </header>
    <section class="controls">
      <label>Search<input id="search" type="search" autocomplete="off" placeholder="file, symbol, doc"></label>
      <label>Node kind<select id="node-kind"></select></label>
      <label>Edge kind<select id="edge-kind"></select></label>
      <button id="fit" type="button">Fit</button>
    </section>
    <section id="details"></section>
  </aside>
  <main>
    <canvas id="graph-canvas"></canvas>
    <div id="hint">Drag to pan. Wheel to zoom. Click a node.</div>
  </main>
</div>
<script id="graph-data" type="application/json">{graph_json}</script>
<script>
const graph = JSON.parse(document.getElementById("graph-data").textContent);
const canvas = document.getElementById("graph-canvas");
const ctx = canvas.getContext("2d");
const search = document.getElementById("search");
const nodeKind = document.getElementById("node-kind");
const edgeKind = document.getElementById("edge-kind");
const details = document.getElementById("details");
const statsBox = document.getElementById("stats");
const nodes = graph.nodes || [];
const edges = graph.edges || [];
const byKey = new Map(nodes.map((n) => [n.key, n]));
let selected = null;
let hover = null;
let scale = 1;
let offsetX = 0;
let offsetY = 0;
let dragging = false;
let lastX = 0;
let lastY = 0;

function attr(item) {{ return item.attributes || {{}}; }}
function unique(values) {{ return ["all", ...Array.from(new Set(values.filter(Boolean))).sort()]; }}
function fillSelect(select, values) {{
  select.innerHTML = "";
  for (const value of values) {{
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }}
}}
fillSelect(nodeKind, unique(nodes.map((n) => attr(n).kind)));
fillSelect(edgeKind, unique(edges.map((e) => attr(e).kind)));

function resize() {{
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}}
function worldToScreen(x, y) {{
  return [x * scale + offsetX + canvas.clientWidth / 2, y * scale + offsetY + canvas.clientHeight / 2];
}}
function screenToWorld(x, y) {{
  return [(x - offsetX - canvas.clientWidth / 2) / scale, (y - offsetY - canvas.clientHeight / 2) / scale];
}}
function visibleNodes() {{
  const q = search.value.trim().toLowerCase();
  return nodes.filter((n) => {{
    const a = attr(n);
    if (nodeKind.value !== "all" && a.kind !== nodeKind.value) return false;
    if (!q) return true;
    return [n.key, a.label, a.file_path, a.language].some((v) => String(v || "").toLowerCase().includes(q));
  }});
}}
function visibleEdges(keys) {{
  return edges.filter((e) => {{
    if (edgeKind.value !== "all" && attr(e).kind !== edgeKind.value) return false;
    return keys.has(e.source) && keys.has(e.target);
  }});
}}
function fit() {{
  if (!nodes.length) return;
  const xs = nodes.map((n) => Number(attr(n).x || 0));
  const ys = nodes.map((n) => Number(attr(n).y || 0));
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = Math.max(1, maxX - minX);
  const spanY = Math.max(1, maxY - minY);
  scale = Math.min(canvas.clientWidth / spanX, canvas.clientHeight / spanY) * 0.82;
  offsetX = -((minX + maxX) / 2) * scale;
  offsetY = -((minY + maxY) / 2) * scale;
  draw();
}}
function draw() {{
  ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
  const vNodes = visibleNodes();
  const keys = new Set(vNodes.map((n) => n.key));
  const vEdges = visibleEdges(keys);
  ctx.lineCap = "round";
  for (const e of vEdges) {{
    const s = byKey.get(e.source), t = byKey.get(e.target);
    if (!s || !t) continue;
    const [x1, y1] = worldToScreen(Number(attr(s).x || 0), Number(attr(s).y || 0));
    const [x2, y2] = worldToScreen(Number(attr(t).x || 0), Number(attr(t).y || 0));
    ctx.strokeStyle = edgeColor(attr(e).kind);
    ctx.globalAlpha = selected && e.source !== selected && e.target !== selected ? 0.12 : 0.42;
    ctx.lineWidth = Math.max(1, Number(attr(e).weight || 1) > 1 ? 2 : 1);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  }}
  ctx.globalAlpha = 1;
  for (const n of vNodes) {{
    const a = attr(n);
    const [x, y] = worldToScreen(Number(a.x || 0), Number(a.y || 0));
    const r = Math.max(3, Number(a.size || 4) * Math.sqrt(scale));
    const active = n.key === selected || n.key === hover || matchesSearch(n);
    ctx.fillStyle = a.color || "#64748b";
    ctx.strokeStyle = active ? "#111827" : "#ffffff";
    ctx.lineWidth = active ? 2.5 : 1.4;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    if (scale > 0.55 || active) {{
      ctx.fillStyle = "#111827";
      ctx.font = active ? "600 12px system-ui" : "11px system-ui";
      ctx.fillText(String(a.label || n.key).slice(0, 80), x + r + 4, y + 4);
    }}
  }}
  updateStats(vNodes.length, vEdges.length);
}}
function edgeColor(kind) {{
  return {{calls: "#dc2626", imports: "#2563eb", extends: "#7c3aed", implements: "#7c3aed", doc_links: "#d97706", contains: "#94a3b8"}}[kind] || "#64748b";
}}
function matchesSearch(n) {{
  const q = search.value.trim().toLowerCase();
  if (!q) return false;
  const a = attr(n);
  return [n.key, a.label, a.file_path].some((v) => String(v || "").toLowerCase().includes(q));
}}
function pick(clientX, clientY) {{
  const [wx, wy] = screenToWorld(clientX, clientY);
  let best = null, bestD = Infinity;
  for (const n of visibleNodes()) {{
    const a = attr(n);
    const dx = Number(a.x || 0) - wx;
    const dy = Number(a.y || 0) - wy;
    const d = Math.hypot(dx, dy);
    if (d < bestD && d < 14 / Math.max(scale, 0.2)) {{ best = n; bestD = d; }}
  }}
  return best;
}}
function showDetails(node) {{
  if (!node) {{
    details.innerHTML = "<h2>No selection</h2>";
    return;
  }}
  const a = attr(node);
  const related = edges.filter((e) => e.source === node.key || e.target === node.key).slice(0, 40);
  const relatedHtml = related.map((e) =>
    "<div><b>" + escapeText(attr(e).kind || "") + "</b><br>" +
    escapeText(e.source) + " -> " + escapeText(e.target) + "</div>"
  ).join("");
  details.innerHTML =
    "<h2>" + escapeText(a.label || node.key) + "</h2>" +
    '<div class="kv"><span>kind</span><span>' + escapeText(a.kind || "") +
    "</span><span>path</span><span>" + escapeText(a.file_path || "") +
    "</span><span>language</span><span>" + escapeText(a.language || "") +
    '</span></div><div class="edge-list">' + relatedHtml + "</div>";
}}
function escapeText(value) {{
  return String(value).replace(/[&<>"']/g, (c) => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
}}
function updateStats(nodeCount, edgeCount) {{
  const s = graph.stats || {{}};
  const attributes = graph.attributes || {{}};
  statsBox.innerHTML =
    "<span>nodes</span><b>" + nodeCount + "/" + (s.export_node_count || nodes.length) +
    "</b><span>edges</span><b>" + edgeCount + "/" + (s.export_edge_count || edges.length) +
    "</b><span>lod</span><b>" + escapeText(attributes.lod || "") +
    "</b><span>truncated</span><b>" + (attributes.truncated ? "yes" : "no") +
    "</b>";
}}
canvas.addEventListener("mousedown", (e) => {{ dragging = true; lastX = e.clientX; lastY = e.clientY; }});
window.addEventListener("mouseup", () => {{ dragging = false; }});
canvas.addEventListener("mousemove", (e) => {{
  if (dragging) {{ offsetX += e.clientX - lastX; offsetY += e.clientY - lastY; lastX = e.clientX; lastY = e.clientY; draw(); return; }}
  const n = pick(e.clientX, e.clientY);
  hover = n ? n.key : null;
  draw();
}});
canvas.addEventListener("click", (e) => {{
  const n = pick(e.clientX, e.clientY);
  selected = n ? n.key : null;
  showDetails(n);
  draw();
}});
canvas.addEventListener("wheel", (e) => {{
  e.preventDefault();
  const before = screenToWorld(e.clientX, e.clientY);
  scale = Math.min(12, Math.max(0.05, scale * (e.deltaY < 0 ? 1.12 : 0.89)));
  const after = screenToWorld(e.clientX, e.clientY);
  offsetX += (after[0] - before[0]) * scale;
  offsetY += (after[1] - before[1]) * scale;
  draw();
}}, {{ passive: false }});
search.addEventListener("input", draw);
nodeKind.addEventListener("change", draw);
edgeKind.addEventListener("change", draw);
document.getElementById("fit").addEventListener("click", fit);
window.addEventListener("resize", resize);
showDetails(null);
resize();
fit();
</script>
</body>
</html>
"""
