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
  --bg: #f5f6f8;
  --panel: #ffffff;
  --panel-2: #fafafa;
  --ink: #18181b;
  --muted: #71717a;
  --line: #d8d8dc;
  --soft-line: #ececef;
  --accent: #0f766e;
  --accent-ink: #0f3f3a;
  --focus: #e11d48;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; height: 100vh; overflow: hidden; font: 13px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: var(--bg); }}
#app {{ display: grid; grid-template-columns: 360px minmax(0, 1fr); height: 100vh; min-width: 0; }}
.sidebar {{ border-right: 1px solid var(--line); background: var(--panel); display: flex; flex-direction: column; min-width: 0; }}
.brand {{ padding: 18px 18px 14px; border-bottom: 1px solid var(--line); }}
.eyebrow {{ color: var(--accent); font-size: 11px; font-weight: 700; text-transform: uppercase; }}
h1 {{ margin: 4px 0 14px; font-size: 18px; font-weight: 720; letter-spacing: 0; }}
.stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
.metric {{ border: 1px solid var(--soft-line); border-radius: 8px; padding: 8px 9px; background: var(--panel-2); min-width: 0; }}
.metric span {{ display: block; color: var(--muted); font-size: 11px; }}
.metric b {{ display: block; margin-top: 2px; font-size: 15px; font-variant-numeric: tabular-nums; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.controls {{ padding: 14px 18px; display: grid; gap: 11px; border-bottom: 1px solid var(--line); }}
label {{ display: grid; gap: 5px; color: var(--muted); font-size: 12px; font-weight: 610; }}
input, select, button {{ width: 100%; border: 1px solid var(--line); border-radius: 7px; padding: 8px 9px; background: #fff; color: var(--ink); font: inherit; }}
input:focus, select:focus, button:focus {{ outline: 2px solid rgba(15, 118, 110, 0.22); border-color: var(--accent); }}
button {{ cursor: pointer; background: var(--ink); border-color: var(--ink); color: #fff; font-weight: 680; }}
button:hover {{ background: var(--accent-ink); border-color: var(--accent-ink); }}
#legend {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; padding: 13px 18px; border-bottom: 1px solid var(--line); color: var(--muted); }}
.legend-item {{ display: flex; align-items: center; min-width: 0; gap: 7px; }}
.dot {{ width: 10px; height: 10px; border-radius: 999px; flex: 0 0 auto; }}
#details {{ padding: 15px 18px; overflow: auto; min-height: 0; }}
#details h2 {{ margin: 0 0 10px; font-size: 15px; letter-spacing: 0; overflow-wrap: anywhere; }}
#details .empty {{ color: var(--muted); margin: 0; }}
.kv {{ display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 6px 10px; margin-bottom: 14px; }}
.kv span:nth-child(odd) {{ color: var(--muted); }}
.kv span:nth-child(even) {{ overflow-wrap: anywhere; }}
.edge-list {{ display: grid; gap: 7px; }}
.edge-list div {{ border: 1px solid var(--soft-line); border-radius: 7px; padding: 8px; overflow-wrap: anywhere; background: var(--panel-2); }}
.stage {{ position: relative; min-width: 0; background: #f7f7f8; }}
canvas {{ width: 100%; height: 100%; display: block; background: #f7f7f8; }}
#topbar {{ position: absolute; left: 16px; top: 14px; right: 16px; display: flex; align-items: center; justify-content: space-between; gap: 12px; pointer-events: none; }}
.pill {{ pointer-events: none; border: 1px solid rgba(24,24,27,0.12); border-radius: 999px; padding: 7px 10px; background: rgba(255,255,255,0.84); color: var(--muted); box-shadow: 0 8px 24px rgba(24,24,27,0.08); backdrop-filter: blur(10px); }}
#hint {{ position: absolute; left: 16px; bottom: 14px; color: var(--muted); background: rgba(255,255,255,0.9); border: 1px solid rgba(24,24,27,0.12); border-radius: 8px; padding: 7px 10px; pointer-events: none; box-shadow: 0 8px 24px rgba(24,24,27,0.08); }}
@media (max-width: 760px) {{
  #app {{ grid-template-columns: 1fr; grid-template-rows: 260px 1fr; }}
  .sidebar {{ border-right: 0; border-bottom: 1px solid var(--line); }}
  #details {{ display: none; }}
  #topbar {{ display: none; }}
}}
</style>
</head>
<body>
<div id="app">
  <aside class="sidebar">
    <header class="brand">
      <div class="eyebrow">Interactive code map</div>
      <h1>TSA Knowledge Graph</h1>
      <div class="stats" id="stats"></div>
    </header>
    <section class="controls">
      <label>Search<input id="search" type="search" autocomplete="off" placeholder="file, symbol, doc"></label>
      <label>Node kind<select id="node-kind"></select></label>
      <label>Edge kind<select id="edge-kind"></select></label>
      <button id="fit" type="button">Fit</button>
    </section>
    <section id="legend"></section>
    <section id="details"></section>
  </aside>
  <main class="stage">
    <div id="topbar">
      <div class="pill" id="scope-pill"></div>
      <div class="pill">pan / zoom / select</div>
    </div>
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
const legendBox = document.getElementById("legend");
const scopePill = document.getElementById("scope-pill");
const nodes = graph.nodes || [];
const edges = graph.edges || [];
const byKey = new Map(nodes.map((n) => [n.key, n]));
const adjacency = new Map();
let selected = null;
let hover = null;
let scale = 1;
let offsetX = 0;
let offsetY = 0;
let dragging = false;
let lastX = 0;
let lastY = 0;

function attr(item) {{ return item.attributes || {{}}; }}
for (const edge of edges) {{
  if (!adjacency.has(edge.source)) adjacency.set(edge.source, new Set());
  if (!adjacency.has(edge.target)) adjacency.set(edge.target, new Set());
  adjacency.get(edge.source).add(edge.target);
  adjacency.get(edge.target).add(edge.source);
}}
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
renderLegend();
scopePill.textContent = "LOD " + ((graph.attributes || {{}}).lod || "file");

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
  drawGrid();
  const vNodes = visibleNodes();
  const keys = new Set(vNodes.map((n) => n.key));
  const vEdges = visibleEdges(keys);
  const selectedNeighbours = selected ? adjacency.get(selected) || new Set() : new Set();
  ctx.lineCap = "round";
  for (const e of vEdges) {{
    const s = byKey.get(e.source), t = byKey.get(e.target);
    if (!s || !t) continue;
    const [x1, y1] = worldToScreen(Number(attr(s).x || 0), Number(attr(s).y || 0));
    const [x2, y2] = worldToScreen(Number(attr(t).x || 0), Number(attr(t).y || 0));
    const activeEdge = !selected || e.source === selected || e.target === selected;
    ctx.strokeStyle = edgeColor(attr(e).kind);
    ctx.globalAlpha = activeEdge ? 0.52 : 0.08;
    ctx.lineWidth = activeEdge ? Math.max(1.2, Number(attr(e).weight || 1) > 1 ? 2.2 : 1.2) : 1;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    if (activeEdge && scale > 0.16) drawArrowHead(x1, y1, x2, y2, edgeColor(attr(e).kind));
  }}
  ctx.globalAlpha = 1;
  for (const n of vNodes) {{
    const a = attr(n);
    const [x, y] = worldToScreen(Number(a.x || 0), Number(a.y || 0));
    const r = Math.max(3, Number(a.size || 4) * Math.sqrt(scale));
    const active = n.key === selected || n.key === hover || selectedNeighbours.has(n.key) || matchesSearch(n);
    ctx.globalAlpha = selected && !active ? 0.28 : 1;
    ctx.fillStyle = nodeColor(a.kind, a.color);
    ctx.strokeStyle = n.key === selected ? "#e11d48" : "#ffffff";
    ctx.lineWidth = n.key === selected ? 3 : active ? 2 : 1.4;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    if (scale > 0.55 || active) {{
      ctx.globalAlpha = 1;
      ctx.fillStyle = "#18181b";
      ctx.font = active ? "600 12px system-ui" : "11px system-ui";
      ctx.fillText(String(a.label || n.key).slice(0, 80), x + r + 4, y + 4);
    }}
  }}
  ctx.globalAlpha = 1;
  updateStats(vNodes.length, vEdges.length);
}}
function drawGrid() {{
  ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
  const step = Math.max(32, Math.min(96, 52 * scale));
  ctx.strokeStyle = "rgba(24,24,27,0.055)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = (offsetX % step); x < canvas.clientWidth; x += step) {{
    ctx.moveTo(x, 0);
    ctx.lineTo(x, canvas.clientHeight);
  }}
  for (let y = (offsetY % step); y < canvas.clientHeight; y += step) {{
    ctx.moveTo(0, y);
    ctx.lineTo(canvas.clientWidth, y);
  }}
  ctx.stroke();
}}
function drawArrowHead(x1, y1, x2, y2, color) {{
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const len = 7;
  ctx.save();
  ctx.translate(x2, y2);
  ctx.rotate(angle);
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.5;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(-len, -len * 0.45);
  ctx.lineTo(-len, len * 0.45);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}}
function edgeColor(kind) {{
  return {{calls: "#dc2626", imports: "#2563eb", extends: "#7c3aed", implements: "#7c3aed", doc_links: "#d97706", contains: "#a1a1aa"}}[kind] || "#64748b";
}}
function nodeColor(kind, fallback) {{
  return {{package: "#2563eb", markdown: "#d97706", file: "#0f766e", class: "#7c3aed", method: "#dc2626", function: "#dc2626", symbol: "#64748b"}}[kind] || fallback || "#64748b";
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
    details.innerHTML = '<h2>No selection</h2><p class="empty">Select a node to inspect file, symbol, doc, and relationship details.</p>';
    return;
  }}
  const a = attr(node);
  const allRelated = edges.filter((e) => e.source === node.key || e.target === node.key);
  const incoming = allRelated.filter((e) => e.target === node.key).length;
  const outgoing = allRelated.filter((e) => e.source === node.key).length;
  const related = allRelated.slice(0, 40);
  const relatedHtml = related.map((e) =>
    "<div><b>" + escapeText(attr(e).kind || "") + "</b><br>" +
    escapeText(e.source) + " -> " + escapeText(e.target) + "</div>"
  ).join("");
  details.innerHTML =
    "<h2>" + escapeText(a.label || node.key) + "</h2>" +
    '<div class="kv"><span>kind</span><span>' + escapeText(a.kind || "") +
    "</span><span>path</span><span>" + escapeText(a.file_path || "") +
    "</span><span>language</span><span>" + escapeText(a.language || "") +
    "</span><span>incoming</span><span>" + incoming +
    "</span><span>outgoing</span><span>" + outgoing +
    '</span></div><div class="edge-list">' + relatedHtml + "</div>";
}}
function escapeText(value) {{
  return String(value).replace(/[&<>"']/g, (c) => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
}}
function updateStats(nodeCount, edgeCount) {{
  const s = graph.stats || {{}};
  const attributes = graph.attributes || {{}};
  const materializedNodes = s.node_count || nodes.length;
  const materializedEdges = s.edge_count || edges.length;
  const exportNodes = s.export_node_count || nodes.length;
  const exportEdges = s.export_edge_count || edges.length;
  statsBox.innerHTML =
    metric("visible nodes", nodeCount + "/" + exportNodes) +
    metric("visible edges", edgeCount + "/" + exportEdges) +
    metric("materialized", materializedNodes + " / " + materializedEdges) +
    metric("viewer capped", attributes.truncated ? "yes" : "no");
}}
function metric(label, value) {{
  return '<div class="metric"><span>' + escapeText(label) + '</span><b>' + escapeText(value) + '</b></div>';
}}
function renderLegend() {{
  const kinds = unique(nodes.map((n) => attr(n).kind)).filter((k) => k !== "all").slice(0, 8);
  legendBox.innerHTML = kinds.map((kind) =>
    '<div class="legend-item"><span class="dot" style="background:' + nodeColor(kind) + '"></span><span>' + escapeText(kind) + '</span></div>'
  ).join("");
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
