// ── Utilities ────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const attr = (x) => x.attributes || {};
function qs(params) { return new URLSearchParams(params).toString(); }
async function fetchJson(url) { const r = await fetch(url); if (!r.ok) throw new Error(await r.text()); return r.json(); }

// ── Canvas & State ────────────────────────────────────────────────────────────
const canvas = $("graph");
const ctx = canvas.getContext("2d");
const state = {
  lod: "symbol", view: "overview", edge: "all", depth: 1, graph: null,
  nodes: [], edges: [], byKey: new Map(), adjacent: new Map(), files: [], fileTotal: 0,
  selected: null, activeFile: null, hover: null, dragging: false, dragNode: null,
  scale: 1, ox: 0, oy: 0, lastX: 0, lastY: 0, alpha: 0,
  blastHighlighted: new Set(),
};

// ── Node / Edge color palettes ────────────────────────────────────────────────
const colors = {
  package:"#38bdf8", file:"#10b981", markdown:"#f5a524", class:"#9b7cff",
  interface:"#b9a2ff", method:"#fb4667", function:"#fb4667", symbol:"#c4b5fd",
};
const edgeColors = {
  calls:"#fb4667", imports:"#38bdf8", extends:"#9b7cff",
  implements:"#b9a2ff", doc_links:"#f5a524", contains:"#64748b",
};

// ── Data loading ──────────────────────────────────────────────────────────────
async function loadOverview() {
  state.view = "overview";
  syncViewButtons();
  const graph = await fetchJson(`/api/graph?${qs({lod:state.lod, focus:$("command").value, max_nodes:1200, max_edges:3600})}`);
  setGraph(graph);
}
async function loadLocal(id) {
  if (!id) return;
  state.view = "local";
  syncViewButtons();
  const graph = await fetchJson(`/api/neighborhood?${qs({id, depth:state.depth, edge_kind:state.edge, max_nodes:650, max_edges:1800})}`);
  setGraph(graph);
  applyLocalLayout(id);
  fit(); heat(); draw();
  if (state.byKey.has(id)) inspect(id);
}
async function searchCommand() {
  const q = $("command").value.trim();
  if (!q) return loadOverview();
  if (state.byKey.has(q)) return loadLocal(q);
  const result = await fetchJson(`/api/search?${qs({q, limit:1})}`);
  const hit = result.matches?.[0];
  if (hit) return loadLocal(hit.id);
  return loadOverview();
}
async function loadExplorer() {
  const result = await fetchJson(`/api/files?${qs({q:$("fileFilter").value, limit:5000})}`);
  state.files = (result.files || []).map(node => ({key:node.id, attributes:node}));
  state.fileTotal = result.total_matches || state.files.length;
  $("explorerCount").textContent = `${result.returned || state.files.length} / ${state.fileTotal}`;
  renderFolderTree();
  renderLegend();
}

// ── Graph state management ────────────────────────────────────────────────────
function setGraph(graph) {
  state.graph = graph; state.nodes = graph.nodes || []; state.edges = graph.edges || [];
  state.byKey = new Map(state.nodes.map(n => [n.key, n]));
  state.adjacent = new Map();
  for (const e of state.edges) {
    if (!state.adjacent.has(e.source)) state.adjacent.set(e.source, new Set());
    if (!state.adjacent.has(e.target)) state.adjacent.set(e.target, new Set());
    state.adjacent.get(e.source).add(e.target); state.adjacent.get(e.target).add(e.source);
  }
  state.blastHighlighted.clear();
  layout(); renderFolderTree(); renderMetrics(); renderLegend(); resize(); fit(); heat();
}

