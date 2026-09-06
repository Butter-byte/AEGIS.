from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether
from reportlab.pdfbase.pdfmetrics import stringWidth
import os

OUT = r"C:\Users\yyash\Documents\Codex\2026-09-06\i-am-building-a-hackathon-project\outputs\aegis-ai-diagnosis-recovery-planner.pdf"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

NAVY = colors.HexColor('#0B1736')
BLUE = colors.HexColor('#176BBA')
TEAL = colors.HexColor('#00A6A6')
PALE = colors.HexColor('#EEF5FB')
INK = colors.HexColor('#172033')
MUTED = colors.HexColor('#5A6A7B')
RED = colors.HexColor('#B33A3A')

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleAegis', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=30, leading=35, textColor=NAVY, spaceAfter=12))
styles.add(ParagraphStyle(name='SubtitleAegis', parent=styles['BodyText'], fontName='Helvetica', fontSize=14, leading=20, textColor=MUTED, spaceAfter=20))
styles.add(ParagraphStyle(name='H1Aegis', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=19, leading=24, textColor=NAVY, spaceBefore=14, spaceAfter=9))
styles.add(ParagraphStyle(name='H2Aegis', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=13, leading=17, textColor=BLUE, spaceBefore=11, spaceAfter=6))
styles.add(ParagraphStyle(name='BodyAegis', parent=styles['BodyText'], fontName='Helvetica', fontSize=10.2, leading=15.2, textColor=INK, spaceAfter=7))
styles.add(ParagraphStyle(name='SmallAegis', parent=styles['BodyText'], fontName='Helvetica', fontSize=8.4, leading=11, textColor=MUTED))
styles.add(ParagraphStyle(name='CalloutAegis', parent=styles['BodyText'], fontName='Helvetica-Bold', fontSize=11, leading=16, textColor=NAVY, leftIndent=8, rightIndent=8, spaceBefore=3, spaceAfter=3))
styles.add(ParagraphStyle(name='MonoAegis', parent=styles['BodyText'], fontName='Courier', fontSize=7.6, leading=10, textColor=INK))
styles.add(ParagraphStyle(name='TOCAegis', parent=styles['BodyText'], fontName='Helvetica', fontSize=11, leading=18, textColor=INK))

def p(text, style='BodyAegis'):
    return Paragraph(text, styles[style])

def bullet(text):
    return p('&bull; ' + text)

def section(title):
    return p(title, 'H1Aegis')

def h2(title):
    return p(title, 'H2Aegis')

def callout(text):
    t = Table([[p(text, 'CalloutAegis')]], colWidths=[16.4*cm])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('LINEBEFORE',(0,0),(0,-1),4,TEAL),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    return t

def table(headers, rows, widths):
    data = [[p(x, 'SmallAegis') for x in headers]] + [[p(str(x), 'SmallAegis') for x in row] for row in rows]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),NAVY), ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'), ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#C9D7E5')), ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),
        ('LEFTPADDING',(0,0),(-1,-1),6), ('RIGHTPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),6), ('BOTTOMPADDING',(0,0),(-1,-1),6),
    ]))
    return t

def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#D8E2EC'))
    canvas.line(1.5*cm, 1.25*cm, A4[0]-1.5*cm, 1.25*cm)
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(1.5*cm, .85*cm, 'AEGIS | Safety-Gated Autonomous Network Recovery')
    canvas.drawRightString(A4[0]-1.5*cm, .85*cm, f'Page {doc.page}')
    canvas.restoreState()

story = []
story += [Spacer(1, 3.2*cm), p('AEGIS', 'TitleAegis'), p('AI Diagnosis + Recovery Planner', 'TitleAegis'), p('A beginner-friendly module guide for Safety-Gated Autonomous Network Recovery', 'SubtitleAegis'), callout('Your module is Aegis\'s reasoning brain: it identifies the most likely cause of a network incident and proposes safe, reversible recovery plans. It does <b>not</b> directly change the real network.'), Spacer(1, .8*cm), p('Hackathon architecture brief', 'H2Aegis'), p('Prepared for the AI Diagnosis + Recovery Planner responsibility', 'BodyAegis'), PageBreak()]

