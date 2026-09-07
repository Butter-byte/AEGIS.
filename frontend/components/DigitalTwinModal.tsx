import { useEffect, useRef } from "react";
import type { CandidateResult, RecoveryRunResult, SimMetrics } from "../types/network";

// Full-screen modal that visualises the Digital Twin simulation results.
// Shows a before → after comparison of network health metrics for the
// applied (or best) candidate plan, with animated gauge bars.

type DigitalTwinModalProps = {
  result: RecoveryRunResult;
  onClose: () => void;
};

// The bar renders a horizontal fill gauge with an optional delta badge.
function MetricBar({
  label,
  before,
  after,
  unit,
  invert,
}: {
  label: string;
  before: number;
  after: number;
  unit: string;
  /** If true, a *decrease* is good (e.g. latency). */
  invert?: boolean;
}) {
  // Normalise to 0–100 for the bar width.  For percentages the value
  // is already 0–100; for latency we clamp to a 0–500 ms visual range.
  const maxRange = unit === "ms" ? 500 : 100;
  const beforePct = Math.min(100, (before / maxRange) * 100);
  const afterPct = Math.min(100, (after / maxRange) * 100);

  const diff = after - before;
  const improved = invert ? diff < -0.01 : diff > 0.01;
  const worse = invert ? diff > 0.01 : diff < -0.01;

  return (
    <div className="dtm-metric">
      <div className="dtm-metric-label">{label}</div>
      <div className="dtm-metric-bars">
        <div className="dtm-bar-row">
          <span className="dtm-bar-tag">BEFORE</span>
          <div className="dtm-bar-track">
            <div
              className="dtm-bar-fill dtm-bar-before"
              style={{ width: `${beforePct}%` }}
            />
          </div>
          <span className="dtm-bar-val">
            {before.toFixed(1)}
            {unit}
          </span>
        </div>
        <div className="dtm-bar-row">
          <span className="dtm-bar-tag">AFTER</span>
          <div className="dtm-bar-track">
            <div
              className={`dtm-bar-fill dtm-bar-after ${improved ? "dtm-bar-good" : worse ? "dtm-bar-bad" : ""}`}
              style={{ width: `${afterPct}%` }}
            />
          </div>
          <span className="dtm-bar-val">
            {after.toFixed(1)}
            {unit}
          </span>
        </div>
      </div>
      {Math.abs(diff) > 0.01 && (
        <span className={`dtm-delta ${improved ? "dtm-delta-good" : "dtm-delta-bad"}`}>
          {diff > 0 ? "+" : ""}
          {diff.toFixed(1)}
          {unit}
        </span>
      )}
    </div>
  );
}

function StatusNode({
  id,
  status,
  changed,
}: {
  id: string;
  status: string;
  changed?: boolean;
}) {
  return (
    <div className={`dtm-node dtm-node-${status} ${changed ? "dtm-node-changed" : ""}`}>
      <span className="dtm-node-dot" />
      <span className="dtm-node-id">{id}</span>
      <span className="dtm-node-status">{status}</span>
    </div>
  );
}