// ── Folder Tree ───────────────────────────────────────────────────────────────
function buildFolderTree() {
  const q = $("fileFilter").value.trim().toLowerCase();
  const files = state.files.filter(n => {
    const a = attr(n), p = String(a.file_path || a.label || n.key);
    return !q || p.toLowerCase().includes(q);
  });
  const groups = new Map();
  for (const n of files) {
    const p = String(attr(n).file_path || attr(n).label || n.key);
    const dir = p.includes("/") ? p.split("/")[0] : "root";
    if (!groups.has(dir)) groups.set(dir, []);
    groups.get(dir).push({key:n.key, path:p});
  }
  $("explorerCount").textContent = q ? `${files.length} / ${state.files.length}` : `${files.length} / ${state.fileTotal || state.files.length}`;
  return [...groups.entries()].sort((a,b)=>b[1].length-a[1].length||a[0].localeCompare(b[0]));
}
function renderFolderTree() {
  const sortedGroups = buildFolderTree();
  let visibleGroups = sortedGroups.slice(0, 20);
  const activeKey = state.activeFile || state.selected;
  if (activeKey) {
    const ag = sortedGroups.find(([,items]) => items.some(i => i.key === activeKey));
    if (ag && !visibleGroups.includes(ag)) visibleGroups = [ag, ...visibleGroups.slice(0,19)];
  }
  $("folder-tree").innerHTML = visibleGroups.map(([dir, items], i) => {
    const sorted = items.sort((a,b)=>a.path.localeCompare(b.path));
    let visible = sorted.slice(0,90);
    if (activeKey) {
      const ai = sorted.find(x => x.key === activeKey);
      if (ai && !visible.includes(ai)) visible = [ai, ...visible.slice(0,89)];
    }
    return `<details ${i<3?"open":""}><summary>${esc(dir)} <small>${items.length}</small></summary>${visible.map(item => {
      const label = item.path.split("/").slice(1).join("/") || item.path.split("/").pop();
      const active = item.key === activeKey ? " activeFile" : "";
      return `<button class="${active}" data-node="${esc(item.key)}" data-file="${esc(item.path)}">${esc(label)}</button>`;
    }).join("")}</details>`;
  }).join("") || "<p style='color:var(--muted);font-size:12px;margin:0'>No files match this filter.</p>";
}
function expandAll() {
  $("folder-tree").querySelectorAll("details").forEach(d => d.open = true);
}
function collapseAll() {
  $("folder-tree").querySelectorAll("details").forEach(d => d.open = false);
}
function onFolderClick(e) {
  const b = e.target.closest("button[data-node]");
  if (!b) return;
  state.activeFile = b.dataset.node;
  $("command").value = b.dataset.file;
  renderFolderTree();
  loadLocal(b.dataset.node);
}

// ── Legend ────────────────────────────────────────────────────────────────────
function renderLegend() {
  const usedNodeKinds = new Set(state.nodes.map(n => attr(n).kind).filter(Boolean));
  const usedEdgeKinds = new Set(state.edges.map(e => attr(e).kind).filter(Boolean));
  const nodeLegend = $("node-legend");
  const edgeLegend = $("edge-legend");
  if (!nodeLegend || !edgeLegend) return;
  if (!usedNodeKinds.size && !usedEdgeKinds.size) return;
  nodeLegend.innerHTML = [...usedNodeKinds].map(kind =>
    `<div class="legend-item"><div class="legend-dot" style="background:${colors[kind]||'#94a3b8'}"></div>${esc(kind)}</div>`
  ).join("");
  edgeLegend.innerHTML = [...usedEdgeKinds].map(kind =>
    `<div class="legend-item"><div class="legend-line" style="background:${edgeColors[kind]||'#64748b'}"></div>${esc(kind)}</div>`
  ).join("");
}

// ── Metrics / HUD ─────────────────────────────────────────────────────────────
function renderMetrics() {
  const s = state.graph?.stats || {}, a = state.graph?.attributes || {};
  $("backend").textContent = a.backend || s.backend || "json";
  $("viewCount").textContent = `${state.nodes.length} / ${state.edges.length}`;
  $("modePill").textContent = `${state.view} · ${state.lod}`;
  $("metrics").innerHTML = metric("nodes", state.nodes.length) + metric("edges", state.edges.length) + metric("total nodes", s.node_count || 0) + metric("total edges", s.edge_count || 0);
}
function metric(k, v) { return `<div class="metric"><span>${esc(k)}</span><b>${esc(v)}</b></div>`; }
function syncViewButtons() {
  document.querySelectorAll("[data-view]").forEach(x => x.classList.toggle("active", x.dataset.view === state.view));
}
function syncSelectionActions() {
  $("openLocal").disabled = !state.selected;
  $("copyId").disabled = !state.selected;
}

