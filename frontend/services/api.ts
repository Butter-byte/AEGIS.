import type { NetworkState, RecoveryRunResult, Telemetry } from "../types/network";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function getTelemetry(): Promise<Telemetry> {
    const response = await fetch(`${API_URL}/telemetry`);

    if (!response.ok) {
        throw new Error(`Telemetry request failed: ${response.status}`);
    }

    return (await response.json()) as Telemetry;
}

export async function getNetworkState(): Promise<NetworkState> {
    const response = await fetch(`${API_URL}/network/state`);

    if (!response.ok) {
        throw new Error(`Network state request failed: ${response.status}`);
    }

    return (await response.json()) as NetworkState;
}

export async function resetNetwork(): Promise<void> {
    const response = await fetch(`${API_URL}/network/reset`, { method: "POST" });

    if (!response.ok) {
        throw new Error(`Network reset failed: ${response.status}`);
    }
    // The rebuilt NetworkState arrives over the WebSocket `state` stream; the
    // caller must not construct or assume state locally.
}

export type FaultType =
    | "kill_node"
    | "degrade_node"
    | "overload_node"
    | "cut_edge"
    | "congest_edge"
    | "traffic_spike";

export async function injectFault(
    type: FaultType,
    target: string,
): Promise<void> {
    const response = await fetch(`${API_URL}/faults`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            type,
            target,
        }),
    });

    if (!response.ok) {
        throw new Error(`Fault injection failed: ${response.status}`);
    }
}

export async function runRecovery(): Promise<RecoveryRunResult> {
    const response = await fetch(`${API_URL}/recovery/run`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            auto_apply: true,
        }),
    });

    if (!response.ok) {
        throw new Error(`Recovery request failed: ${response.status}`);
    }

    const data: unknown = await response.json();

    // Lightweight runtime shape guard — a malformed body must never be treated
    // as a successful recovery.
    if (
        typeof data !== "object" ||
        data === null ||
        typeof (data as RecoveryRunResult).outcome !== "string" ||
        !Array.isArray((data as RecoveryRunResult).candidates)
    ) {
        throw new Error("Recovery response could not be read");
    }

    return data as RecoveryRunResult;
}