story += [section('1. The big picture'), p('Aegis is designed to help a network recover from incidents without giving an AI unrestricted control. Your module sits in the middle of the decision process: it turns evidence into an explanation and a proposed recovery plan.'), h2('The flow'), table(['Stage', 'Question answered', 'Result'], [
    ('Monitoring', 'What is happening?', 'Metrics, logs, alerts, configuration changes'),
    ('Incident detection', 'Is this abnormal?', 'An incident and its initial scope'),
    ('Your module', 'What likely caused it, and what could fix it?', 'Ranked diagnosis and candidate plans'),
    ('Digital Twin', 'What is likely to happen if we try this?', 'Simulation evidence'),
    ('Safety Engine', 'May this exact plan run?', 'Approval, limits, rejection, or human review'),
    ('Executor', 'How is the approved plan applied?', 'Controlled real-world actions'),
    ('Verification', 'Did service actually recover?', 'Success, rollback, or re-planning')
], [3.0*cm, 6.2*cm, 7.2*cm]), Spacer(1, .4*cm), callout('Think of it this way: monitors are Aegis\'s eyes and ears; your module is the doctor; the Digital Twin is the practice patient; the Safety Engine is the cautious supervisor; and the executor is the technician.'), h2('Why the separation matters'), p('An AI can be useful but uncertain. Aegis therefore makes the AI a planner, not a direct operator. Simulation tests predicted consequences, while a rule-based safety layer checks authorization, risk limits, and rollback readiness before the executor can act.')]

story += [section('2. What your module should do'), h2('A. Diagnose the incident'), p('Diagnosis means moving from visible symptoms to likely causes. A symptom might be “customers cannot reach the payment API.” A root cause might be “a routing change on Router R7 sent payment traffic to the wrong destination.”'), bullet('Correlate metrics, logs, topology, service health, and recent changes.'), bullet('Build a timeline: what changed first, and what failed immediately afterward?'), bullet('Identify affected devices, links, services, users, and regions.'), bullet('Generate more than one plausible cause if the evidence is incomplete.'), bullet('Give each hypothesis a confidence level and list the evidence for and against it.'), bullet('Say when more safe, read-only diagnostics are needed.'), h2('B. Plan recovery'), p('Recovery planning turns the diagnosis into explicit steps that can be simulated and checked. A good plan explains the objective, exact actions, preconditions, expected effects, verification checks, stop conditions, and rollback.'), bullet('Produce a small set of candidate plans, such as containment, fastest restoration, and root-cause repair.'), bullet('Prefer constrained operations from an approved action catalog rather than arbitrary commands.'), bullet('Rank plans by predicted success, safety, disruption, blast radius, and rollback difficulty.'), bullet('Attach a human-readable explanation for operators and judges.')]

story += [section('3. A worked example'), p('Scenario: payment requests in the ap-south region begin failing. The monitoring system finds that a BGP routing configuration changed on Router R7 just before packet loss began. Application servers and DNS are healthy; the backup route through R8 still works.'), h2('Diagnosis output'), table(['Hypothesis', 'Confidence', 'Supporting evidence'], [
    ('Incorrect BGP route on R7', '0.82', 'R7 route change occurred just before loss; backup path works; app and DNS are healthy.'),
    ('Physical link failure', '0.12', 'Packet loss exists, but link health indicators are normal.'),
    ('Payment API failure', '0.06', 'Service health checks are passing.')
], [5.0*cm, 2.0*cm, 9.4*cm]), h2('Candidate plans'), table(['Plan', 'Goal', 'Trade-off'], [
    ('A: Roll back R7 configuration', 'Restore the last known-good route.', 'Likely fixes the root cause; brief routing reconvergence is possible.'),
    ('B: Shift traffic to R8', 'Restore service using the backup path.', 'Fast containment, but capacity must be sufficient and root cause remains.'),
    ('C: Gather more evidence', 'Run a read-only route lookup and validation.', 'Lowest risk, but delays recovery if the cause is already clear.')
], [4.1*cm, 6.1*cm, 6.2*cm]), h2('Example plan A'), p('1. Confirm the unexpected route is still present on R7.<br/>2. Save the current configuration.<br/>3. Restore the approved known-good BGP configuration.<br/>4. Validate configuration syntax and routing state.<br/>5. Simulate the change in the Digital Twin.<br/>6. If approved, execute in production.<br/>7. Verify payment connectivity, packet loss, and error rate.<br/>8. Roll back if health worsens or a stop condition is met.')]