// ── Accordion controls ────────────────────────────────────────────────────────
document.querySelectorAll(".accordion-toggle").forEach(btn => {
  btn.addEventListener("click", () => {
    const body = $(btn.dataset.target);
    if (!body) return;
    const collapsed = body.classList.toggle("collapsed");
    btn.querySelector(".accordion-arrow").textContent = collapsed ? "▸" : "▾";
  });
});

// ── Layout / Physics ──────────────────────────────────────────────────────────
function groupKey(n) {
  const a = attr(n), p = String(a.file_path || a.label || n.key);
  if (state.lod === "package") return "package";
  if (state.lod === "file" || a.kind === "file" || a.kind === "markdown") return p.includes("/") ? p.split("/")[0] : "root";
  return p.includes("/") ? p.split("/").slice(0,2).join("/") : (a.kind || "root");
}
function hashFloat(value) {
  let h = 2166136261;
  for (let i = 0; i < value.length; i++) h = Math.imul(h ^ value.charCodeAt(i), 16777619);
  return (h >>> 0) / 4294967295;
}
function layout() {
  const groups = new Map();
  for (const n of state.nodes) { const k = groupKey(n); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(n); }
  const ordered = [...groups.values()].sort((a,b)=>b.length-a.length);
  const golden = Math.PI * (3 - Math.sqrt(5));
  const spread = Math.max(180, Math.min(720, 36 * Math.sqrt(state.nodes.length)));
  ordered.forEach((items, gi) => {
    const theta = gi * golden, rr = ordered.length === 1 ? 0 : spread * Math.sqrt((gi + .5) / ordered.length);
    const cx = Math.cos(theta) * rr * 1.28, cy = Math.sin(theta) * rr;
    const localStep = 10 + Math.min(9, Math.sqrt(items.length));
    items.sort((a,b)=>String(attr(a).label||a.key).localeCompare(String(attr(b).label||b.key)));
    items.forEach((n, i) => {
      const a = attr(n), noise = hashFloat(n.key), angle = (i + 1) * golden + noise * .9;
      const radius = Math.sqrt(i + 1) * localStep;
      a.x = cx + Math.cos(angle) * radius + (noise - .5) * 18;
      a.y = cy + Math.sin(angle) * radius + (hashFloat(n.key + ":y") - .5) * 18;
      a.gx = a.x; a.gy = a.y; a.vx = 0; a.vy = 0; a.pinned = false;
      a.r = Math.max(4, Number(a.size || 4) + (state.adjacent.get(n.key)?.size ? 2 : 0));
    });
  });
  state.alpha = .85;
}
function applyLocalLayout(centerId) {
  const center = state.byKey.get(centerId);
  if (!center || state.view !== "local") return;
  const direct = new Map();
  for (const e of state.edges) {
    if (e.source === centerId) direct.set(e.target, {edge:e, direction:"out"});
    else if (e.target === centerId) direct.set(e.source, {edge:e, direction:"in"});
  }
  const centerAttr = attr(center);
  Object.assign(centerAttr, {x:0, y:0, gx:0, gy:0, vx:0, vy:0, pinned:true, r:Math.max(9, centerAttr.r || 7)});
  const golden = Math.PI * (3 - Math.sqrt(5));
  const directNodes = [...direct.keys()].map(key => state.byKey.get(key)).filter(Boolean).sort((a,b) => {
    const da = direct.get(a.key), db = direct.get(b.key);
    return String(attr(da.edge).kind).localeCompare(String(attr(db.edge).kind)) || da.direction.localeCompare(db.direction) || String(attr(a).label || a.key).localeCompare(String(attr(b).label || b.key));
  });
  directNodes.forEach((node, i) => {
    const a = attr(node), relation = direct.get(node.key);
    const ring = Math.floor(i / 18);
    const angle = i * golden + (relation.direction === "in" ? Math.PI : 0);
    const radius = 145 + ring * 78 + (relation.direction === "in" ? 24 : 0);
    a.x = Math.cos(angle) * radius; a.y = Math.sin(angle) * radius;
    a.gx = a.x; a.gy = a.y; a.vx = 0; a.vy = 0; a.pinned = false;
  });
  const outerNodes = state.nodes.filter(node => node.key !== centerId && !direct.has(node.key)).sort((a,b) => String(attr(a).label || a.key).localeCompare(String(attr(b).label || b.key)));
  outerNodes.forEach((node, i) => {
    const a = attr(node), angle = i * golden + .6, radius = 370 + Math.floor(i / 24) * 92;
    a.x = Math.cos(angle) * radius; a.y = Math.sin(angle) * radius;
    a.gx = a.x; a.gy = a.y; a.vx = 0; a.vy = 0; a.pinned = false;
  });
}
function tick() {
  if (state.alpha < .01 || !state.nodes.length) return;
  const nodes = state.nodes.slice(0, 900), links = state.edges.slice(0, 2200);
  for (const e of links) {
    const s = state.byKey.get(e.source), t = state.byKey.get(e.target); if (!s || !t) continue;
    const a = attr(s), b = attr(t), dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx,dy) || 1;
    const f = (d - 82) * .0025 * state.alpha, fx = dx / d * f, fy = dy / d * f;
    if (!a.pinned) { a.vx += fx; a.vy += fy; } if (!b.pinned) { b.vx -= fx; b.vy -= fy; }
  }
  const spatial = nodes.slice().sort((a,b)=>attr(a).x-attr(b).x);
  for (let i=0;i<spatial.length;i++) for (let j=i+1;j<spatial.length;j++) {
    if (attr(spatial[j]).x - attr(spatial[i]).x > 34) break;
    const a = attr(spatial[i]), b = attr(spatial[j]), dx = b.x-a.x, dy = b.y-a.y, d = Math.hypot(dx,dy)||.01, min = (a.r||6)+(b.r||6)+6;
    if (d < min) { const f = (min-d)/d*.34*state.alpha; if(!a.pinned){a.vx-=dx*f;a.vy-=dy*f;} if(!b.pinned){b.vx+=dx*f;b.vy+=dy*f;} }
  }
  for (let i=0;i<nodes.length;i+=3) for (let j=i+1;j<Math.min(nodes.length,i+45);j+=3) {
    const a = attr(nodes[i]), b = attr(nodes[j]), dx = b.x-a.x, dy = b.y-a.y, d = Math.hypot(dx,dy)||.01, min = (a.r||6)+(b.r||6)+5;
    if (d < min) { const f = (min-d)/d*.18*state.alpha; if(!a.pinned){a.vx-=dx*f;a.vy-=dy*f;} if(!b.pinned){b.vx+=dx*f;b.vy+=dy*f;} }
  }
  for (const n of nodes) { const a = attr(n); if (!a.pinned) { a.vx += ((a.gx||0)-a.x)*.0018*state.alpha; a.vy += ((a.gy||0)-a.y)*.0018*state.alpha; } }
  for (const n of nodes) { const a = attr(n); if (!a.pinned) { a.x += (a.vx||0); a.y += (a.vy||0); } a.vx = (a.vx||0)*.72; a.vy = (a.vy||0)*.72; }
  state.alpha *= .95;
}
function heat() { state.alpha = Math.max(state.alpha, .55); }

