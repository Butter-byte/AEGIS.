// Shared pipeline-stage model — moved verbatim from RecoveryPanel so both the
// PipelineBar (system view) and the RecoveryPanel (detail view) render the same
// stages from one place. Pure functions over RecoveryPhase / RecoveryRunResult.
//
// This DISPLAYS the backend's decisions. It never computes a diagnosis, a plan,
// feasibility, or a safety verdict — it reads authoritative fields
// (`diagnosis`, `candidates[].simulation.feasible`, `candidates[].safety.approved`,
// `outcome`) and maps them to glyph states.

import type { RecoveryPhase, RecoveryRunResult, RunOutcome } from "../types/network";

export type StageState = "done" | "fail" | "skip" | "active" | "pending";
export type Stage = { key: string; label: string; state: StageState; note?: string };

export const STAGE_GLYPH: Record<StageState, string> = {
  done: "✓",
  fail: "✕",
  skip: "—",
  active: "●",
  pending: "○",
};

// outcome -> human label + severity. Shared by the PipelineBar RESULT stage and
// the RecoveryPanel header badge / outcome block.
export const OUTCOME_META: Record<
  RunOutcome,
  { label: string; kind: "ok" | "warn" | "bad" | "neutral" }
> = {
  applied: { label: "APPLIED", kind: "ok" },
  approved_pending: { label: "APPROVED — NOT EXECUTED", kind: "warn" },
  no_plan: { label: "NO RECOVERY REQUIRED", kind: "neutral" },
  no_safe_plan: { label: "NO SAFE PLAN", kind: "bad" },
  diagnosis_failed: { label: "DIAGNOSIS FAILED", kind: "bad" },
  error: { label: "RECOVERY ERROR", kind: "bad" },
};

const PHASE_ORDER: RecoveryPhase[] = [
  "idle",
  "diagnosing",
  "simulating",
  "evaluating",
  "executing",
  "done",
];

// Live progress, driven only by the cosmetic `recoveryPhase` (which advances from
// real WS events). The authoritative result replaces this the moment it lands.
export function liveStages(phase: RecoveryPhase): Stage[] {
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

// Completed stage states, derived purely from the authoritative RecoveryRunResult.
export function resultStages(result: RecoveryRunResult): Stage[] {
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

// Small typed lookup so callers can pull a stage by key without `| undefined`.
export function stageByKey(stages: Stage[], key: string): Stage {
  return stages.find((s) => s.key === key) ?? { key, label: key, state: "pending" };
}
