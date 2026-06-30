"use client";

import { useEffect, useState } from "react";
import { getStats } from "@/lib/api";
import type { DashboardStats } from "@/lib/types";

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getStats().then(setStats).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <p className="muted" style={{ color: "#cf222e" }}>{err}</p>;
  if (!stats) return <p className="muted">loading stats…</p>;

  const max = Math.max(1, ...stats.per_solution.map((p) => p.accepts));
  return (
    <div>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
        <div className="card">
          <div className="muted" style={{ fontSize: 12 }}>Documents reviewed</div>
          <div style={{ fontSize: 28, fontWeight: 600 }}>{stats.docs_reviewed}</div>
        </div>
        <div className="card">
          <div className="muted" style={{ fontSize: 12 }}>Pages accepted</div>
          <div style={{ fontSize: 28, fontWeight: 600 }}>{stats.pages_accepted}</div>
        </div>
        <div className="card">
          <div className="muted" style={{ fontSize: 12 }}>Solutions used</div>
          <div style={{ fontSize: 28, fontWeight: 600 }}>{stats.per_solution.length}</div>
        </div>
      </div>

      {stats.per_solution.length > 0 && (
        <div className="card" style={{ marginTop: 12 }}>
          <strong>Acceptance by solution</strong>
          <div style={{ marginTop: 6 }}>
            {stats.per_solution.map((p) => (
              <div key={p.solution} style={{ display: "grid", gridTemplateColumns: "180px 1fr 40px", gap: 8, alignItems: "center", padding: "3px 0" }}>
                <code style={{ fontSize: 12 }}>{p.solution}</code>
                <div style={{ background: "#eaeef2", height: 8, borderRadius: 4, overflow: "hidden" }}>
                  <div style={{ width: `${(p.accepts / max) * 100}%`, height: "100%", background: "#1a7f37" }} />
                </div>
                <span style={{ textAlign: "right", fontSize: 12 }}>{p.accepts}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {stats.recent.length > 0 && (
        <div className="card" style={{ marginTop: 12 }}>
          <strong>Recently reviewed</strong>
          <table style={{ marginTop: 6 }}>
            <thead><tr><th>document</th><th>pages accepted</th><th>updated</th></tr></thead>
            <tbody>
              {stats.recent.map((r) => (
                <tr key={r.document_id}>
                  <td>{r.filename}</td>
                  <td>{r.n_pages_accepted}</td>
                  <td className="muted">{r.updated_at?.slice(0, 19).replace("T", " ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
