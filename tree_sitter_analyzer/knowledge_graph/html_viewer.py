"""Standalone HTML viewer for knowledge graph exports — force-directed layout."""

from __future__ import annotations

import html
import json
from typing import Any


def to_html_viewer(graph: dict[str, Any]) -> str:
    """Return a standalone force-directed canvas viewer for a Graphology payload."""
    graph_json = (
        json.dumps(graph, ensure_ascii=True, sort_keys=True)
        .replace("</", "<\\/")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
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
  color-scheme: dark;
  --bg: #060910;
  --panel: rgba(15, 22, 32, 0.84);
  --panel-solid: #0f1622;
  --panel-soft: rgba(20, 30, 44, 0.8);
  --ink: #eff2f8;
  --muted: #92a1b8;
  --line: rgba(130, 154, 178, 0.3);
  --line-soft: rgba(130, 154, 178, 0.15);
  --accent: #33d39a;
  --accent-weak: rgba(51, 211, 154, 0.22);
  --hot: #ff6a83;
  --radius: 12px;
  --shadow-soft: 0 16px 44px rgba(4, 8, 18, 0.45);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  height: 100vh;
  overflow: hidden;
  font: 13px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: var(--ink);
  background:
    radial-gradient(circle at 16% 9%, rgba(66, 188, 255, 0.16), transparent 35%),
    radial-gradient(circle at 78% 79%, rgba(159, 142, 255, 0.14), transparent 42%),
    radial-gradient(circle at 46% 48%, rgba(51, 211, 154, 0.14), transparent 56%),
    var(--bg);
}}
#app {{ display: grid; grid-template-columns: 360px minmax(0, 1fr); height: 100vh; min-width: 0; }}
.sidebar {{
  border-right: 1px solid var(--line);
  background: var(--panel);
  display: flex;
  flex-direction: column;
  min-width: 0;
  backdrop-filter: blur(8px);
}}
.brand {{
  padding: 18px 18px 14px;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.01));
}}
.eyebrow {{ color: var(--accent); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }}
h1 {{ margin: 4px 0 14px; font-size: 18px; font-weight: 720; letter-spacing: 0; }}
.stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
.metric {{
  border: 1px solid var(--line);
  border-radius: 9px;
  padding: 8px 9px;
  background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01));
  min-width: 0;
}}
.metric span {{ display: block; color: var(--muted); font-size: 11px; }}
.metric b {{ display: block; margin-top: 2px; font-size: 15px; font-variant-numeric: tabular-nums; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
section {{
  margin: 10px 12px;
  padding: 13px 14px;
  border-radius: var(--radius);
  border: 1px solid var(--line);
  background: linear-gradient(170deg, rgba(17, 23, 34, 0.8), rgba(13, 18, 27, 0.7));
  box-shadow: var(--shadow-soft);
}}
.controls {{ padding: 14px 0 0; display: grid; gap: 11px; border-bottom: 1px solid var(--line); }}
label {{ display: grid; gap: 5px; color: var(--muted); font-size: 12px; font-weight: 610; }}
input, select {{
  width: 100%;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 8px 9px;
  background: rgba(7, 11, 18, 0.86);
  color: var(--ink);
  font: inherit;
}}
input:focus, select:focus, button:focus-visible {{ outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-weak); }}
button {{
  cursor: pointer;
  width: 100%;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.01));
  color: var(--ink);
  font-weight: 680;
  padding: 8px;
  font: inherit;
  transition: transform .16s ease, box-shadow .16s ease, background .16s ease;
}}
button:hover {{ background: var(--accent); color: #041018; border-color: var(--accent); box-shadow: 0 10px 24px rgba(51, 211, 154, 0.32); transform: translateY(-1px); }}
button.active {{ background: rgba(51,211,154,0.18); border-color: var(--accent); color: var(--accent); }}
.btn-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
#legend {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; padding: 13px 0; border-bottom: 1px solid var(--line); color: var(--muted); }}
.legend-item {{ display: flex; align-items: center; min-width: 0; gap: 7px; }}
.dot {{ width: 10px; height: 10px; border-radius: 999px; flex: 0 0 auto; }}
#details {{ padding: 15px 0; overflow: auto; min-height: 0; flex: 1; }}
#details h2 {{ margin: 0 0 10px; font-size: 15px; letter-spacing: 0; overflow-wrap: anywhere; }}
#details .empty {{ color: var(--muted); margin: 0; }}
.kv {{ display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 6px 10px; margin-bottom: 14px; }}
.kv span:nth-child(odd) {{ color: var(--muted); }}
.kv span:nth-child(even) {{ overflow-wrap: anywhere; }}
.edge-list {{ display: grid; gap: 7px; }}
.edge-list div {{ border: 1px solid var(--line); border-radius: 8px; padding: 8px; overflow-wrap: anywhere; background: linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.01)); }}
.stage {{ position: relative; min-width: 0; background:
  radial-gradient(circle at 20% 8%, rgba(56,189,248,.14), transparent 30%),
  radial-gradient(circle at 80% 85%, rgba(159,142,255,.12), transparent 34%),
  #080b0e;
}}
canvas {{
  width: 100%;
  height: 100%;
  display: block;
  background: transparent;
  touch-action: none;
}}
#topbar {{ position: absolute; left: 16px; top: 14px; right: 16px; display: flex; align-items: center; justify-content: space-between; gap: 12px; pointer-events: none; }}
.pill {{
  pointer-events: none;
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 999px;
  padding: 7px 10px;
  background: rgba(255,255,255,0.78);
  color: #2e3440;
  box-shadow: 0 8px 24px rgba(24,24,27,0.08);
  backdrop-filter: blur(10px);
  font-size: 12px;
}}
#hint {{ position: absolute; left: 16px; bottom: 14px; color: var(--muted); background: rgba(8,12,20,0.84); border: 1px solid rgba(255,255,255,0.14); border-radius: 8px; padding: 7px 10px; pointer-events: none; font-size: 12px; }}
#physics-badge {{ position: absolute; right: 16px; bottom: 14px; background: rgba(51,211,154,0.18); color: var(--accent); border: 1px solid rgba(51,211,154,0.35); border-radius: 8px; padding: 6px 10px; pointer-events: none; font-size: 11px; font-weight: 700; display: none; }}
@media (max-width: 760px) {{
  #app {{ grid-template-columns: 1fr; grid-template-rows: 260px 1fr; }}
  .sidebar {{ border-right: 0; border-bottom: 1px solid var(--line); }}
  section {{ margin: 10px; }}
  #details {{ display: none; }}
  #topbar {{ display: none; }}
}}
</style>
</head>
<body>
<div id="app">
  <aside class="sidebar">
    <header class="brand">
      <div class="eyebrow">Interactive code map &middot; force-directed</div>
      <h1>TSA Knowledge Graph</h1>
      <div class="stats" id="stats"></div>
    </header>
    <section class="controls">
      <label>Search<input id="search" type="search" autocomplete="off" placeholder="file, symbol, doc"></label>
      <label>Node kind<select id="node-kind"></select></label>
      <label>Edge kind<select id="edge-kind"></select></label>
      <div class="btn-row">
        <button id="fit" type="button">Fit view</button>
        <button id="physics-toggle" type="button">Physics</button>
      </div>
    </section>
    <section id="legend"></section>
    <section id="details"></section>
  </aside>
  <main class="stage">
    <div id="topbar">
      <div class="pill" id="scope-pill"></div>
      <div class="pill">drag pan &middot; wheel zoom &middot; click node</div>
    </div>
    <canvas id="graph-canvas"></canvas>
    <div id="hint">Drag to pan &nbsp;&bull;&nbsp; Scroll to zoom &nbsp;&bull;&nbsp; Click a node to inspect</div>
    <div id="physics-badge">&#9654; PHYSICS ON</div>
  </main>
