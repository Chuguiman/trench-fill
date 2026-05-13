"use client";

import { useState, useEffect, useRef, useCallback, DragEvent } from "react";
import type { Project, Layer } from "@/lib/supabase";
import LayerGridViewer from "@/components/LayerGridViewer";
import SvgPlanViewer  from "@/components/SvgPlanViewer";

const DOT: Record<string, string> = {
  interpolated: "#4ade80",
  pending: "#facc15",
  parsing: "#facc15",
  error: "#f87171",
};

const CHIP_BG: Record<string, string> = {
  interpolated: "#14532d",
  pending: "#1c1c00",
  parsing: "#1c1c00",
  error: "#450a0a",
};

const CHIP_FG: Record<string, string> = {
  interpolated: "#4ade80",
  pending: "#facc15",
  parsing: "#facc15",
  error: "#f87171",
};

const s = {
  page: {
    minHeight: "100vh", background: "#0a0a0a", color: "#e5e5e5",
    fontFamily: "monospace", display: "flex", flexDirection: "column" as const,
  },
  topbar: {
    display: "flex", alignItems: "center", gap: 12,
    padding: "10px 20px", background: "#111", borderBottom: "1px solid #222",
  },
  logo: { color: "#f5c518", fontWeight: "bold", fontSize: 15, letterSpacing: 1 },
  backLink: {
    color: "#888", fontSize: 12, textDecoration: "none",
    padding: "4px 10px", border: "1px solid #333", borderRadius: 3,
  },
  body: { display: "flex", flex: 1, overflow: "hidden" },
  sidebar: {
    width: 280, minWidth: 280, background: "#111", borderRight: "1px solid #222",
    display: "flex", flexDirection: "column" as const, overflow: "hidden",
  },
  sideHead: {
    padding: "10px 14px", borderBottom: "1px solid #222",
    fontSize: 11, color: "#666", textTransform: "uppercase" as const, letterSpacing: 1,
    display: "flex", justifyContent: "space-between", alignItems: "center",
  },
  projList: { flex: 1, overflowY: "auto" as const },
  projItem: (active: boolean) => ({
    padding: "9px 14px", cursor: "pointer",
    background: active ? "#161616" : "transparent",
    borderBottom: "1px solid #181818",
    borderLeft: active ? "2px solid #f5c518" : "2px solid transparent",
    display: "flex", alignItems: "center", gap: 8,
  }),
  projName: { fontSize: 12, color: "#e5e5e5", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const },
  projMeta: { fontSize: 10, color: "#444" },
  delBtn: {
    background: "none", border: "none", color: "#444", cursor: "pointer",
    fontSize: 14, padding: "0 2px", lineHeight: 1, flexShrink: 0,
  },
  main: { flex: 1, display: "flex", flexDirection: "column" as const, overflow: "hidden" },
  mainHead: {
    padding: "12px 20px", borderBottom: "1px solid #222",
    display: "flex", alignItems: "center", justifyContent: "space-between",
  },
  mainTitle: { fontSize: 14, color: "#e5e5e5", fontWeight: "bold" },
  mainBody: { flex: 1, overflowY: "auto" as const, padding: 20 },
  form: {
    background: "#111", border: "1px solid #222", borderRadius: 6,
    padding: 18, marginBottom: 18,
  },
  formTitle: { fontSize: 11, color: "#555", marginBottom: 12, textTransform: "uppercase" as const, letterSpacing: 1 },
  input: {
    width: "100%", background: "#0a0a0a", border: "1px solid #2a2a2a",
    color: "#e5e5e5", padding: "6px 10px", fontSize: 12, borderRadius: 4,
    fontFamily: "monospace", boxSizing: "border-box" as const, outline: "none",
  },
  btnPrimary: {
    padding: "7px 16px", background: "#f5c518", color: "#000",
    border: "none", borderRadius: 4, cursor: "pointer",
    fontFamily: "monospace", fontWeight: "bold", fontSize: 12,
  },
  btnSecondary: {
    padding: "5px 12px", background: "#1a1a1a", color: "#888",
    border: "1px solid #2a2a2a", borderRadius: 4, cursor: "pointer",
    fontFamily: "monospace", fontSize: 11,
  },
  btnDanger: {
    padding: "5px 12px", background: "#1a0000", color: "#f87171",
    border: "1px solid #450a0a", borderRadius: 4, cursor: "pointer",
    fontFamily: "monospace", fontSize: 11,
  },
  drop: (hover: boolean) => ({
    border: `2px dashed ${hover ? "#f5c518" : "#2a2a2a"}`,
    borderRadius: 6, padding: 28, textAlign: "center" as const,
    background: hover ? "#151000" : "#0d0d0d",
    cursor: "pointer", transition: "all 0.15s", marginBottom: 12,
  }),
};

