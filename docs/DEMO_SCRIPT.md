# AEGIS — Hackathon Demo Script

Three scenarios, ~5 minutes total. Run them in order.

**Setup:** `docker compose up --build` → open `http://localhost:5173`. The dashboard
shows the **AEGIS pipeline spine** (top strip:
`TELEMETRY → DIAGNOSIS → PLANNING → DIGITAL TWIN → SAFETY GATE → EXECUTOR → RESULT`),
the live network topology, telemetry, a Fault Injection panel, and an Event Log.

**The pipeline spine is your visual anchor.** It is always visible. While a
recovery runs it lights up left→right from real backend events; when the run
finishes it shows the backend's verdict for every stage (✓ / ✕ / —).

**The operational timeline.** Top-right of the header shows connection status —
`SYSTEM OPERATIONAL` (green), `RECOVERY IN PROGRESS` (amber), or
`BACKEND DISCONNECTED` (red) if the WebSocket drops. The **SYSTEM EVENTS** log
(bottom-left) is a live feed of *real* events only: your fault injections, a
`RUN RECOVERY` / `NETWORK RESET` divider each time you start one, and the
backend's own diagnosis / Digital Twin / Safety Gate / outcome events as they
fire. Nothing in it is fabricated or timed — if the log is quiet, the system is
quiet. It clears to a single `NETWORK RESET` line on every reset, so each
scenario starts from an empty timeline.

**Resetting between scenarios:** click **RESET NETWORK** (top-right of the dashboard).
The topology snaps back to a clean 15-node baseline over WebSocket within a second,
any recovery result on screen is cleared, and the SYSTEM EVENTS log resets to a
single `NETWORK RESET` line. Do this before every scenario.

**One-line pitch (say this first):**
> "AEGIS is an autonomous network-recovery engine. AI diagnoses faults and *proposes*
> fixes — but a proposed fix never touches the network. Every plan is simulated in a
> Digital Twin and cleared by a deterministic Safety Gate before anything executes.
> Let me show you three things: a recovery, a different kind of recovery, and — most
> importantly — a recovery that AEGIS *refuses* to run."

---

## Scenario 1 — Node Failure

**Click sequence**

1. **RESET NETWORK**.
2. Click node **N2** in the topology (it highlights; the Fault panel shows `NODE N2`).
3. Click **Kill Node**.
4. Click **RUN RECOVERY** (Fault panel) — or **TRIGGER RECOVERY** in the node inspector.

**What to point at**

- **On step 3:** N2 turns **red**. Telemetry: `AVAILABILITY` drops (100% → 93%),
  `ACTIVE NODES` 15 → 14. This is real backend state over WebSocket — the frontend
  never invented it.
- **On step 4**, point at the **pipeline spine** — watch
  `DIAGNOSIS → DIGITAL TWIN → SAFETY GATE → EXECUTOR → RESULT` light up and finish
  **all ✓**, with `RESULT ✓ APPLIED`.
- Then the Recovery panel (detail) shows *why*:
  - **Diagnosis** — `NODE OR INTERFACE FAILURE / N2`, confidence 90%, suspect chips.
  - **Candidate plan** — *"isolate N2 and relocate its services"*: `Migrate svc-auth → N1`,
    then `Quarantine N2`.
  - **Digital Twin** — `FEASIBLE`, worst node load 45%.
  - **Safety Engine** — `APPROVED`, no violations.
  - **Outcome** — `RECOVERY APPLIED`, *Network state version: N*.
