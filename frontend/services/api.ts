const API_URL = "http://localhost:8000";

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

export async function runRecovery(): Promise<void> {
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
}