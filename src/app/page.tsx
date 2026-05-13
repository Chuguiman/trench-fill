"use client";

import { useState } from "react";
import SurveyViewer from "@/components/SurveyViewer";
import TopoViewer from "@/components/TopoViewer";
import CivilsViewer from "@/components/CivilsViewer";
import ArchViewer from "@/components/ArchViewer";
import CorrViewer from "@/components/CorrViewer";
import DXFSVGViewer from "@/components/DXFSVGViewer";

type Tab = "survey" | "civils" | "interp" | "arch" | "corr" | "topo" | "planos";

const EXPORTS: Record<string, { file: string; label: string }> = {
  survey: { file: "XREF_Survey_Grid.dxf",         label: "Survey Grid" },
  civils: { file: "XREF_Civils_Grid.dxf",         label: "Civils Grid" },
  interp: { file: "XREF_Civils_Interp_MinZ.dxf",   label: "Civils Interp Min-Z" },
  arch:   { file: "XREF_Arch_Grid.dxf",           label: "Arch Grid" },
  corr:   { file: "XREF_Corr_SurveyCivils.dxf",   label: "Correlación" },
};

type PlanosTab = "survey" | "civils" | "interp" | "arch" | "corr";
const PLANOS: Record<PlanosTab, { file: string; label: string }> = {
  survey: { file: "XREF_Survey_Grid.dxf",       label: "Survey Grid" },
  civils: { file: "XREF_Civils_Grid.dxf",       label: "Civils Grid" },
  interp: { file: "XREF_Civils_Interp_MinZ.dxf", label: "Civils (Interp Min-Z)" },
  arch:   { file: "XREF_Arch_Grid.dxf",         label: "Arch Grid"   },
  corr:   { file: "XREF_Corr_SurveyCivils.dxf", label: "Correlación" },
};

export default function Home() {
  const [tab,       setTab]       = useState<Tab>("survey");
  const [planosTab, setPlanosTab] = useState<PlanosTab>("survey");

  const btnStyle = (active: boolean) => ({
    padding: "6px 14px",
    background: active ? "#f5c518" : "#222",
    color: active ? "#000" : "#aaa",
    border: "1px solid #444",
    cursor: "pointer",
    fontFamily: "monospace",
    fontWeight: active ? "bold" : "normal",
    fontSize: 12,
  });

  const exp = EXPORTS[tab];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <div style={{ display: "flex", gap: 3, padding: "5px 10px", background: "#111", borderBottom: "1px solid #333", alignItems: "center", flexWrap: "wrap" }}>
        <button style={btnStyle(tab === "survey")} onClick={() => setTab("survey")}>Survey</button>
        <button style={btnStyle(tab === "civils")} onClick={() => setTab("civils")}>Civils</button>
        <button style={{...btnStyle(tab === "interp"), background: tab === "interp" ? "#f39c12" : "#222"}} onClick={() => setTab("interp")}>Civils Interp (Min-Z)</button>
        <button style={btnStyle(tab === "arch")}   onClick={() => setTab("arch")}>Arch Site</button>
        <button style={btnStyle(tab === "corr")}   onClick={() => setTab("corr")}>Correlación</button>
        <button style={btnStyle(tab === "topo")}   onClick={() => setTab("topo")}>Topo DXF</button>
        <button style={{...btnStyle(tab === "planos"), borderLeft: "2px solid #555", marginLeft: 8}} onClick={() => setTab("planos")}>▦ Planos SVG</button>

        <div style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center" }}>
          <a
            href="/projects"
            style={{
              padding: "5px 12px", background: "#1a1a2e", color: "#818cf8",
              border: "1px solid #3730a3", fontFamily: "monospace", fontSize: 11,
              textDecoration: "none", borderRadius: 3,
            }}
          >
            ⬡ GIS Projects
          </a>
          {exp && (
            <a
              href={`/exports/${exp.file}`}
              download={exp.file}
              style={{
                padding: "5px 12px", background: "#1a3a1a", color: "#4ade80",
                border: "1px solid #166534", fontFamily: "monospace", fontSize: 11,
                textDecoration: "none", borderRadius: 3,
              }}
            >
              ⬇ DXF — {exp.label}
            </a>
          )}
          <a
            href="/exports/XREF_Grids_Export.zip"
            download="XREF_Grids_Export.zip"
            style={{
              padding: "5px 12px", background: "#0f3", color: "#000",
              border: "1px solid #0a0", fontFamily: "monospace", fontWeight: "bold",
              fontSize: 11, textDecoration: "none", borderRadius: 3,
            }}
          >
            ⬇ ZIP todos (436KB)
          </a>
        </div>
      </div>

      <div style={{ flex: 1, overflow: "auto" }}>
        {tab === "survey"  && <SurveyViewer />}
        {tab === "civils"  && <CivilsViewer />}
        {tab === "interp"  && (
           <div style={{ height: "100%", overflow: "hidden" }}>
             <DXFSVGViewer filename="XREF_Civils_Interp_MinZ.dxf" label="Civils Interp (Min-Z)" />
           </div>
        )}
        {tab === "arch"    && <ArchViewer />}
        {tab === "corr"    && <CorrViewer />}
        {tab === "topo"    && <TopoViewer />}
        {tab === "planos"  && (
          <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
            <div style={{ display: "flex", gap: 2, padding: "4px 8px", background: "#0f0f0f", borderBottom: "1px solid #2a2a2a" }}>
              {(Object.entries(PLANOS) as [PlanosTab, {file:string;label:string}][]).map(([k, v]) => (
                <button key={k} style={btnStyle(planosTab === k)} onClick={() => setPlanosTab(k)}>
                  {v.label}
                </button>
              ))}
            </div>
            <div style={{ flex: 1, overflow: "hidden" }}>
              <DXFSVGViewer
                key={planosTab}
                filename={PLANOS[planosTab].file}
                label={PLANOS[planosTab].label}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