story += [section('4. Inputs your module receives'), p('Your module should receive a clean incident context package. It should not receive secrets such as passwords, private keys, or access tokens.'), table(['Input', 'Why it matters', 'Example'], [
    ('Incident metadata', 'Identifies urgency and initial scope.', 'INC-1042, critical, payment-api, ap-south'),
    ('Topology snapshot', 'Shows dependencies and alternate paths.', 'Users -> R1 -> R7 -> Payment subnet; R8 is backup'),
    ('Telemetry', 'Shows measured network behavior.', 'Packet loss, latency, CPU, link state, interface errors'),
    ('Logs and events', 'Explains what devices and services observed.', 'BGP updates, firewall denies, configuration errors'),
    ('Recent changes', 'Often exposes the triggering event.', 'A routing-policy update at 14:00:52'),
    ('Configuration snapshots', 'Allows comparison and safe rollback.', 'Current and known-good R7 configuration versions'),
    ('Runbooks and history', 'Supplies approved organizational knowledge.', 'Previous incident fixes and standard procedures'),
    ('Policies and constraints', 'Defines what automation may safely attempt.', 'Max 25% traffic shift; device reboot needs approval')
], [3.4*cm, 6.3*cm, 6.7*cm]), h2('Minimum incident context'), p('At a minimum, include incident ID, timestamps, symptom, current severity, affected service and region, topology version, relevant metrics and events, recent changes, policy version, and the list of approved actions.')]

story += [section('5. Outputs your module generates'), h2('1. Structured diagnosis report'), p('Machines need predictable fields. The report should include incident summary, affected components, ranked hypotheses, confidence, evidence, conflicting evidence, missing information, and estimated blast radius.'), p('{<br/>&nbsp;&nbsp;"incident_id": "INC-1042",<br/>&nbsp;&nbsp;"summary": "Payment traffic is failing between R7 and the payment subnet.",<br/>&nbsp;&nbsp;"hypotheses": [{"cause": "Incorrect BGP route on R7", "confidence": 0.82}],<br/>&nbsp;&nbsp;"missing_information": ["Post-change BGP validation result"]<br/>}', 'MonoAegis'), h2('2. Candidate recovery plan'), p('Each plan should include a plan ID, objective, related hypothesis, ordered actions, preconditions, expected impact, risk estimate, verification checks, rollback operation, required permissions, stop conditions, and required human approval.'), h2('3. Operator explanation'), p('Also generate a short explanation in plain language: “A routing change on R7 is the strongest root-cause candidate. The recommended plan restores the last known-good configuration. Aegis will simulate it and verify reachability before production execution.”')]

story += [section('6. Working with the Digital Twin'), p('The Digital Twin is a safe virtual representation of the network. It models devices, links, routing behavior, firewall policies, traffic flows, capacity, and service dependencies. Your planner sends the full candidate plan to it before any production action.'), h2('What the twin tests'), bullet('Does connectivity return?'), bullet('Does the plan create routing loops, isolation, or unstable convergence?'), bullet('Does it overload a backup link or break a different service?'), bullet('Does it preserve required redundancy?'), bullet('Does the rollback work after a partial or failed action?'), h2('Feedback loop'), p('If the planner proposes shifting 100% of traffic to R8 and the Digital Twin predicts 130% capacity utilization, the plan must be revised. It might shift only 20% of traffic and defer the rest, or choose a configuration rollback instead.'), callout('The Digital Twin answers “what is likely to happen?” It does not grant permission. Passing a simulation is necessary evidence, but it is not a safety approval.')]