// ── Canvas drawing ────────────────────────────────────────────────────────────
function resize() {
  const r = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(r.width*dpr)); canvas.height = Math.max(1, Math.floor(r.height*dpr)); ctx.setTransform(dpr,0,0,dpr,0,0); draw();
}
function fit() {
  if (!state.nodes.length) return;
  const xs = state.nodes.map(n=>attr(n).x), ys = state.nodes.map(n=>attr(n).y);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  state.scale = Math.min(canvas.clientWidth/Math.max(1,maxX-minX), canvas.clientHeight/Math.max(1,maxY-minY))*.74;
  state.ox = -((minX+maxX)/2)*state.scale; state.oy = -((minY+maxY)/2)*state.scale;
}
function screen(x,y){ return [x*state.scale+state.ox+canvas.clientWidth/2, y*state.scale+state.oy+canvas.clientHeight/2]; }
function world(x,y){ return [(x-state.ox-canvas.clientWidth/2)/state.scale, (y-state.oy-canvas.clientHeight/2)/state.scale]; }

function draw() {
  ctx.clearRect(0,0,canvas.clientWidth,canvas.clientHeight);
  drawGrid();
  const focus = state.selected || state.hover, peers = focus ? state.adjacent.get(focus) || new Set() : new Set();
  const labeledPeers = focus ? nearestPeers(focus, 10) : new Set();
  for (const e of state.edges) {
    const s=state.byKey.get(e.source), t=state.byKey.get(e.target); if(!s||!t) continue;
    const a=attr(s), b=attr(t), [x1,y1]=screen(a.x,a.y), [x2,y2]=screen(b.x,b.y), active=!focus||e.source===focus||e.target===focus;
    ctx.globalAlpha = focus ? (active ? .62 : .045) : (state.edges.length > 1600 ? .12 : .28);
    ctx.strokeStyle = edgeColors[attr(e).kind] || "#64748b"; ctx.lineWidth = active ? 1.35 : .8;
    ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke();
  }
  ctx.globalAlpha = 1;
  for (const n of state.nodes) {
    const a=attr(n), [x,y]=screen(a.x,a.y), active=n.key===state.selected||n.key===state.hover||peers.has(n.key);
    const isBlast = state.blastHighlighted.has(n.key);
    const r=Math.max(3.5,(a.r||5)*Math.sqrt(state.scale));
    ctx.globalAlpha = focus && !active ? .24 : 1;
    ctx.fillStyle = isBlast ? "#ffcc00" : (colors[a.kind] || "#94a3b8");
    ctx.strokeStyle = n.key===state.selected ? "#fff" : (isBlast ? "#ff9900" : "#071015");
    ctx.lineWidth = active ? 2.6 : (isBlast ? 2.0 : 1.2);
    ctx.beginPath(); ctx.arc(x,y,r,0,Math.PI*2); ctx.fill(); ctx.stroke();
    const showLabel = n.key===state.selected || n.key===state.hover || labeledPeers.has(n.key) || (!focus && state.nodes.length < 180 && state.scale > .38);
    if (showLabel) {
      ctx.fillStyle = (n.key===state.selected || n.key===state.hover) ? "#fff" : "#cbd5e1";
      ctx.font = (n.key===state.selected || n.key===state.hover) ? "700 12px system-ui" : "11px system-ui";
      ctx.fillText(String(a.label||n.key).slice(0,64), x+r+5, y+4);
    }
  }
  ctx.globalAlpha = 1;
}
function nearestPeers(focus, limit) {
  const center = state.byKey.get(focus);
  if (!center) return new Set();
  const c = attr(center);
  return new Set([...state.adjacent.get(focus) || []]
    .map(key => state.byKey.get(key)).filter(Boolean)
    .sort((a,b) => Math.hypot(attr(a).x-c.x, attr(a).y-c.y) - Math.hypot(attr(b).x-c.x, attr(b).y-c.y))
    .slice(0, limit).map(node => node.key));
}
function drawGrid() {
  const step = Math.max(30, Math.min(90, 54*state.scale)); ctx.strokeStyle="rgba(148,163,184,.07)"; ctx.lineWidth=1; ctx.beginPath();
  for (let x=state.ox%step; x<canvas.clientWidth; x+=step) { ctx.moveTo(x,0); ctx.lineTo(x,canvas.clientHeight); }
  for (let y=state.oy%step; y<canvas.clientHeight; y+=step) { ctx.moveTo(0,y); ctx.lineTo(canvas.clientWidth,y); }
  ctx.stroke();
}
function pick(cx, cy) {
  const [wx,wy]=world(cx,cy); let best=null, bd=Infinity;
  for (const n of state.nodes) { const a=attr(n), d=Math.hypot(a.x-wx,a.y-wy); if (d<bd && d<18/Math.max(state.scale,.22)) { best=n; bd=d; } }
  return best;
}
function pointer(e) {
  const r = canvas.getBoundingClientRect();
  return [e.clientX - r.left, e.clientY - r.top];
}
function centerOn(id) {
  const node = state.byKey.get(id); if (!node) return;
  const a = attr(node); state.ox = -a.x * state.scale; state.oy = -a.y * state.scale;
}