</div>
<script id="graph-data" type="application/json">{graph_json}</script>
<script>
"use strict";
// ── Data load ──────────────────────────────────────────────────────────────
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
const physicsBadge = document.getElementById("physics-badge");
const nodes = graph.nodes || [];
const edges = graph.edges || [];
const byKey = new Map(nodes.map((n) => [n.key, n]));
const adjacency = new Map();

function attr(item) {{ return item.attributes || {{}}; }}

for (const edge of edges) {{
  if (!adjacency.has(edge.source)) adjacency.set(edge.source, []);
  if (!adjacency.has(edge.target)) adjacency.set(edge.target, []);
  adjacency.get(edge.source).push(edge.target);
  adjacency.get(edge.target).push(edge.source);
}}

// ── Force-directed simulation ───────────────────────────────────────────────
// pos: Map<nodeKey, {{x, y, vx, vy}}>
const pos = new Map();
const REPULSION = 240;
const SPRING_LEN = 80;
const SPRING_K = 0.045;
const GRAVITY = 0.015;
const DAMPING = 0.88;
const BIG_GRAPH_THRESHOLD = 800; // switch to simplified physics above this
let physicsRunning = false;
let animFrameId = null;

function initPositions() {{
  // Use existing circular positions as starting state
  for (const n of nodes) {{
    const a = attr(n);
    pos.set(n.key, {{
      x: Number(a.x || (Math.random() - 0.5) * 400),
      y: Number(a.y || (Math.random() - 0.5) * 400),
      vx: 0, vy: 0
    }});
  }}
}}

