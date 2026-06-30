"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { acceptCategory, getReview, getRun, pdfUrl, rejectCategory, reportHtmlUrl, reportPdfUrl, resumeRun, revokeCategory, startRun, unrejectCategory } from "@/lib/api";
import type { Category, ReviewRecord, RunState, SolutionLifecycle } from "@/lib/types";
import { SolutionCompareGrid, type SolutionTile, type CategoryEditPayload } from "@/components/SolutionCompareGrid";
import { RunBpmnSection } from "@/components/RunBpmnSection";
import { PiiBenchmarkSection } from "@/components/PiiBenchmarkSection";

export default function RunPage() {
  const { runId } = useParams<{ runId: string }>();
  const router = useRouter();
  const [run, setRun] = useState<RunState | null>(null);
  const [review, setReview] = useState<ReviewRecord | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [rerunning, setRerunning] = useState(false);

  useEffect(() => {
    if (!runId) return;
    let stop = false;
    async function tick() {
      try {
        const data = await getRun(runId);
        if (!stop) setRun(data);
        if (data.status !== "done" && !stop) setTimeout(tick, 1500);
      } catch (e) {
        if (!stop) setErr(String(e));
      }
    }
    tick();
    return () => { stop = true; };
  }, [runId]);

  useEffect(() => {
    if (!run) return;
    getReview(run.document.document_id).then(setReview).catch(() => setReview(null));
  }, [run]);

  const nPages = useMemo(() => run?.document?.n_pages ?? 1, [run]);
  const pageReview = review?.pages?.[String(pageIndex)];

  const tiles: SolutionTile[] = useMemo(() => {
    if (!run) return [];
    return (run.solution_names ?? []).map((name) => {
      const result = (run.solution_results ?? []).find((r) => r.solution_name === name);
      const entry = run.solution_status?.[name];
      const status: SolutionLifecycle = entry?.state ?? (result ? "done" : "pending");
      return { name, status, entry, result };
    });
  }, [run]);

  const onAcceptCategory = useCallback(async (sol: string, payload: CategoryEditPayload) => {
    if (!run) return;
    try {
      const updated = await acceptCategory(run.document.document_id, pageIndex, payload.category, sol, runId, {
        order: payload.order,
        comment: payload.comment,
      });
      setReview(updated);
    } catch (e) { setErr(String(e)); }
  }, [run, runId, pageIndex]);

  const onRevokeCategory = useCallback(async (sol: string, category: Category) => {
    if (!run) return;
    try {
      const updated = await revokeCategory(run.document.document_id, pageIndex, category, sol);
      setReview(updated);
    } catch (e) { setErr(String(e)); }
  }, [run, pageIndex]);

  const onRejectCategory = useCallback(async (sol: string, category: Category, reason: string) => {
    if (!run) return;
    try {
      const updated = await rejectCategory(run.document.document_id, pageIndex, category, sol, runId, reason, run.document.filename);
      setReview(updated);
    } catch (e) { setErr(String(e)); }
  }, [run, runId, pageIndex]);

  const onUnrejectCategory = useCallback(async (sol: string, category: Category) => {
    if (!run) return;
    try {
      const updated = await unrejectCategory(run.document.document_id, pageIndex, category, sol);
      setReview(updated);
    } catch (e) { setErr(String(e)); }
  }, [run, pageIndex]);

  if (err) return <main className="container"><p style={{ color: "#cf222e" }}>{err}</p></main>;
  if (!run) return <main className="container"><p className="muted">loading run…</p></main>;

  const reviewedPages = review
    ? Object.values(review.pages).filter((p) => p && (p.solution || Object.keys(p.categories ?? {}).length > 0)).length
    : 0;

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1 style={{ marginBottom: 4 }}>Run {runId}</h1>
          <div className="muted" style={{ fontSize: 13 }}>
            <strong>{run.document.filename}</strong> · kind {run.document.pdf_kind} · {run.document.n_pages} pages ·{" "}
            <span className={`pill ${run.status === "done" ? "ok" : "running"}`}>{run.status}</span>{" "}
            {reviewedPages > 0 && (
              <span className="pill ok">{reviewedPages}/{nPages} pages accepted</span>
            )}
          </div>
        </div>
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          <Link className="btn" href="/">← home</Link>
          <a className="btn" href={pdfUrl(run.document.document_id)} target="_blank" rel="noreferrer">view PDF ↗</a>
          <Link className="btn" href={`/documents/${encodeURIComponent(run.document.document_id)}/history`}>history</Link>
          <Link className="btn" href={`/documents/${encodeURIComponent(run.document.document_id)}/benchmark`}>benchmark</Link>
          <button
            className="btn"
            disabled={rerunning || run.status !== "done"}
            onClick={async () => {
              if (!run) return;
              setRerunning(true);
              try {
                const { run_id } = await startRun(run.document.document_id, run.solution_names);
                router.push(`/runs/${run_id}`);
              } catch (e) {
                setErr(String(e));
                setRerunning(false);
              }
            }}
            title="re-run this document with the same solutions"
          >
            {rerunning ? "starting…" : "re-run ↻"}
          </button>
          {(() => {
            const sols = Object.values(run.solution_status ?? {}) as {
              state?: string;
              result_status?: string;
              n_pages_done?: number;
              n_pages_expected?: number;
            }[];
            const failed = sols.filter(
              (s) =>
                s.state === "error" ||
                s.state === "partial" ||
                s.result_status === "error" ||
                s.result_status === "partial" ||
                // Safety net — solution reported "done" but the page count
                // came up short (e.g., a non-recovered page-loop timeout
                // where partial_stages didn't get signalled).
                (
                  typeof s.n_pages_done === "number" &&
                  typeof s.n_pages_expected === "number" &&
                  s.n_pages_expected > 0 &&
                  s.n_pages_done < s.n_pages_expected
                ),
            );
            if (failed.length === 0) return null;
            return (
              <button
                className="btn primary"
                disabled={rerunning || run.status === "running"}
                onClick={async () => {
                  setRerunning(true);
                  try {
                    await resumeRun(runId);
                  } catch (e) {
                    setErr(String(e));
                  } finally {
                    setRerunning(false);
                  }
                }}
                title="re-run only the failed / partial solutions on this same run_id"
              >
                Resume {failed.length} failed ▶
              </button>
            );
          })()}
          <a className="btn" href={reportHtmlUrl(runId)} target="_blank" rel="noreferrer">report.html</a>
          <a className="btn" href={reportPdfUrl(runId)} target="_blank" rel="noreferrer">report.pdf</a>
        </div>
      </div>

      <div className="row" style={{ marginTop: 12, alignItems: "center", flexWrap: "wrap", overflowX: "auto", maxWidth: "100%", padding: "4px 0" }}>
        <span>page:</span>
        {Array.from({ length: nPages }).map((_, i) => {
          const pr = review?.pages?.[String(i)];
          const nCats = pr ? Object.keys(pr.categories ?? {}).length : 0;
          const hasAny = !!pr && (!!pr.solution || nCats > 0);
          return (
            <button
              key={i}
              className={`btn ${i === pageIndex ? "primary" : ""}`}
              onClick={() => setPageIndex(i)}
              title={nCats ? `${nCats}/4 categories accepted` : undefined}
              style={hasAny ? { borderColor: "#1a7f37" } : undefined}
            >
              {i + 1}{nCats > 0 ? ` ${nCats}/4` : ""}
            </button>
          );
        })}
      </div>

      {run.solution_results && run.solution_results.length > 0 && (
        <details open style={{ marginTop: 16 }}>
          <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 13, marginBottom: 8 }}>
            Pipeline execution flow
          </summary>
          <RunBpmnSection results={run.solution_results} />
        </details>
      )}

      {run.pii_v2_run_id && (
        <details open style={{ marginTop: 16 }}>
          <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 13, marginBottom: 8 }}>
            PII benchmark · paired run
          </summary>
          <PiiBenchmarkSection
            piiRunId={run.pii_v2_run_id}
            pageIndex={pageIndex}
            documentId={run.document.document_id}
          />
        </details>
      )}

      <div style={{ marginTop: 16 }}>
        <SolutionCompareGrid
          runId={runId}
          pageIndex={pageIndex}
          tiles={tiles}
          pageReview={pageReview}
          piiV2RunId={run.pii_v2_run_id ?? null}
          onAcceptCategory={onAcceptCategory}
          onRevokeCategory={onRevokeCategory}
          onRejectCategory={onRejectCategory}
          onUnrejectCategory={onUnrejectCategory}
          onResumeSolution={async (solutionName) => {
            try {
              await resumeRun(runId, [solutionName]);
            } catch (e) {
              setErr(String(e));
            }
          }}
        />
      </div>
    </main>
  );
}
