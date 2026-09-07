import type { RecoveryPhase, RecoveryRunResult } from "../types/network";
import {
  OUTCOME_META,
  STAGE_GLYPH,
  liveStages,
  resultStages,
  stageByKey,
  type StageState,
} from "../lib/pipelineStages";

// Persistent, presentational view of the AEGIS recovery loop. Always visible so a
// judge sees the shape of the system at a glance. It renders `recoveryPhase`
// (cosmetic, from real WS events) while running and the authoritative
// `RecoveryRunResult` once it lands — it never calls an API, touches network
// state, or computes a pipeline decision.

type PipelineBarProps = {
  phase: RecoveryPhase;
  result: RecoveryRunResult | null;
  running: boolean;
  error: string | null;
};

// The 7 stages of the loop. TELEMETRY (observe) and RESULT are display-only
// bookends around the 5 stages the shared helper models.
const SPINE: { key: string; label: string }[] = [
  { key: "telemetry", label: "TELEMETRY" },
  { key: "dx", label: "DIAGNOSIS" },
  { key: "plans", label: "PLANNING" },
  { key: "twin", label: "DIGITAL TWIN" },
  { key: "safety", label: "SAFETY GATE" },
  { key: "exec", label: "EXECUTOR" },
  { key: "result", label: "RESULT" },
];

function outcomeState(kind: "ok" | "warn" | "bad" | "neutral"): StageState {
  if (kind === "ok") return "done";
  if (kind === "bad") return "fail";
  return "skip";
}

type Cell = { state: StageState; note?: string };

function cells(
  phase: RecoveryPhase,
  result: RecoveryRunResult | null,
  running: boolean,
  error: string | null,
): Cell[] {
  if (result) {
    const rs = resultStages(result);
    const meta = OUTCOME_META[result.outcome] ?? { label: result.outcome.toUpperCase(), kind: "bad" as const };
    return [
      { state: "done" }, // the pipeline ran, so state was observed
      { state: stageByKey(rs, "dx").state, note: stageByKey(rs, "dx").note },
      { state: stageByKey(rs, "plans").state, note: stageByKey(rs, "plans").note },
      { state: stageByKey(rs, "twin").state, note: stageByKey(rs, "twin").note },
      { state: stageByKey(rs, "safety").state, note: stageByKey(rs, "safety").note },
      { state: stageByKey(rs, "exec").state },
      { state: outcomeState(meta.kind), note: meta.label },
    ];
  }

  if (running) {
    const ls = liveStages(phase);
    return [
      { state: "done" },
      { state: stageByKey(ls, "dx").state },
      { state: stageByKey(ls, "plans").state },
      { state: stageByKey(ls, "twin").state },
      { state: stageByKey(ls, "safety").state },
      { state: stageByKey(ls, "exec").state },
      { state: phase === "done" ? "active" : "pending" },
    ];
  }

  // request failed before any authoritative result (e.g. backend unreachable)
  if (error) {
    return [
      { state: "skip" },
      { state: "skip" },
      { state: "skip" },
      { state: "skip" },
      { state: "skip" },
      { state: "skip" },
      { state: "fail", note: "RECOVERY FAILED" },
    ];
  }

  // idle
  return SPINE.map(() => ({ state: "pending" as StageState }));
}

function PipelineBar({ phase, result, running, error }: PipelineBarProps) {
  const row = cells(phase, result, running, error);
  const mode = result ? "complete" : error ? "error" : running ? "running" : "idle";

  return (
    <div className={`pipeline-bar pipeline-bar-${mode}`} aria-label="AEGIS recovery pipeline">
      {SPINE.map((stage, i) => {
        const cell = row[i];
        return (
          <div key={stage.key} className="pl-item">
            <div className={`pl-stage pl-${cell.state}`}>
              <span className="pl-glyph">{STAGE_GLYPH[cell.state]}</span>
              <span className="pl-label">{stage.label}</span>
              {cell.note && <span className="pl-note">{cell.note}</span>}
            </div>
            {i < SPINE.length - 1 && <span className="pl-arrow">→</span>}
          </div>
        );
      })}
    </div>
  );
}

export default PipelineBar;