export default function ProjectsPage() {
  const [projects, setProjects]       = useState<Project[]>([]);
  const [activeProj, setActiveProj]   = useState<Project | null>(null);
  const [layers, setLayers]           = useState<Layer[]>([]);
  const [loadingProjs, setLoadingProjs] = useState(true);
  const [loadingLayers, setLoadingLayers] = useState(false);
  const [confirmDel, setConfirmDel]   = useState<string | null>(null); // project id
  const [gridLayer, setGridLayer]     = useState<string | null>(null);
  const [svgUrl,    setSvgUrl]        = useState<string | null>(null);
  const [activeLayerId, setActiveLayerId] = useState<string | null>(null);

  // New project form
  const [showNewProj, setShowNewProj] = useState(false);
  const [newName, setNewName]         = useState("");
  const [newDesc, setNewDesc]         = useState("");
  const [creating, setCreating]       = useState(false);

  // Upload
  const [dragOver, setDragOver]       = useState(false);
  const [uploading, setUploading]     = useState(false);
  const [uploadLog, setUploadLog]     = useState<string | null>(null);
  const [uploadErr, setUploadErr]     = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const fetchProjects = useCallback(async () => {
    setLoadingProjs(true);
    const r = await fetch("/api/projects");
    const data = await r.json();
    setProjects(Array.isArray(data) ? data : []);
    setLoadingProjs(false);
  }, []);

  const fetchLayers = useCallback(async (proj: Project) => {
    setLoadingLayers(true);
    setLayers([]);
    const r = await fetch(`/api/projects/${proj.id}/layers`);
    if (r.ok) setLayers(await r.json());
    setLoadingLayers(false);
  }, []);

  useEffect(() => { fetchProjects(); }, [fetchProjects]);
  useEffect(() => { if (activeProj) fetchLayers(activeProj); }, [activeProj, fetchLayers]);

  async function createProject() {
    if (!newName.trim()) return;
    setCreating(true);
    const r = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName.trim(), description: newDesc.trim() || null }),
    });
    if (r.ok) {
      const proj = await r.json();
      setProjects(p => [proj, ...p]);
      setActiveProj(proj);
      setNewName(""); setNewDesc(""); setShowNewProj(false);
    }
    setCreating(false);
  }

  async function deleteProject(id: string) {
    await fetch(`/api/projects/${id}`, { method: "DELETE" });
    setProjects(p => p.filter(x => x.id !== id));
    if (activeProj?.id === id) { setActiveProj(null); setLayers([]); }
    setConfirmDel(null);
  }

  async function deleteLayer(lid: string) {
    if (!activeProj) return;
    await fetch(`/api/projects/${activeProj.id}/layers/${lid}`, { method: "DELETE" });
    setLayers(l => l.filter(x => x.id !== lid));
  }

  async function uploadFile(file: File) {
    if (!activeProj) return;
    if (!file.name.toLowerCase().endsWith(".dxf")) {
      setUploadErr("Only .dxf files are accepted"); return;
    }
    setUploading(true); setUploadLog(null); setUploadErr(null);

    const fd = new FormData();
    fd.append("file", file);
    fd.append("project_id", activeProj.id);
    fd.append("category", "survey");
    fd.append("layer_type", "survey");

    const r = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) {
      setUploadErr(data.error ?? "Upload failed");
    } else {
      setUploadLog(data.log ?? "Done");
      fetchLayers(activeProj);
    }
    setUploading(false);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault(); setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  }

  return (
    <div style={s.page}>
      {gridLayer && <LayerGridViewer layerId={gridLayer} onClose={() => setGridLayer(null)} />}

      {svgUrl && (
        <SvgPlanViewer 
          url={svgUrl} 
          layerId={activeLayerId || undefined}
          onClose={() => { setSvgUrl(null); setActiveLayerId(null); }} 
        />
      )}
      {/* Topbar */}
      <div style={s.topbar}>
        <span style={s.logo}>TRENCH·FILL</span>
        <span style={{ color: "#333", fontSize: 12 }}>/</span>
        <span style={{ fontSize: 13, color: "#aaa" }}>Projects</span>
        <a href="/" style={{ ...s.backLink, marginLeft: "auto" }}>← Viewer</a>
      </div>

      <div style={s.body}>
        {/* ── Sidebar ── */}
        <div style={s.sidebar}>
          <div style={s.sideHead}>
            <span>Projects</span>
            <button style={s.btnSecondary} onClick={() => setShowNewProj(v => !v)}>+ New</button>
          </div>

          {showNewProj && (
            <div style={{ padding: "12px 14px", borderBottom: "1px solid #1a1a1a", background: "#0d0d0d" }}>
              <input style={s.input} placeholder="Project name" value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={e => e.key === "Enter" && createProject()} autoFocus />
              <input style={{ ...s.input, marginTop: 6 }} placeholder="Description (optional)" value={newDesc}
                onChange={e => setNewDesc(e.target.value)} />
              <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                <button style={s.btnPrimary} onClick={createProject} disabled={creating}>
                  {creating ? "…" : "Create"}
                </button>
                <button style={s.btnSecondary} onClick={() => setShowNewProj(false)}>Cancel</button>
              </div>
            </div>
          )}

          <div style={s.projList}>
            {loadingProjs ? (
              <div style={{ padding: 14, color: "#333", fontSize: 12 }}>Loading…</div>
            ) : projects.length === 0 ? (
              <div style={{ padding: 14, color: "#333", fontSize: 12 }}>No projects. Create one.</div>
            ) : projects.map(p => (
              <div key={p.id} style={s.projItem(activeProj?.id === p.id)} onClick={() => setActiveProj(p)}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={s.projName}>{p.name}</div>
                  <div style={s.projMeta}>{p.crs} · {new Date(p.created_at).toLocaleDateString("en-GB")}</div>
                </div>
                {confirmDel === p.id ? (
                  <div style={{ display: "flex", gap: 4 }} onClick={e => e.stopPropagation()}>
                    <button style={{ ...s.btnDanger, padding: "2px 7px", fontSize: 10 }}
                      onClick={() => deleteProject(p.id)}>Yes</button>
                    <button style={{ ...s.btnSecondary, padding: "2px 7px", fontSize: 10 }}
                      onClick={() => setConfirmDel(null)}>No</button>
                  </div>
                ) : (
                  <button style={s.delBtn} title="Delete project"
                    onClick={e => { e.stopPropagation(); setConfirmDel(p.id); }}>×</button>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* ── Main ── */}
        <div style={s.main}>
          {!activeProj ? (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <div style={{ textAlign: "center", color: "#2a2a2a", fontSize: 13 }}>
                <div style={{ fontSize: 36, marginBottom: 10 }}>▦</div>
                Select or create a project
              </div>
            </div>
          ) : (
            <>
              <div style={s.mainHead}>
                <div>
                  <div style={s.mainTitle}>{activeProj.name}</div>
                  {activeProj.description && <div style={{ fontSize: 11, color: "#444", marginTop: 2 }}>{activeProj.description}</div>}
                </div>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <button
                    style={{ ...s.btnPrimary, background: "#0f1a2e", color: "#60a5fa", border: "1px solid #1e3a5f" }}
                    onClick={() => setShowSandwich(true)}
                  >🥪 Sandwich (Z-Drill)</button>
                  <div style={{ fontSize: 10, color: "#333" }}>{activeProj.crs} · {activeProj.id.slice(0, 8)}</div>
                </div>
              </div>

              <div style={s.mainBody}>
                {/* Upload zone */}
                <div style={s.form}>
                  <div style={s.formTitle}>Upload DXF</div>
                  <div
                    style={s.drop(dragOver)}
                    onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={onDrop}
                    onClick={() => !uploading && fileRef.current?.click()}
                  >
                    <div style={{ fontSize: 24, marginBottom: 6 }}>{uploading ? "⏳" : "⬆"}</div>
                    <div style={{ color: "#555", fontSize: 11 }}>
                      {uploading ? "Processing… (may take ~30s)" : "Drag .dxf here or click to select"}
                    </div>
                  </div>
                  <input ref={fileRef} type="file" accept=".dxf" style={{ display: "none" }}
                    onChange={e => { const f = e.target.files?.[0]; if (f) uploadFile(f); e.target.value = ""; }} />
                  {uploadErr && (
                    <div style={{ padding: "8px 12px", background: "#1a0000", border: "1px solid #450a0a", borderRadius: 4, color: "#f87171", fontSize: 11, marginTop: 8 }}>
                      ✕ {uploadErr}
                    </div>
                  )}
                  {uploadLog && (
                    <pre style={{ padding: "10px 12px", background: "#001a00", border: "1px solid #14532d", borderRadius: 4, color: "#4ade80", fontSize: 10, overflowX: "auto", margin: "8px 0 0", whiteSpace: "pre-wrap" }}>
                      {uploadLog}
                    </pre>
                  )}
                </div>

                {/* Layer list */}
                <div style={{ background: "#111", border: "1px solid #222", borderRadius: 6, overflow: "hidden" }}>
                  <div style={{ padding: "9px 14px", borderBottom: "1px solid #1a1a1a", fontSize: 11, color: "#444", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ textTransform: "uppercase", letterSpacing: 1 }}>Layers</span>
                    <button style={{ ...s.btnSecondary, padding: "2px 8px", fontSize: 10 }}
                      onClick={() => fetchLayers(activeProj)}>↻ Refresh</button>
                  </div>

                  {loadingLayers ? (
                    <div style={{ padding: 14, color: "#333", fontSize: 11 }}>Loading layers…</div>
                  ) : layers.length === 0 ? (
                    <div style={{ padding: 14, color: "#333", fontSize: 11 }}>No layers. Upload a DXF file.</div>
                  ) : layers.map(l => (
                    <div key={l.id} style={{ borderBottom: "1px solid #181818" }}>
                      {/* Header row */}
                      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: "#0d0d0d" }}>
                        <div style={{ width: 8, height: 8, borderRadius: "50%", background: DOT[l.status] ?? "#555", flexShrink: 0 }} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 12, color: "#ddd", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{l.name}</div>
                          <div style={{ fontSize: 10, color: "#444", marginTop: 2 }}>
                            {l.source_file} · {new Date(l.created_at).toLocaleString("en-GB")}
                          </div>
                        </div>
                        <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 10, background: CHIP_BG[l.status] ?? "#1a1a1a", color: CHIP_FG[l.status] ?? "#555" }}>
                          {l.status}
                        </span>
                        {l.status === "interpolated" && (l.metadata as Record<string,unknown>)?.svg_path && (
                          <button
                            style={{ padding: "2px 9px", background: "#0f1a0f", color: "#4ade80", border: "1px solid #166534", borderRadius: 4, cursor: "pointer", fontFamily: "monospace", fontSize: 10, whiteSpace: "nowrap" as const }}
                            onClick={() => { 
                              setSvgUrl(String((l.metadata as Record<string,unknown>).svg_path)); 
                              setActiveLayerId(l.id); 
                            }}
                          >⬡ SVG Plane</button>
                        )}
                        <button style={{ ...s.delBtn, color: "#333" }} title="Delete layer"
                          onClick={() => deleteLayer(l.id)}>×</button>
                      </div>

                      {/* Data summary */}
                      {l.status === "interpolated" && (
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 1, background: "#1a1a1a", padding: "0 1px 1px" }}>
                          {[
                            { label: "Survey pts",  value: l.point_count.toLocaleString() },
                            { label: "Polylines",   value: l.poly_count.toLocaleString() },
                            { label: "Grid cells",  value: (l.grid_count ?? 0).toLocaleString() },
                            { label: "Z range",     value: l.z_min != null ? `${l.z_min.toFixed(2)} – ${l.z_max?.toFixed(2)}m` : "—" },
                          ].map(({ label, value }) => (
                            <div key={label} style={{ background: "#0d0d0d", padding: "8px 10px" }}>
                              <div style={{ fontSize: 9, color: "#444", textTransform: "uppercase", letterSpacing: 1, marginBottom: 3 }}>{label}</div>
                              <div style={{ fontSize: 13, color: "#86efac", fontWeight: "bold" }}>{value}</div>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Error detail */}
                      {l.status === "error" && !!(l.metadata?.error) && (
                        <pre style={{ margin: 0, padding: "8px 14px", background: "#0d0000", color: "#f87171", fontSize: 10, whiteSpace: "pre-wrap", borderTop: "1px solid #2a0000" }}>
                          {String((l.metadata as Record<string, unknown>).error)}
                        </pre>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