// ── Node inspect & details panel ──────────────────────────────────────────────
async function inspect(id) {
  const data = await fetchJson(`/api/node?${qs({id, limit:80})}`); if (!data.found) return;
  state.selected = id;
  const a = data.node;
  $("selectionTitle").textContent = a.label || id;
  syncSelectionActions();
  const selectedNode = state.byKey.get(id);
  if (selectedNode) attr(selectedNode).pinned = true;
  centerOn(id);

  // Basic kv details
  const kv = `<div class="kv"><span>kind</span><span>${esc(a.kind)}</span><span>path</span><span>${esc(a.file_path)}</span><span>in</span><span>${data.incoming_count}</span><span>out</span><span>${data.outgoing_count}</span></div>`;
  const edges = [...data.incoming.map(e=>edgeHtml("in",e)), ...data.outgoing.map(e=>edgeHtml("out",e))].join("");
  $("details").innerHTML = kv + `<div class="edgeList">${edges || "<p>No relationships.</p>"}</div>`;

  // Extended node details panel
  const ndPanel = $("nodeDetails");
  if (ndPanel) {
    ndPanel.style.display = "";
    $("nodeDetailsContent").innerHTML = `<span>kind</span><span>${esc(a.kind)}</span><span>file</span><span>${esc(a.file_path)}</span><span>label</span><span>${esc(a.label || id)}</span>`;
    // vscode:// link
    const vsLink = $("vscodeLink");
    const vsAnchor = $("vscodeLinkAnchor");
    if (a.file_path && vsLink && vsAnchor) {
      const line = (a.metadata && a.metadata.line) ? `:${a.metadata.line}` : "";
      vsAnchor.href = `vscode://file/${a.file_path}${line}`;
      vsLink.style.display = "";
    } else if (vsLink) {
      vsLink.style.display = "none";
    }
  }
  draw();
}
function edgeHtml(dir,e){ return `<div class="edge"><b>${esc(dir)} ${esc(e.kind)}</b><br>${esc(e.peer?.label||e.peer?.id||"")}<br><small>${esc(e.peer?.file_path||"")}</small></div>`; }