function forceTick() {{
  const nodeArr = Array.from(pos.entries()); // [[key, p], ...]
  const n = nodeArr.length;
  const big = n > BIG_GRAPH_THRESHOLD;

  if (!big) {{
    // Full N² repulsion for smaller graphs
    for (let i = 0; i < n; i++) {{
      const [, a] = nodeArr[i];
      for (let j = i + 1; j < n; j++) {{
        const [, b] = nodeArr[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const dist2 = dx * dx + dy * dy + 0.01;
        const dist = Math.sqrt(dist2);
        const force = REPULSION / dist2;
        const fx = force * dx / dist, fy = force * dy / dist;
        a.vx -= fx; a.vy -= fy;
        b.vx += fx; b.vy += fy;
      }}
    }}
  }} else {{
    // Simplified grid-cell repulsion for large graphs (O(n) avg)
    const cellSize = 120;
    const grid = new Map();
    for (const [key, p] of nodeArr) {{
      const cx = Math.round(p.x / cellSize);
      const cy = Math.round(p.y / cellSize);
      const cell = `${{cx}},${{cy}}`;
      if (!grid.has(cell)) grid.set(cell, []);
      grid.get(cell).push([key, p]);
    }}
    for (const [, p] of nodeArr) {{
      const cx = Math.round(p.x / cellSize);
      const cy = Math.round(p.y / cellSize);
      for (let dcx = -1; dcx <= 1; dcx++) {{
        for (let dcy = -1; dcy <= 1; dcy++) {{
          const neighbors = grid.get(`${{cx+dcx}},${{cy+dcy}}`);
          if (!neighbors) continue;
          for (const [, b] of neighbors) {{
            if (b === p) continue;
            const dx = b.x - p.x, dy = b.y - p.y;
            const dist2 = dx * dx + dy * dy + 0.01;
            if (dist2 > cellSize * cellSize * 4) continue;
            const dist = Math.sqrt(dist2);
            const force = REPULSION / dist2;
            p.vx -= force * dx / dist;
            p.vy -= force * dy / dist;
          }}
        }}
      }}
    }}
  }}

  // Spring attraction along edges
  for (const e of edges) {{
    const a = pos.get(e.source), b = pos.get(e.target);
    if (!a || !b) continue;
    const dx = b.x - a.x, dy = b.y - a.y;
    const dist = Math.max(0.01, Math.sqrt(dx * dx + dy * dy));
    const force = SPRING_K * (dist - SPRING_LEN);
    const fx = force * dx / dist, fy = force * dy / dist;
    a.vx += fx; a.vy += fy;
    b.vx -= fx; b.vy -= fy;
  }}

  // Gravity toward center
  for (const [, p] of nodeArr) {{
    p.vx -= p.x * GRAVITY;
    p.vy -= p.y * GRAVITY;
    // Integrate + dampen
    p.x += p.vx * DAMPING;
    p.y += p.vy * DAMPING;
    p.vx *= DAMPING;
    p.vy *= DAMPING;
  }}
}}

function runInitTicks() {{
  const ticks = nodes.length > BIG_GRAPH_THRESHOLD ? 60 : 180;
  for (let i = 0; i < ticks; i++) forceTick();
}}

// ── Render state ───────────────────────────────────────────────────────────
let selected = null;
let hover = null;
let scale = 1;
let offsetX = 0;
let offsetY = 0;
let dragging = false;
let lastX = 0, lastY = 0;

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

// ── Coordinate transforms ──────────────────────────────────────────────────
function worldToScreen(x, y) {{
  return [x * scale + offsetX + canvas.clientWidth / 2, y * scale + offsetY + canvas.clientHeight / 2];
}}
function screenToWorld(x, y) {{
  return [(x - offsetX - canvas.clientWidth / 2) / scale, (y - offsetY - canvas.clientHeight / 2) / scale];
}}

// ── Node filtering ─────────────────────────────────────────────────────────
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

// ── Fit view ───────────────────────────────────────────────────────────────
function fit() {{
  if (!nodes.length) return;
  const xs = nodes.map((n) => {{ const p = pos.get(n.key); return p ? p.x : 0; }});
  const ys = nodes.map((n) => {{ const p = pos.get(n.key); return p ? p.y : 0; }});
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = Math.max(1, maxX - minX);
  const spanY = Math.max(1, maxY - minY);
  scale = Math.min(canvas.clientWidth / spanX, canvas.clientHeight / spanY) * 0.82;
  offsetX = -((minX + maxX) / 2) * scale;
  offsetY = -((minY + maxY) / 2) * scale;
  draw();
}}

// ── Draw ───────────────────────────────────────────────────────────────────
function nodeRadius(node) {{
  const a = attr(node);
  const base = {{package:9,markdown:7,file:6,class:5,method:4,function:4}}[a.kind] || 3;
  // Scale up hub nodes by centrality score stored in metadata
  const centrality = Number(a.centrality || 0);
  return Math.max(3, (base + centrality * 8) * Math.sqrt(Math.max(0.1, scale)));
}}

function draw() {{
  ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
  drawGrid();
  const vNodes = visibleNodes();
  const keys = new Set(vNodes.map((n) => n.key));
  const vEdges = visibleEdges(keys);
  const selectedAdj = selected ? new Set(adjacency.get(selected) || []) : new Set();

  // Edges
  ctx.lineCap = "round";
  for (const e of vEdges) {{
    const sp = pos.get(e.source), tp = pos.get(e.target);
    if (!sp || !tp) continue;
    const [x1, y1] = worldToScreen(sp.x, sp.y);
    const [x2, y2] = worldToScreen(tp.x, tp.y);
    const active = !selected || e.source === selected || e.target === selected;
    const ecolor = edgeColor(attr(e).kind);
    ctx.strokeStyle = ecolor;
    ctx.globalAlpha = active ? 0.50 : 0.06;
    ctx.lineWidth = active ? Math.max(1.2, Number(attr(e).weight || 1) > 1 ? 2.2 : 1.4) : 1;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    if (active && scale > 0.14) drawArrowHead(x1, y1, x2, y2, ecolor);
  }}
  ctx.globalAlpha = 1;

  // Nodes
  for (const n of vNodes) {{
    const a = attr(n);
    const p = pos.get(n.key);
    if (!p) continue;
    const [x, y] = worldToScreen(p.x, p.y);
    const r = nodeRadius(n);
    const isSelected = n.key === selected;
    const isHover = n.key === hover;
    const isNeighbour = selectedAdj.has(n.key);
    const active = isSelected || isHover || isNeighbour || matchesSearch(n);
    ctx.globalAlpha = selected && !active ? 0.22 : 1;

    // Glow for hubs with high centrality
    const centrality = Number(a.centrality || 0);
    if (centrality > 0.4 && scale > 0.2) {{
      ctx.save();
      ctx.shadowColor = nodeColor(a.kind, a.color);
      ctx.shadowBlur = 14 * centrality;
      ctx.fillStyle = nodeColor(a.kind, a.color);
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }}

    ctx.fillStyle = nodeColor(a.kind, a.color);
    ctx.strokeStyle = isSelected ? "#e11d48" : (isHover ? "#ffffff" : "rgba(255,255,255,0.5)");
    ctx.lineWidth = isSelected ? 3 : active ? 2 : 1.2;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    if (scale > 0.45 || active) {{
      ctx.globalAlpha = 1;
      ctx.fillStyle = isSelected ? "#e11d48" : (active ? "#f8fafc" : "#b0bec5");
      ctx.font = active ? "bold 12px system-ui" : "11px system-ui";
      ctx.fillText(String(a.label || n.key).slice(0, 72), x + r + 4, y + 4);
    }}
  }}
  ctx.globalAlpha = 1;
  updateStats(vNodes.length, vEdges.length);
}}

function drawGrid() {{
  const step = Math.max(32, Math.min(96, 52 * scale));
  ctx.strokeStyle = "rgba(24,24,27,0.045)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  const ox = ((offsetX + canvas.clientWidth / 2) % step + step) % step;
  const oy = ((offsetY + canvas.clientHeight / 2) % step + step) % step;
  for (let x = ox - step; x < canvas.clientWidth; x += step) {{ ctx.moveTo(x, 0); ctx.lineTo(x, canvas.clientHeight); }}
  for (let y = oy - step; y < canvas.clientHeight; y += step) {{ ctx.moveTo(0, y); ctx.lineTo(canvas.clientWidth, y); }}
  ctx.stroke();
}}

function drawArrowHead(x1, y1, x2, y2, color) {{
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const len = 8;
  ctx.save();
  ctx.translate(x2, y2);
  ctx.rotate(angle);
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.55;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(-len, -len * 0.42);
  ctx.lineTo(-len, len * 0.42);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}}

function edgeColor(kind) {{
  return {{calls:"#dc2626",imports:"#2563eb",extends:"#7c3aed",implements:"#7c3aed",doc_links:"#d97706",contains:"#a1a1aa",references:"#f59e0b"}}[kind] || "#64748b";
}}
function nodeColor(kind, fallback) {{
  return {{package:"#2563eb",markdown:"#d97706",file:"#0f766e",class:"#7c3aed",method:"#dc2626",function:"#dc2626",symbol:"#64748b"}}[kind] || fallback || "#64748b";
}}
function matchesSearch(n) {{
  const q = search.value.trim().toLowerCase();
  if (!q) return false;
  return [n.key, attr(n).label, attr(n).file_path].some((v) => String(v||"").toLowerCase().includes(q));
}}

// ── Node pick ──────────────────────────────────────────────────────────────
function pick(cx, cy) {{
  const [wx, wy] = screenToWorld(cx, cy);
  let best = null, bestD = Infinity;
  for (const n of visibleNodes()) {{
    const p = pos.get(n.key);
    if (!p) continue;
    const dx = p.x - wx, dy = p.y - wy;
    const d = Math.hypot(dx, dy);
    if (d < bestD && d < 18 / Math.max(scale, 0.18)) {{ best = n; bestD = d; }}
  }}
  return best;
}}

// ── Details panel ──────────────────────────────────────────────────────────
function showDetails(node) {{
  if (!node) {{
    details.innerHTML = '<h2>No selection</h2><p class="empty">Click a node to inspect file, symbol, doc, and relationship details.</p>';
    return;
  }}
  const a = attr(node);
  const allRelated = edges.filter((e) => e.source === node.key || e.target === node.key);
  const incoming = allRelated.filter((e) => e.target === node.key).length;
  const outgoing = allRelated.filter((e) => e.source === node.key).length;
  const centrality = a.centrality != null ? Number(a.centrality).toFixed(4) : "—";
  const related = allRelated.slice(0, 40);
  const relHtml = related.map((e) =>
    "<div><b>" + escapeText(attr(e).kind||"") + "</b>&nbsp;" +
    escapeText(e.source) + " &rarr; " + escapeText(e.target) + "</div>"
  ).join("");
  details.innerHTML =
    "<h2>" + escapeText(a.label || node.key) + "</h2>" +
    '<div class="kv">' +
    "<span>kind</span><span>" + escapeText(a.kind||"") + "</span>" +
    "<span>path</span><span>" + escapeText(a.file_path||"") + "</span>" +
    "<span>language</span><span>" + escapeText(a.language||"") + "</span>" +
    "<span>in&nbsp;edges</span><span>" + incoming + "</span>" +
    "<span>out&nbsp;edges</span><span>" + outgoing + "</span>" +
    "<span>centrality</span><span>" + centrality + "</span>" +
    '</div><div class="edge-list">' + relHtml + "</div>";
}}
function escapeText(v) {{
  return String(v).replace(/[&<>"']/g,(c)=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
}}

// ── Stats ──────────────────────────────────────────────────────────────────
function updateStats(nodeCount, edgeCount) {{
  const s = graph.stats || {{}};
  statsBox.innerHTML =
    metric("visible nodes", nodeCount + "/" + (s.export_node_count || nodes.length)) +
    metric("visible edges", edgeCount + "/" + (s.export_edge_count || edges.length)) +
    metric("total nodes", s.node_count || nodes.length) +
    metric("physics", physicsRunning ? "live" : "settled");
}}
function metric(label, value) {{
  return '<div class="metric"><span>' + escapeText(label) + '</span><b>' + escapeText(String(value)) + '</b></div>';
}}
function renderLegend() {{
  const kinds = unique(nodes.map((n) => attr(n).kind)).filter((k) => k !== "all").slice(0, 8);
  legendBox.innerHTML = kinds.map((kind) =>
    '<div class="legend-item"><span class="dot" style="background:' + nodeColor(kind) + '"></span><span>' + escapeText(kind) + '</span></div>'
  ).join("");
}}

// ── Physics toggle ─────────────────────────────────────────────────────────
function startPhysics() {{
  if (physicsRunning) return;
  physicsRunning = true;
  physicsBadge.style.display = "block";
  document.getElementById("physics-toggle").classList.add("active");
  function animate() {{
    if (!physicsRunning) return;
    forceTick();
    draw();
    animFrameId = requestAnimationFrame(animate);
  }}
  animFrameId = requestAnimationFrame(animate);
}}
function stopPhysics() {{
  physicsRunning = false;
  if (animFrameId) {{ cancelAnimationFrame(animFrameId); animFrameId = null; }}
  physicsBadge.style.display = "none";
  document.getElementById("physics-toggle").classList.remove("active");
  draw();
}}

// ── Resize ─────────────────────────────────────────────────────────────────
function resize() {{
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}}

// ── Event listeners ────────────────────────────────────────────────────────
canvas.addEventListener("mousedown", (e) => {{ dragging = true; lastX = e.clientX; lastY = e.clientY; }});
window.addEventListener("mouseup", () => {{ dragging = false; }});
canvas.addEventListener("mousemove", (e) => {{
  if (dragging) {{
    offsetX += e.clientX - lastX; offsetY += e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    if (!physicsRunning) draw();
    return;
  }}
  const n = pick(e.clientX, e.clientY);
  const newHover = n ? n.key : null;
  if (newHover !== hover) {{ hover = newHover; if (!physicsRunning) draw(); }}
}});
canvas.addEventListener("click", (e) => {{
  const n = pick(e.clientX, e.clientY);
  selected = n ? n.key : null;
  showDetails(n);
  if (!physicsRunning) draw();
}});
canvas.addEventListener("wheel", (e) => {{
  e.preventDefault();
  const before = screenToWorld(e.clientX, e.clientY);
  scale = Math.min(14, Math.max(0.04, scale * (e.deltaY < 0 ? 1.12 : 0.89)));
  const after = screenToWorld(e.clientX, e.clientY);
  offsetX += (after[0] - before[0]) * scale;
  offsetY += (after[1] - before[1]) * scale;
  if (!physicsRunning) draw();
}}, {{ passive: false }});
search.addEventListener("input", () => {{ if (!physicsRunning) draw(); }});
nodeKind.addEventListener("change", () => {{ if (!physicsRunning) draw(); }});
edgeKind.addEventListener("change", () => {{ if (!physicsRunning) draw(); }});
document.getElementById("fit").addEventListener("click", fit);
document.getElementById("physics-toggle").addEventListener("click", () => {{
  physicsRunning ? stopPhysics() : startPhysics();
}});
window.addEventListener("resize", resize);

// ── Boot ───────────────────────────────────────────────────────────────────
initPositions();
runInitTicks();
showDetails(null);
resize();
fit();
</script>
</body>
</html>
"""