- The topology updates: **N2 is now quarantined** (slate) and its incident links
  are cut — the failure is *contained*, and `svc-auth` has moved to a healthy node.
  (The node stays isolated on purpose; AEGIS didn't pretend the hardware healed.)
- **Glance at SYSTEM EVENTS:** `Fault injected — kill_node on N2`, a `RUN RECOVERY`
  divider, then `Diagnosis → Digital Twin feasible → Safety Gate APPROVED →
  Recovery complete — applied`, newest on top. That is the whole pipeline as a
  readable log.

**Narration**

> "N2 fails. AEGIS diagnoses a node failure, proposes moving the affected service and
> isolating the node, simulates that in the Digital Twin, the Safety Gate approves it,
> and only *then* the executor applies it. The failure is contained and the service
> keeps running — and every step is on screen, on the pipeline spine."

---

## Scenario 2 — Congestion

> **Do NOT use "Traffic Spike" for this scenario.** Traffic Spike is a node-overload
> fault and produces a *"Network device overload"* diagnosis. Congestion needs
> **Congest Link**.

**Click sequence**

1. **RESET NETWORK**.
2. Click the **edge N1–N2** in the topology (it highlights; the Fault panel shows `LINK N1-N2`).
3. Click **Congest Link**.
4. Click **RUN RECOVERY** in the Fault panel.
   *(The link is selected, not a node — this is why RUN RECOVERY is always available.)*

**What to point at**

- **On step 3:** the N1–N2 link turns **amber and animated**; `LINK FAULTS` telemetry
  ticks to `1` — the backend marked the edge congested (95% utilisation).
- **On step 4**, point at the **pipeline spine**:
  `DIAGNOSIS` identifies congestion → `DIGITAL TWIN` validates → `SAFETY GATE` approves
  → `EXECUTOR ✓` → `RESULT ✓ APPLIED`.
- Then the Recovery panel (detail):
  - **Diagnosis** — `NETWORK CONGESTION / N1-N2`, confidence 90%.
  - **Candidate plan** — *"reroute services off N1-N2 and reset it"*:
    `Reroute svc-auth (avoid N1-N2)`, then `Reset link N1-N2`.
  - **Digital Twin** — `FEASIBLE`.
  - **Safety Engine** — `APPROVED`.
  - **Outcome** — `RECOVERY APPLIED`.
- The N1–N2 link returns to **normal grey** and `LINK FAULTS` returns to `0` — the
  congestion is actually cleared, not just marked "done".

**Narration**

> "Same pipeline, a completely different fault. AEGIS recognises congestion rather
> than a hard failure, proposes steering traffic away and resetting the link, the
> Twin and Safety Gate clear it, and the link goes back to normal."

---

## Scenario 3 — Unsafe Recovery (the important one)

This proves AEGIS does **not** blindly execute AI output.

**Click sequence**

1. **RESET NETWORK**.
2. Click node **N7** → click **Overload Node**.
3. Click node **N1** → click **Overload Node**.
4. Click **RUN RECOVERY**.

**What to point at**

- **After steps 2–3:** N7 and N1 both turn **amber** (`degraded`, 95% load).
- **On step 4 — point at the pipeline spine and pause here:**

  ```
  TELEMETRY ✓   DIAGNOSIS ✓   PLANNING ✓   DIGITAL TWIN ✓   SAFETY GATE ✕   EXECUTOR —   RESULT ✕ NO SAFE PLAN
  ```

  The Safety Gate turned it back. The Executor never ran (`—`).
- Then the Recovery panel (detail) shows why:
  - **Diagnosis** — `NETWORK DEVICE OVERLOAD / N1, N7`.
  - **Candidate plans** — **four** of them (restore / quarantine / migrate variants).
  - **Digital Twin** — each is `FEASIBLE`…
  - **Safety Engine** — **every single one is `REJECTED`**, each with a **critical**
    `node_load_limit` violation: *"worst load ratio 0.950 above 0.900"*.
  - **Outcome** — big red **`NO SAFE PLAN`** · *"Network unchanged."*
- Point back at the topology: **N7 and N1 are still amber.** Nothing moved — the
  network state version is unchanged by the recovery run.

- **SYSTEM EVENTS** makes it undeniable: four `Digital Twin — … feasible` lines
  followed by four `Safety Gate — … REJECTED` lines, then
  `Recovery complete — no_safe_plan`. Every rejection is a real backend event.

**Emphasize:** the AI proposed four recoveries; AEGIS executed **none** of them
because none passed the deterministic Safety Gate.

**Narration**

> "Two core routers are overloaded. AEGIS generates four recovery plans. The Digital
> Twin simulates every one of them. The deterministic Safety Gate rejects **all four** —
> because each plan would still leave a router above the 90% load limit. So AEGIS
> **refuses to execute anything**. The AI proposed; the safety layer said no; the
> network was never touched. That's the whole point of the architecture."

---

## If something goes wrong

- **Pipeline spine / recovery panel look stuck mid-run:** the HTTP response is
  authoritative and still renders the final result even if the WebSocket dropped.
  Wait ~1s.
- **Topology looks stale:** click **RESET NETWORK**, then re-run the scenario.
- **"Select a node/link first":** the fault buttons need a target selected in the
  topology first. RUN RECOVERY and RESET NETWORK do not.
- **Backend unreachable:** the header status turns red (`BACKEND DISCONNECTED`) and
  telemetry shows `UNAVAILABLE`. The frontend reconnects on its own within ~2s once
  `docker compose ps` shows `backend` healthy again — the topology resyncs from the
  backend, no refresh needed.
- **RUN RECOVERY on a healthy network** (no fault injected) is safe — it returns
  `NO RECOVERY REQUIRED` / *"No actionable fault detected"* and changes nothing.
- **A full-screen "RELOAD DASHBOARD" message:** the UI caught an unexpected render
  error and stopped itself instead of going blank. Click the button — backend
  network state is untouched and the dashboard resyncs on load.