// ── UML panel ─────────────────────────────────────────────────────────────────
async function loadUml(nodeId, diagramType) {
  const content = $("umlContent");
  if (!content) return;
  content.innerHTML = "<span style='color:var(--muted)'>Loading…</span>";
  try {
    const result = await fetchJson(`/api/uml?${qs({node_id: nodeId, diagram_type: diagramType})}`);
    if (result.error) {
      content.innerHTML = `<span style='color:var(--accent-red)'>${esc(result.error)}</span>`;
      return;
    }
    const mermaidSrc = result.diagram || "";
    content.innerHTML = `<pre>${esc(mermaidSrc)}</pre>`;
    try {
      const rendered = await mermaid.render("mermaid-inline-" + Date.now(), mermaidSrc);
      content.innerHTML = rendered.svg;
    } catch (_) {
      // Keep the pre fallback
    }
  } catch (err) {
    content.innerHTML = `<span style='color:var(--accent-red)'>${esc(String(err))}</span>`;
  }
}
async function showUmlPopup(nodeId, diagramType) {
  const modal = $("uml-modal");
  const diagramDiv = $("umlModalDiagram");
  $("umlModalTitle").textContent = `UML: ${nodeId || ""}`;
  diagramDiv.innerHTML = "<span style='color:var(--muted)'>Loading…</span>";
  modal.style.display = "flex";
  try {
    const result = await fetchJson(`/api/uml?${qs({node_id: nodeId, diagram_type: diagramType})}`);
    if (result.error) {
      diagramDiv.innerHTML = `<span style='color:var(--accent-red)'>${esc(result.error)}</span>`;
      return;
    }
    const mermaidSrc = result.diagram || "";
    diagramDiv.innerHTML = `<pre>${esc(mermaidSrc)}</pre>`;
    try {
      const rendered = await mermaid.render("mermaid-popup-" + Date.now(), mermaidSrc);
      diagramDiv.innerHTML = rendered.svg;
    } catch (_) {
      // Keep the pre fallback
    }
  } catch (err) {
    diagramDiv.innerHTML = `<span style='color:var(--accent-red)'>${esc(String(err))}</span>`;
  }
}