function DigitalTwinModal({ result, onClose }: DigitalTwinModalProps) {
  const backdropRef = useRef<HTMLDivElement>(null);

  // Close on Escape key.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Find the applied candidate (or the first feasible one).
  const appliedCandidate: CandidateResult | null =
    result.candidates.find(
      (c) => result.applied_plan_id !== null && c.plan.id === result.applied_plan_id,
    ) ??
    result.candidates.find((c) => c.simulation.feasible) ??
    result.candidates[0] ??
    null;

  if (!appliedCandidate) {
    return (
      <div className="dtm-backdrop" ref={backdropRef} onClick={(e) => e.target === backdropRef.current && onClose()}>
        <div className="dtm-modal">
          <div className="dtm-header">
            <h3>Digital Twin Visualization</h3>
            <button className="dtm-close" onClick={onClose}>✕</button>
          </div>
          <p className="dtm-empty">No candidate plans to visualize.</p>
        </div>
      </div>
    );
  }

  const sim = appliedCandidate.simulation;
  const plan = appliedCandidate.plan;
  const isApplied = result.applied_plan_id === plan.id;

  // Reconstruct "before" metrics from post-metrics + delta (if available).
  const postMetrics: SimMetrics | null = sim.metrics;
  const delta = sim.delta;

  const beforeAvail = postMetrics && delta ? postMetrics.availability - delta.availability : null;
  const afterAvail = postMetrics?.availability ?? null;

  const beforeLatency = postMetrics && delta ? postMetrics.avg_latency - delta.avg_latency : null;
  const afterLatency = postMetrics?.avg_latency ?? null;

  const beforeMaxLat = postMetrics && delta ? postMetrics.max_latency - delta.max_latency : null;
  const afterMaxLat = postMetrics?.max_latency ?? null;

  // Nodes / edges mentioned in diagnosis + actions → these are the "affected" elements.
  const affectedNodes = new Set<string>();
  const affectedEdges = new Set<string>();
  if (result.diagnosis) {
    result.diagnosis.suspected_nodes.forEach((n) => affectedNodes.add(n));
    result.diagnosis.suspected_edges.forEach((e) => affectedEdges.add(e));
  }
  plan.actions.forEach((a) => {
    if ("node_id" in a) affectedNodes.add(a.node_id);
    if ("edge_id" in a) affectedEdges.add(a.edge_id);
    if ("to_node" in a) affectedNodes.add(a.to_node);
    if ("service_id" in a) {
      // Show the service as a node in the visual.
      affectedNodes.add(a.service_id);
    }
  });

  // Action descriptions in simple form for the flow diagram.
  const actionSteps = plan.actions.map((a, i) => {
    let icon = "⚙️";
    let text = "";
    switch (a.type) {
      case "quarantine_node":
        icon = "🔒";
        text = `Isolate ${a.node_id}`;
        break;
      case "drain_node":
        icon = "📤";
        text = `Drain traffic from ${a.node_id}`;
        break;
      case "restore_node":
        icon = "♻️";
        text = `Restore ${a.node_id}`;
        break;
      case "migrate_service":
        icon = "📦";
        text = `Move ${a.service_id} → ${a.to_node}`;
        break;
      case "reset_link":
        icon = "🔗";
        text = `Reset link ${a.edge_id}`;
        break;
      case "reroute":
        icon = "🔀";
        text = `Reroute ${a.service_id}`;
        break;
    }
    return { icon, text, key: `${a.type}-${i}` };
  });

  return (
    <div
      className="dtm-backdrop"
      ref={backdropRef}
      onClick={(e) => e.target === backdropRef.current && onClose()}
    >
      <div className="dtm-modal">
        {/* Header */}
        <div className="dtm-header">
          <div>
            <span className="dtm-eyebrow">DIGITAL TWIN SIMULATION</span>
            <h3>
              {plan.strategy_label}
              <span className={`dtm-badge ${isApplied ? "dtm-badge-applied" : sim.feasible ? "dtm-badge-feasible" : "dtm-badge-infeasible"}`}>
                {isApplied ? "APPLIED" : sim.feasible ? "FEASIBLE" : "INFEASIBLE"}
              </span>
            </h3>
          </div>
          <button className="dtm-close" onClick={onClose}>✕</button>
        </div>

        <div className="dtm-content">
          {/* Left column: Metrics comparison */}
          <div className="dtm-col-metrics">
            <div className="dtm-section-title">HEALTH METRICS — BEFORE vs AFTER</div>
            {beforeAvail !== null && afterAvail !== null && (
              <MetricBar
                label="Availability"
                before={beforeAvail * 100}
                after={afterAvail * 100}
                unit="%"
              />
            )}
            {beforeLatency !== null && afterLatency !== null && (
              <MetricBar
                label="Avg Latency"
                before={beforeLatency}
                after={afterLatency}
                unit=" ms"
                invert
              />
            )}
            {beforeMaxLat !== null && afterMaxLat !== null && (
              <MetricBar
                label="Max Latency"
                before={beforeMaxLat}
                after={afterMaxLat}
                unit=" ms"
                invert
              />
            )}
            {postMetrics && (
              <div className="dtm-metric-extras">
                <div>
                  <span>WORST NODE LOAD</span>
                  <strong>{Math.round(postMetrics.worst_node_load * 100)}%</strong>
                </div>
                <div>
                  <span>PATHS RESOLVED</span>
                  <strong>{postMetrics.path_count}</strong>
                </div>
                {postMetrics.unreachable_services.length > 0 && (
                  <div className="dtm-unreachable">
                    <span>UNREACHABLE</span>
                    <strong>{postMetrics.unreachable_services.join(", ")}</strong>
                  </div>
                )}
              </div>
            )}
            {!postMetrics && (
              <div className="dtm-infeasible-box">
                <span className="dtm-infeasible-icon">✕</span>
                <div>
                  <strong>Simulation Infeasible</strong>
                  <p>{sim.infeasible_reason ?? "The recovery plan could not produce a viable network state."}</p>
                </div>
              </div>
            )}
          </div>

          {/* Right column: Action flow + affected nodes */}
          <div className="dtm-col-flow">
            <div className="dtm-section-title">RECOVERY ACTION FLOW</div>
            <div className="dtm-flow">
              {actionSteps.map((step, i) => (
                <div key={step.key} className="dtm-flow-step">
                  <div className="dtm-flow-connector">
                    <div className={`dtm-flow-dot ${i === actionSteps.length - 1 ? "dtm-flow-dot-last" : ""}`} />
                    {i < actionSteps.length - 1 && <div className="dtm-flow-line" />}
                  </div>
                  <div className="dtm-flow-content">
                    <span className="dtm-flow-icon">{step.icon}</span>
                    <span className="dtm-flow-text">{step.text}</span>
                  </div>
                </div>
              ))}
            </div>

            <div className="dtm-section-title" style={{ marginTop: 20 }}>AFFECTED COMPONENTS</div>
            <div className="dtm-nodes-grid">
              {[...affectedNodes].map((id) => (
                <StatusNode
                  key={id}
                  id={id}
                  status={result.diagnosis?.suspected_nodes.includes(id) ? "faulty" : "target"}
                  changed
                />
              ))}
              {[...affectedEdges].map((id) => (
                <StatusNode
                  key={id}
                  id={id}
                  status="edge"
                  changed
                />
              ))}
            </div>
          </div>
        </div>

        {/* Source badge */}
        <div className="dtm-footer">
          <span className="dtm-source">
            Plan source: <strong>{plan.source.toUpperCase()}</strong>
          </span>
          <span className="dtm-timestamp">
            Simulated at {new Date(sim.computed_at).toLocaleTimeString()}
          </span>
        </div>
      </div>
    </div>
  );
}

export default DigitalTwinModal;
