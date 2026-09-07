import type {
  CandidateResult,
  RecoveryAction,
  RecoveryDiagnosis,
  RecoveryPhase,
  RecoveryRunResult,
  RunOutcome,
  SimulationResult,
} from "../types/network";

// Read-only recovery console. Receives the authoritative RecoveryRunResult and
// the live progress phase; renders both. It never calls a backend API, never
// decides an outcome, and never mutates network state.

type RecoveryPanelProps = {
  result: RecoveryRunResult | null;
  phase: RecoveryPhase;
  running: boolean;
  error: string | null;
  onClose: () => void;
};

const OUTCOME_META: Record<RunOutcome, { label: string; kind: "ok" | "warn" | "bad" | "neutral" }> = {
  applied: { label: "APPLIED", kind: "ok" },
  approved_pending: { label: "APPROVED — NOT EXECUTED", kind: "warn" },
  no_plan: { label: "NO RECOVERY REQUIRED", kind: "neutral" },
  no_safe_plan: { label: "NO SAFE PLAN", kind: "bad" },
  diagnosis_failed: { label: "DIAGNOSIS FAILED", kind: "bad" },
  error: { label: "RECOVERY ERROR", kind: "bad" },
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

// --- pipeline stage model -------------------------------------------------

type StageState = "done" | "fail" | "skip" | "active" | "pending";
type Stage = { key: string; label: string; state: StageState; note?: string };

const PHASE_ORDER: RecoveryPhase[] = [
  "idle",
  "diagnosing",
  "simulating",
  "evaluating",
  "executing",
  "done",
];

function liveStages(phase: RecoveryPhase): Stage[] {
  const idx = PHASE_ORDER.indexOf(phase);
  const at = (needed: RecoveryPhase): StageState => {
    const n = PHASE_ORDER.indexOf(needed);
    if (idx > n) return "done";
    if (idx === n) return "active";
    return "pending";
  };
  return [
    { key: "dx", label: "Diagnosis", state: at("diagnosing") },
    { key: "plans", label: "Candidate plans", state: at("simulating") },
    { key: "twin", label: "Digital Twin", state: at("simulating") },
    { key: "safety", label: "Safety Engine", state: at("evaluating") },
    { key: "exec", label: "Execution", state: at("executing") },
    { key: "final", label: "Final state", state: at("done") },
  ];
}

function resultStages(result: RecoveryRunResult): Stage[] {
  const cands = result.candidates;
  const anyFeasible = cands.some((c) => c.simulation.feasible);
  const anyApproved = cands.some((c) => c.safety.approved);

  const dx: Stage =
    result.outcome === "diagnosis_failed"
      ? { key: "dx", label: "Diagnosis", state: "fail" }
      : result.diagnosis
        ? { key: "dx", label: "Diagnosis", state: "done" }
        : { key: "dx", label: "Diagnosis", state: "skip" };

  const plans: Stage =
    cands.length > 0
      ? { key: "plans", label: "Candidate plans", state: "done", note: `${cands.length}` }
      : { key: "plans", label: "Candidate plans", state: "skip", note: "none" };

  const twin: Stage =
    cands.length === 0
      ? { key: "twin", label: "Digital Twin", state: "skip" }
      : anyFeasible
        ? { key: "twin", label: "Digital Twin", state: "done" }
        : { key: "twin", label: "Digital Twin", state: "fail", note: "all infeasible" };

  const safety: Stage =
    cands.length === 0
      ? { key: "safety", label: "Safety Engine", state: "skip" }
      : anyApproved
        ? { key: "safety", label: "Safety Engine", state: "done" }
        : { key: "safety", label: "Safety Engine", state: "fail", note: "no safe plan" };

  const exec: Stage =
    result.outcome === "applied"
      ? { key: "exec", label: "Execution", state: "done" }
      : result.outcome === "error"
        ? { key: "exec", label: "Execution", state: "fail" }
        : { key: "exec", label: "Execution", state: "skip", note: "—" };

  const final: Stage =
    result.outcome === "applied"
      ? {
          key: "final",
          label: "Final state",
          state: "done",
          note: result.resulting_version !== null ? `v${result.resulting_version}` : undefined,
        }
      : { key: "final", label: "Final state", state: "skip", note: "unchanged" };

  return [dx, plans, twin, safety, exec, final];
}

const STAGE_GLYPH: Record<StageState, string> = {
  done: "✓",
  fail: "✕",
  skip: "—",
  active: "●",
  pending: "○",
};

function Stepper({ stages }: { stages: Stage[] }) {
  return (
    <ol className="rp-steps">
      {stages.map((s) => (
        <li key={s.key} className={`rp-step rp-step-${s.state}`}>
          <span className="rp-step-glyph">{STAGE_GLYPH[s.state]}</span>
          <span className="rp-step-label">{s.label}</span>
          {s.note && <span className="rp-step-note">{s.note}</span>}
        </li>
      ))}
    </ol>
  );
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

  return (
    <section className={`rp-outcome rp-outcome-${meta.kind}`}>
      <div className="rp-outcome-label">{meta.label}</div>
      <p className="rp-outcome-msg">{result.message}</p>
      {applied && result.resulting_version !== null && (
        <p className="rp-outcome-detail">Network state version: {result.resulting_version}</p>
      )}
      {!applied && <p className="rp-outcome-detail">Network unchanged.</p>}
    </section>
  );
}

// --- panel -----------------------------------------------------------------

function RecoveryPanel({ result, phase, running, error, onClose }: RecoveryPanelProps) {
  const stages = result ? resultStages(result) : liveStages(phase);

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

      <Stepper stages={stages} />

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
        </div>
      )}
    </div>
  );
}

export default RecoveryPanel;