// ── Blast Radius ──────────────────────────────────────────────────────────────
function highlightBlastRadius(nodeId, mode, depth) {
  state.blastHighlighted.clear();
  if (!nodeId) { draw(); return; }
  const visited = new Set([nodeId]);
  const queue = [[nodeId, 0]];
  while (queue.length) {
    const [cur, d] = queue.shift();
    if (d >= depth) continue;
    for (const e of state.edges) {
      let next = null;
      if (mode === "downstream" || mode === "both") {
        if (e.source === cur) next = e.target;
      }
      if (mode === "upstream" || mode === "both") {
        if (e.target === cur) next = e.source;
      }
      if (next && !visited.has(next)) { visited.add(next); queue.push([next, d+1]); }
    }
  }
  visited.forEach(id => state.blastHighlighted.add(id));
  draw();
}

// ── Polling ───────────────────────────────────────────────────────────────────
let _lastMtime = null;
async function pollStatus() {
  try {
    const result = await fetchJson("/api/status");
    const stats = result.stats || {};
    const mtime = stats.mtime_ns || null;
    if (mtime !== null) {
      const el = $("mtimeDisplay");
      const val = $("mtimeValue");
      if (el) el.style.display = "";
      if (val) val.textContent = new Date(Math.floor(mtime / 1e6)).toLocaleTimeString();
      if (_lastMtime !== null && mtime !== _lastMtime) {
        loadOverview();
      }
      _lastMtime = mtime;
    }
  } catch (_) {}
}
setInterval(pollStatus, 2000);

// ── Canvas event handlers ─────────────────────────────────────────────────────
canvas.addEventListener("mousedown", e => { const [x,y]=pointer(e), n=pick(x,y); state.dragging=true; state.dragNode=n; state.lastX=x; state.lastY=y; if(n) attr(n).pinned=true; });
window.addEventListener("mouseup", () => { state.dragging=false; state.dragNode=null; });
canvas.addEventListener("mousemove", e => {
  const [x,y]=pointer(e);
  if (state.dragging) {
    if (state.dragNode) { const [wx,wy]=world(x,y); Object.assign(attr(state.dragNode), {x:wx,y:wy,vx:0,vy:0}); heat(); }
    else { state.ox += x-state.lastX; state.oy += y-state.lastY; }
    state.lastX=x; state.lastY=y; return draw();
  }
  const n=pick(x,y); state.hover=n?.key||null; $("hoverPill").textContent = n ? "hover " + String(attr(n).label||n.key).slice(0,28) : "hover none"; canvas.style.cursor = n ? "pointer" : "grab"; draw();
});
canvas.addEventListener("click", e => {
  const [x,y]=pointer(e), n=pick(x,y);
  if (n) {
    inspect(n.key);
    // Show UML panel for clicked node
    const umlType = $("umlType");
    if (umlType) loadUml(n.key, umlType.value);
  } else {
    state.selected=null; syncSelectionActions();
    $("selectionTitle").textContent="No selection";
    $("details").innerHTML="<p>Select a node or choose a file.</p>";
    const nd = $("nodeDetails"); if (nd) nd.style.display = "none";
    draw();
  }
});
canvas.addEventListener("dblclick", e => { const [x,y]=pointer(e), n=pick(x,y); if(n) loadLocal(n.key); });
canvas.addEventListener("wheel", e => { e.preventDefault(); const [x,y]=pointer(e), [wx,wy]=world(x,y); state.scale=Math.min(8,Math.max(.05,state.scale*(e.deltaY<0?1.12:.89))); state.ox=x-canvas.clientWidth/2-wx*state.scale; state.oy=y-canvas.clientHeight/2-wy*state.scale; draw(); }, {passive:false});