story += [section('7. Working with the Safety Engine'), p('The Safety Engine is the enforcement layer between an AI recommendation and the real network. It evaluates whether a particular plan is permitted and bounded enough to execute.'), h2('Typical checks'), bullet('Is this target device in the automation scope?'), bullet('Is the action type allowed, and is it represented in the approved action catalog?'), bullet('Did the Digital Twin pass, including the rollback test?'), bullet('Is the blast radius within policy and is redundancy preserved?'), bullet('Is diagnosis confidence high enough for automatic execution?'), bullet('Does the plan require a human approval, maintenance window, or change ticket?'), bullet('Are verification and stop conditions present?'), h2('Possible decisions'), table(['Decision', 'Meaning'], [
    ('APPROVED_AUTOMATICALLY', 'The executor may run only the approved actions.'),
    ('APPROVED_WITH_LIMITS', 'The plan may run with bounded targets, thresholds, or deadlines.'),
    ('HUMAN_APPROVAL_REQUIRED', 'An operator must explicitly authorize the plan.'),
    ('REVISE_AND_RESUBMIT', 'The planner must address defined safety gaps.'),
    ('REJECTED', 'The proposed action is not allowed or too risky.')
], [6.0*cm, 10.4*cm]), callout('A safety approval must be specific: these exact operations, on these exact targets, within these exact limits. It must never mean “the AI may do anything necessary.”')]

story += [section('8. Design rules that keep Aegis safe'), h2('The AI proposes; deterministic controls decide'), p('Use the AI for interpreting evidence, retrieving relevant runbooks, forming hypotheses, and creating candidate plans. Use conventional code and policy rules for schema validation, permissions, command allowlists, risk limits, approvals, execution, timeouts, and rollback triggers.'), h2('Use constrained actions'), p('The planner should emit an operation such as <font name="Courier">restore_config_version(target=router-r7, version=r7-config-v41)</font>. A trusted adapter converts it into vendor-specific commands. The model should not emit unrestricted device CLI commands.'), h2('Make uncertainty visible'), p('“The available evidence is not sufficient for a safe diagnosis; run these read-only checks” is a correct and valuable outcome.'), h2('Every modification needs a tested rollback'), p('A rollback should state the state to restore, the trigger for restoring it, how success will be verified, and the safe escalation path if rollback fails.'), h2('Protect against stale plans'), p('Before execution, re-check that the relevant configuration, topology, device health, backup capacity, and approval are still valid. A plan that was safe five minutes ago may not be safe now.')]

story += [section('9. A practical hackathon scope'), p('A convincing prototype does not need to support every outage. Build one end-to-end story extremely clearly:'), callout('A configuration change causes primary-path traffic loss. Aegis diagnoses the change, proposes a rollback or bounded traffic shift, simulates it in the Digital Twin, enforces safety policy, and executes only a specifically approved recovery.'), h2('Demo checklist'), bullet('Ingest a JSON incident package.'), bullet('Show two or three ranked diagnoses with evidence and confidence.'), bullet('Retrieve an approved runbook or action catalog entry.'), bullet('Generate a machine-readable recovery plan with rollback and stop conditions.'), bullet('Show a Digital Twin pass or fail, then revise the plan if needed.'), bullet('Show the Safety Engine approving, limiting, rejecting, or requiring a human.'), bullet('Display the explanation, decision trail, and final verification metrics in a dashboard.'), h2('A compact module contract'), p('<b>Input:</b> incident context + topology + telemetry + logs + changes + policies + action catalog + runbooks + prior feedback.<br/><b>Process:</b> build timeline -> rank hypotheses -> generate plans -> simulate -> revise -> safety review.<br/><b>Output:</b> diagnosis report + ranked candidate plans + evidence + assumptions + machine-readable actions + verification + rollback + operator explanation.'), Spacer(1, .5*cm), callout('Central rule: your module recommends an evidence-backed, reversible recovery strategy. The Digital Twin predicts its effects, and the Safety Engine controls whether and how it may reach the real network.')]

doc = SimpleDocTemplate(OUT, pagesize=A4, rightMargin=1.55*cm, leftMargin=1.55*cm, topMargin=1.55*cm, bottomMargin=1.7*cm, title='Aegis: AI Diagnosis + Recovery Planner')
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
