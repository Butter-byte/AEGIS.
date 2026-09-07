import { useState } from "react";
import type {
  CandidateResult,
  RecoveryAction,
  RecoveryDiagnosis,
  RecoveryPhase,
  RecoveryRunResult,
  SimulationResult,
} from "../types/network";
import { OUTCOME_META } from "../lib/pipelineStages";
import DigitalTwinModal from "./DigitalTwinModal";

// Read-only recovery DETAIL view — "why did AEGIS decide this?". The high-level
// pipeline "what happened?" lives in the PipelineBar. This never calls a backend
// API, never decides an outcome, and never mutates network state.

type RecoveryPanelProps = {
  result: RecoveryRunResult | null;
  phase: RecoveryPhase;
  running: boolean;
  error: string | null;
  onClose: () => void;
};

function actionText(action: RecoveryAction): string {
  switch (action.type) {
    case "migrate_service":
      return `Migrate ${action.service_id} → ${action.to_node}`;
    case "quarantine_node":
      return `Quarantine ${action.node_id}`;
    case "drain_node":
      return `Drain ${action.node_id}`;
    case "restore_node":
      return `Restore ${action.node_id}`;
    case "reset_link":
      return `Reset link ${action.edge_id}`;
    case "reroute": {
      const avoid = [...action.avoid_nodes, ...action.avoid_edges];
      return avoid.length
        ? `Reroute ${action.service_id} (avoid ${avoid.join(", ")})`
        : `Reroute ${action.service_id}`;
    }
  }
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function signedPts(value: number): string {
  const pts = value * 100;
  return `${pts >= 0 ? "+" : ""}${pts.toFixed(1)} pts`;
}

// --- sub-blocks --------------------------------------------------------------

function DiagnosisBlock({ dx }: { dx: RecoveryDiagnosis }) {
  const [labelPart, targetPart] = dx.summary.includes(":")
    ? [dx.summary.slice(0, dx.summary.indexOf(":")), dx.summary.slice(dx.summary.indexOf(":") + 1).trim()]
    : [dx.summary, ""];
  const confPct = Math.round(dx.confidence * 100);
  const chips = [
    ...dx.suspected_nodes.map((n) => ({ kind: "node", v: n })),
    ...dx.suspected_edges.map((e) => ({ kind: "edge", v: e })),
    ...dx.suspected_services.map((s) => ({ kind: "svc", v: s })),
  ];

  return (
    <section className="rp-block">
      <div className="rp-block-head">DIAGNOSIS</div>
      <div className="rp-dx-title">{labelPart.toUpperCase()}</div>
      {targetPart && <div className="rp-dx-target">{targetPart}</div>}

      <div className="rp-conf">
        <span className="rp-conf-label">CONFIDENCE</span>
        <div className="rp-conf-bar">
          <div className="rp-conf-fill" style={{ width: `${confPct}%` }} />
        </div>
        <span className="rp-conf-val">{confPct}%</span>
      </div>

      {chips.length > 0 && (
        <div className="rp-chips">
          {chips.map((c) => (
            <span key={`${c.kind}-${c.v}`} className={`rp-chip rp-chip-${c.kind}`}>
              {c.v}
            </span>
          ))}
        </div>
      )}

      <details className="rp-why">
        <summary>Diagnosis rationale</summary>
        <p>{dx.rationale}</p>
      </details>
    </section>
  );
}

function TwinBlock({ sim }: { sim: SimulationResult }) {
  return (
    <div className="rp-sub">
      <div className="rp-sub-head">
        DIGITAL TWIN
        <span className={`rp-tag ${sim.feasible ? "rp-ok" : "rp-bad"}`}>
          {sim.feasible ? "FEASIBLE" : "INFEASIBLE"}
        </span>
      </div>
      {sim.feasible && sim.metrics ? (
        <div className="rp-metrics">
          <div>
            <span>AVAILABILITY</span>
            <strong>{pct(sim.metrics.availability)}</strong>
          </div>
          {sim.delta && (
            <div>
              <span>Δ AVAILABILITY</span>
              <strong>{signedPts(sim.delta.availability)}</strong>
            </div>
          )}
          <div>
            <span>AVG LATENCY</span>
            <strong>{sim.metrics.avg_latency.toFixed(1)} ms</strong>
          </div>
          <div>
            <span>WORST NODE LOAD</span>
            <strong>{Math.round(sim.metrics.worst_node_load * 100)}%</strong>
          </div>
        </div>
      ) : (
        <p className="rp-reason">{sim.infeasible_reason ?? "Simulation infeasible."}</p>
      )}
    </div>
  );
}

function SafetyBlock({ candidate }: { candidate: CandidateResult }) {
  const d = candidate.safety;
  return (
    <div className="rp-sub">
      <div className="rp-sub-head">
        SAFETY ENGINE
        <span className={`rp-tag ${d.approved ? "rp-ok" : "rp-bad"}`}>
          {d.approved ? "APPROVED" : "REJECTED"}
        </span>
      </div>
      {!d.approved && d.violations.length > 0 && (
        <ul className="rp-violations">
          {d.violations.map((v, i) => (
            <li key={`${v.rule}-${i}`} className={`rp-viol rp-viol-${v.level}`}>
              <span className="rp-viol-rule">{v.rule}</span>
              <span className="rp-viol-detail">{v.detail}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="rp-policy">policy {d.policy_version}</div>
    </div>
  );
}

function CandidateCard({ candidate, applied }: { candidate: CandidateResult; applied: boolean }) {
  const p = candidate.plan;
  return (
    <article className={`rp-cand ${applied ? "rp-cand-applied" : ""}`}>
      <div className="rp-cand-head">
        <div className="rp-cand-title">{p.strategy_label}</div>
        <div className="rp-cand-tags">
          <span className="rp-tag rp-neutral">{p.source}</span>
          {applied && <span className="rp-tag rp-ok">APPLIED</span>}
        </div>
      </div>
      <p className="rp-cand-rationale">{p.rationale}</p>

      <div className="rp-sub-head">ACTIONS</div>
      <ul className="rp-actions">
        {p.actions.map((a, i) => (
          <li key={`${a.type}-${i}`}>{actionText(a)}</li>
        ))}
      </ul>

      <TwinBlock sim={candidate.simulation} />
      <SafetyBlock candidate={candidate} />
    </article>
  );
}

function OutcomeBlock({ result }: { result: RecoveryRunResult }) {
  const meta = OUTCOME_META[result.outcome] ?? { label: result.outcome.toUpperCase(), kind: "bad" };
  const applied = result.outcome === "applied";
  // `no_plan` on a healthy network means "nothing to do" — the backend's raw
  // message ("no schema-valid candidate plans") reads like a failure, so show
  // its own diagnosis summary instead. Still authoritative backend text.
  const message =
    result.outcome === "no_plan" && result.diagnosis
      ? result.diagnosis.summary
      : result.message;

  return (
    <section className={`rp-outcome rp-outcome-${meta.kind}`}>
      <div className="rp-outcome-label">{meta.label}</div>
      <p className="rp-outcome-msg">{message}</p>
      {applied && result.resulting_version !== null && (
        <p className="rp-outcome-detail">Network state version: {result.resulting_version}</p>
      )}
      {!applied && <p className="rp-outcome-detail">Network unchanged.</p>}
    </section>
  );
}

// --- AI explanation (plain English) -----------------------------------------

/** Turn a recovery action into a friendly one-liner. */
function friendlyAction(action: RecoveryAction): string {
  switch (action.type) {
    case "quarantine_node":
      return `Isolated node "${action.node_id}" so it can't cause more problems.`;
    case "drain_node":
      return `Gradually moved all traffic away from "${action.node_id}".`;
    case "restore_node":
      return `Brought node "${action.node_id}" back online.`;
    case "migrate_service":
      return `Moved the "${action.service_id}" service to a healthier server ("${action.to_node}").`;
    case "reset_link":
      return `Reset the network link "${action.edge_id}" to clear its fault.`;
    case "reroute": {
      const avoidList = [...action.avoid_nodes, ...action.avoid_edges];
      return avoidList.length
        ? `Re-routed "${action.service_id}" traffic around the broken path (avoiding ${avoidList.join(", ")}).`
        : `Re-routed "${action.service_id}" to use a better network path.`;
    }
  }
}

/** Build the plain-English summary paragraph from structured result data. */
function buildExplanation(result: RecoveryRunResult): string[] {
  const lines: string[] = [];

  // 1) What was wrong?
  if (result.diagnosis) {
    const dx = result.diagnosis;
    const targets = [
      ...dx.suspected_nodes.map((n) => `node "${n}"`),
      ...dx.suspected_edges.map((e) => `link "${e}"`),
      ...dx.suspected_services.map((s) => `service "${s}"`),
    ];
    lines.push(
      targets.length > 0
        ? `AEGIS detected a problem involving ${targets.join(", ")}. The diagnosis: "${dx.summary}" (${Math.round(dx.confidence * 100)}% confidence).`
        : `AEGIS detected an issue: "${dx.summary}" (${Math.round(dx.confidence * 100)}% confidence).`,
    );
  }

  // 2) What did it do?
  const applied = result.candidates.find(
    (c) => result.applied_plan_id !== null && c.plan.id === result.applied_plan_id,
  );
  if (applied) {
    const plan = applied.plan;
    lines.push(
      `To fix this, the system used the "${plan.strategy_label}" strategy (generated by the ${plan.source === "llm" ? "AI model" : "built-in heuristic engine"}).`,
    );
    lines.push("Here's what it did, step by step:");
    plan.actions.forEach((a, i) => {
      lines.push(`  ${i + 1}. ${friendlyAction(a)}`);
    });

    // 3) Did it work?
    const sim = applied.simulation;
    if (sim.feasible && sim.delta) {
      const availDelta = sim.delta.availability * 100;
      const latDelta = sim.delta.avg_latency;
      const parts: string[] = [];
      if (Math.abs(availDelta) > 0.05) {
        parts.push(
          availDelta > 0
            ? `availability improved by ${availDelta.toFixed(1)} percentage points`
            : `availability changed by ${availDelta.toFixed(1)} percentage points`,
        );
      }
      if (Math.abs(latDelta) > 0.5) {
        parts.push(
          latDelta < 0
            ? `average latency decreased by ${Math.abs(latDelta).toFixed(1)} ms`
            : `average latency increased by ${latDelta.toFixed(1)} ms`,
        );
      }
      if (parts.length > 0) {
        lines.push(`After applying the fix: ${parts.join(", ")}.`);
      }
    }

    if (applied.safety.approved) {
      lines.push("The Safety Engine reviewed and approved the plan before it was applied.");
    }
  } else if (result.outcome === "no_plan") {
    lines.push("No issues requiring intervention were found — the network appears healthy.");
  } else if (result.outcome === "no_safe_plan") {
    lines.push("Recovery plans were generated but none passed the Safety Engine's review. The network was left unchanged to avoid risk.");
  } else if (result.outcome === "error") {
    lines.push("An error occurred during the recovery process. The network was not modified.");
  }

  return lines;
}

function AIExplanationBlock({ result }: { result: RecoveryRunResult }) {
  const lines = buildExplanation(result);
  const source = result.candidates.find(
    (c) => result.applied_plan_id !== null && c.plan.id === result.applied_plan_id,
  )?.plan.source;

  return (
    <section className="rp-block rp-explain">
      <div className="rp-block-head">
        <span>
          🤖 WHAT HAPPENED — IN SIMPLE WORDS
        </span>
        {source && (
          <span className={`rp-tag ${source === "llm" ? "rp-ai" : "rp-neutral"}`}>
            {source === "llm" ? "AI-GENERATED" : "HEURISTIC"}
          </span>
        )}
      </div>
      <div className="rp-explain-body">
        {lines.map((line, i) => (
          <p key={i} className={line.startsWith("  ") ? "rp-explain-step" : "rp-explain-text"}>
            {line}
          </p>
        ))}
      </div>
    </section>
  );
}

// --- panel -----------------------------------------------------------------

function RecoveryPanel({ result, phase, running, error, onClose }: RecoveryPanelProps) {
  const [showTwin, setShowTwin] = useState(false);

  // Does the result have at least one candidate with simulation data?
  const hasTwinData =
    result !== null &&
    result.candidates.some((c) => c.simulation.metrics !== null || c.simulation.infeasible_reason !== null);

  return (
    <div className="recovery-panel">
      <div className="rp-head">
        <div>
          <span className="rp-eyebrow">RECOVERY RUN</span>
          <h3 className="rp-run-id">{result ? result.run_id : running ? "running…" : "—"}</h3>
        </div>
        <div className="rp-head-right">
          {result && (
            <span className={`rp-badge rp-${(OUTCOME_META[result.outcome] ?? { kind: "bad" }).kind}`}>
              {(OUTCOME_META[result.outcome] ?? { label: result.outcome }).label}
            </span>
          )}
          <button className="rp-close" onClick={onClose}>
            BACK TO INSPECTOR
          </button>
        </div>
      </div>

      {running && !result && (
        <p className="rp-progress">
          {phase === "diagnosing" && "Diagnosing network fault…"}
          {phase === "simulating" && "Testing recovery plans in the Digital Twin…"}
          {phase === "evaluating" && "Evaluating the deterministic safety policy…"}
          {phase === "executing" && "Applying the approved plan…"}
          {phase === "idle" && "Starting recovery…"}
          {phase === "done" && "Finishing…"}
        </p>
      )}

      {error && (
        <div className="rp-error">
          <div className="rp-error-label">RECOVERY REQUEST FAILED</div>
          <p>{error}</p>
        </div>
      )}

      {result && (
        <div className="rp-body">
          <div className="rp-meta">
            <div>
              <span>BASED ON</span>
              <strong>v{result.based_on_version}</strong>
            </div>
            <div>
              <span>RESULT VERSION</span>
              <strong>{result.resulting_version !== null ? `v${result.resulting_version}` : "—"}</strong>
            </div>
          </div>

          {result.diagnosis ? (
            <DiagnosisBlock dx={result.diagnosis} />
          ) : (
            <section className="rp-block">
              <div className="rp-block-head">DIAGNOSIS</div>
              <p className="rp-reason">No diagnosis was produced ({result.outcome}).</p>
            </section>
          )}

          <section className="rp-block">
            <div className="rp-block-head">
              CANDIDATE RECOVERY PLANS
              <span className="rp-count">{result.candidates.length}</span>
            </div>
            {result.candidates.length === 0 ? (
              <p className="rp-reason">No candidate plans were generated.</p>
            ) : (
              result.candidates.map((c) => (
                <CandidateCard
                  key={c.plan.id}
                  candidate={c}
                  applied={result.applied_plan_id !== null && c.plan.id === result.applied_plan_id}
                />
              ))
            )}
          </section>

          <OutcomeBlock result={result} />

          {/* --- AI Explanation: plain-English summary --- */}
          <AIExplanationBlock result={result} />

          {/* --- Visualize Digital Twin button --- */}
          {hasTwinData && (
            <button
              className="rp-twin-btn"
              onClick={() => setShowTwin(true)}
            >
              🔬 VISUALIZE DIGITAL TWIN
            </button>
          )}
        </div>
      )}

      {/* Digital Twin full-screen popup */}
      {showTwin && result && (
        <DigitalTwinModal result={result} onClose={() => setShowTwin(false)} />
      )}
    </div>
  );
}

export default RecoveryPanel;