// ── Sidebar button handlers ───────────────────────────────────────────────────
$("loadGraph").onclick = loadOverview;
$("fitGraph").onclick = () => { fit(); draw(); };
$("openLocal").onclick = () => state.selected && loadLocal(state.selected);
$("copyId").onclick = () => state.selected && navigator.clipboard?.writeText(state.selected);
$("command").addEventListener("keydown", e => { if(e.key==="Enter") searchCommand(); });
$("edgeKind").onchange = e => { state.edge = e.target.value; if(state.view==="local" && state.selected) loadLocal(state.selected); };
$("depth").oninput = e => { state.depth = Number(e.target.value); };
$("fileFilter").addEventListener("input", renderFolderTree);
$("folder-tree").onclick = onFolderClick;
$("expandAll").onclick = expandAll;
$("collapseAll").onclick = collapseAll;

$("viewMode").onclick = e => {
  const b=e.target.closest("button[data-view]"); if(!b) return;
  state.view=b.dataset.view; syncViewButtons();
  state.view==="overview" ? loadOverview() : (state.selected && loadLocal(state.selected));
};
$("lodMode").onclick = e => {
  const b=e.target.closest("button[data-lod]"); if(!b) return;
  state.lod=b.dataset.lod; document.querySelectorAll("[data-lod]").forEach(x=>x.classList.toggle("active",x===b));
  loadOverview();
};

// ── UML handlers ──────────────────────────────────────────────────────────────
const showUmlBtn = $("showUml");
if (showUmlBtn) showUmlBtn.onclick = () => {
  if (!state.selected) return;
  const t = $("umlType");
  loadUml(state.selected, t ? t.value : "class");
};
const umlPopupBtn = $("umlPopup");
if (umlPopupBtn) umlPopupBtn.onclick = () => {
  if (!state.selected) return;
  const t = $("umlType");
  showUmlPopup(state.selected, t ? t.value : "class");
};
const umlModalClose = $("umlModalClose");
if (umlModalClose) umlModalClose.onclick = () => { $("uml-modal").style.display = "none"; };
$("uml-modal").addEventListener("click", e => { if (e.target === $("uml-modal")) $("uml-modal").style.display = "none"; });

// ── Blast Radius handlers ─────────────────────────────────────────────────────
const blastDepthInput = $("blastDepth");
const blastDepthDisplay = $("blastDepthDisplay");
if (blastDepthInput && blastDepthDisplay) {
  blastDepthInput.oninput = () => { blastDepthDisplay.textContent = blastDepthInput.value; };
}
const blastHighlightBtn = $("blastHighlight");
if (blastHighlightBtn) blastHighlightBtn.onclick = () => {
  const mode = $("blastMode")?.value || "downstream";
  const depth = parseInt($("blastDepth")?.value || "2", 10);
  highlightBlastRadius(state.selected, mode, depth);
};
const blastClearBtn = $("blastClear");
if (blastClearBtn) blastClearBtn.onclick = () => {
  state.blastHighlighted.clear(); draw();
};

// ── Window resize & animation loop ───────────────────────────────────────────
window.addEventListener("resize", resize);
function frame(){ tick(); draw(); requestAnimationFrame(frame); }

// ── Boot ──────────────────────────────────────────────────────────────────────
loadExplorer(); loadOverview(); frame();
syncSelectionActions();
