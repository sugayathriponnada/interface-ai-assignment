# Interface.ai Take-Home - Design Report

## Architecture

The prototype implements a learn-once, replay-reliably workflow with two intentionally separate execution paths: LLM-driven discovery and deterministic replay.

During discovery, `discovery.py` receives a natural-language goal and launches the local legacy-style application in Chromium using Playwright. Gemini participates in an observe-decide-act loop. The system observes the current UI state, asks the model for one structured action, executes that action against the live browser, and records only successfully executed browser actions.

The discovery process does not save the raw model conversation as the reusable capability. After the goal is completed, successful actions are transformed into a smaller parameterized artifact. For example, the concrete member identifier used during discovery becomes `{{member_id}}`. This separates the reusable capability from the model transcript and from the specific data used to learn it.

The generated capability contains a schema version, capability identifier, typed inputs and outputs, ordered actions, target strategies, and a success condition.

`replay.py` is a separate deterministic execution path. It loads the saved capability and substitutes runtime parameters before executing the recorded actions directly through Playwright. Gemini is not imported or called by the replay path. This removes model variability, model latency, and model cost from repeated execution.

The implemented vertical slice is:

```text
Natural-language goal
        |
        v
Gemini observe-decide-act discovery
        |
        v
Live Playwright browser interaction
        |
        v
Successful actions
        |
        v
Versioned + parameterized capability artifact
        |
        v
Deterministic Playwright replay
        |
        +---- success
        +---- business outcome
        +---- hard failure
        +---- human handoff -> same browser session -> resume
## Artifact schema

A successful discovery run produces `artifacts/discovered_lookup_savings_balance.json`. The artifact is designed to represent the reusable capability rather than the raw LLM interaction.

The current schema includes:

- `schema_version`: versions the artifact format so future schema changes can be handled explicitly.
- `capability_id` and `name`: identify the reusable capability.
- `inputs`: define required runtime parameters and their types.
- `outputs`: define values returned by the capability.
- `steps`: contain the ordered deterministic actions.
- `target`: describes how replay should identify the UI element.
- `success_condition`: defines the expected completion state.

The discovered member lookup capability contains actions equivalent to:

```json
{
  "schema_version": "1.0",
  "capability_id": "lookup_savings_balance",
  "inputs": {
    "member_id": {
      "type": "string",
      "required": true
    }
  },
  "steps": [
    {
      "id": "step_1",
      "action": "fill",
      "target": {
        "strategy": "label",
        "value": "Member ID:"
      },
      "value": "{{member_id}}"
    },
    {
      "id": "step_2",
      "action": "click",
      "target": {
        "strategy": "role",
        "role": "button",
        "value": "Search"
      }
    },
    {
      "id": "step_3",
      "action": "extract",
      "target": {
        "strategy": "css",
        "value": "#result"
      },
      "output": "result"
    }
  ],
  "success_condition": {
    "type": "text_present",
    "value": "Member Details"
  }
}
```

The important boundary is between discovery evidence and the capability artifact. The discovery log records evidence that an LLM actually drove the learning run, while the capability stores only the minimal information needed for deterministic execution.

Concrete discovery input is parameterized before persistence. As a result, replay can execute the same learned workflow with `67890`, `11111`, or another runtime member identifier without asking the LLM to rediscover the task.

The artifact currently uses label, role, and CSS target strategies. These are sufficient for the implemented vertical slice, while the architecture can be extended with additional target strategies for less semantic surfaces.
## Determinism & error handling

Replay is intentionally separated from discovery. Once a capability has been learned, `replay.py` does not call Gemini or any other LLM. It loads the saved JSON artifact, substitutes runtime parameters, resolves the recorded targets, and executes the actions through Playwright in a fixed order.

This makes repeated execution deterministic at the automation layer. The same artifact and parameters produce the same sequence of browser actions without model sampling or model-dependent decisions.

Each browser operation uses a bounded timeout. Replay reports structured outcomes instead of treating every unexpected state as the same type of failure.

The implemented outcome taxonomy is:

- `success`: the workflow reached the expected application state and produced its output.
- `business_outcome`: the automation worked correctly, but the application returned a valid negative result such as `Member Not Found`.
- `hard_failure`: the workflow could not continue because an automation step failed.
- Recoverable condition: an application state such as `Manual Verification Required` pauses automation and transfers control to a human rather than immediately becoming a hard failure.

Hard failures contain structured diagnostic information. For example, the included `artifacts/broken_test.json` deliberately targets a nonexistent button and produces a result equivalent to:

```json
{
  "status": "hard_failure",
  "capability_id": "lookup_savings_balance",
  "outputs": {},
  "human_handoff_used": false,
  "error": {
    "code": "TARGET_TIMEOUT",
    "step_id": "step_2",
    "action": "click",
    "message": "The target could not be found or used within 5 seconds."
  }
}
```

This preserves the failed step, action type, and machine-readable error code rather than returning only a generic exception.

Replay also distinguishes target timeouts from other step execution errors. This gives an operator or future retry policy a richer signal about why execution stopped.

A successful output is verified against the application's resulting state. For the current capability, `Member Details` is the expected success state. `Member Not Found` is classified separately as a business outcome, and `Manual Verification Required` is treated as a recoverable condition requiring human intervention.

Structured replay evidence is appended to `evidence/replay_log.jsonl`. Persistent evidence records the final status, capability identifier, whether human handoff occurred, and structured failure information when applicable. Member data is redacted from the persisted log.

One practical observation from discovery was that visible body text alone did not expose the current value of the member ID input. The discovery loop therefore explicitly observes the input value in addition to page text. This prevents the model from repeatedly filling an input whose state changed but was not represented in the original observation.
## Heterogeneity & multi-tenant

The implemented vertical slice targets one local browser application, but the capability model is intended to remain separate from the underlying interaction mechanism.

For a production system, I would introduce a `SurfaceAdapter` abstraction between capability execution and the target application. A browser adapter could use Playwright, while additional adapters could support accessibility APIs, screenshot/vision-based interaction, remote desktops, or other legacy surfaces. The capability executor would operate on common actions such as fill, click, read, and navigate while each adapter translates those actions into surface-specific operations.

The current implementation uses Playwright label, role, and CSS targeting because they provide a small, reliable vertical slice. I would not assume that production banking applications always expose clean semantic DOM information. Target resolution could therefore use an ordered strategy: stable semantic identifiers when available, followed by accessibility information, visual anchors, relative positioning, or screenshot-based localization for hostile/non-semantic interfaces.

Multi-tenant support should not require duplicating the entire learned workflow for every financial institution. I would separate a base capability from tenant-specific configuration. A tenant could provide target overrides, allowed origins, application routes, policy settings, and environment-specific configuration while retaining the same logical capability and schema version.

Conceptually:

```text
Base capability
      |
      +---- Tenant A target/config overrides
      |
      +---- Tenant B target/config overrides
      |
      +---- Tenant C target/config overrides
```

Capability versions and tenant overrides should be independently reviewable so that a UI change for one institution does not silently change execution for every tenant.

Secrets should remain outside capability artifacts. Credentials, API keys, and tenant-specific sensitive configuration should come from an external secret/configuration layer at runtime. Artifacts and evidence should contain references or redacted values rather than raw credentials or customer PII.

I intentionally did not implement queues, distributed workers, tenant databases, or orchestration infrastructure for this take-home. Those components would add deployment complexity without improving the correctness of the core learn-once/replay workflow demonstrated here.

## Escalation & handoff

The replay path treats `Manual Verification Required` as a recoverable condition rather than immediately failing the capability.

The demo application intentionally returns this state for member `11111`. When replay detects it, automation pauses while leaving the existing Playwright browser and page open. The terminal instructs the operator to complete the required action in that browser.

The human clicks `Operator Approve` directly in the same live application session. After completing the intervention, the operator returns to the terminal and presses Enter.

Replay then regains control of the same Playwright page, re-observes the application state, and extracts the resulting member details. A successful resumed execution returns:

```json
{
  "status": "success",
  "human_handoff_used": true
}
```

This is a real control transfer rather than a simulated escalation flag. The browser is not closed and recreated, and the workflow is not restarted from the beginning.

If the human intervention does not resolve the blocking state, replay returns a structured hard failure with the error code `HUMAN_INTERVENTION_UNRESOLVED`.

The handoff implementation is intentionally minimal: the terminal acts as the operator interface. In production, the same mechanism could be connected to an operator console that displays the capability, current step, blocking reason, browser session, and available intervention controls.

Evidence preserves whether human intervention occurred through the `human_handoff_used` field while avoiding persistence of raw member data.

## Safety

Safety is enforced independently from the learned capability through `safety.py`. This prevents a capability artifact from automatically gaining permission to perform arbitrary browser actions.

The current policy defines an explicit origin allowlist. Replay is permitted to operate only on:

`http://localhost:8000`

The policy also defines an action allowlist containing only `fill`, `click`, and `extract`. Before replay executes a recorded action, it calls the safety policy to verify that the action is permitted.

The implemented actions are classified as safe, low-risk operations for this read-oriented demo. The policy also contains a separate risky-action category, but no risky or irreversible actions are permitted by the current capability. An unknown action, such as `delete`, is rejected rather than executed.

Replay validates the application origin after opening the target application. Because the implemented capability contains no navigation action, subsequent steps remain within the same local application. In a production executor supporting navigation, I would enforce the origin/route policy before and after every navigation or state-changing transition.

Sensitive configuration is kept outside the capability. The Gemini API key is loaded from `.env`, and `.env` is excluded from Git.

Evidence collection also follows a data-minimization approach. Discovery evidence records the model decision and browser-action metadata needed to demonstrate the LLM-driven run, but concrete member input and completion results are redacted. Replay evidence similarly replaces returned member data with a redacted marker before persistence.

This separation gives the system three independent layers: the capability describes what was learned, the executor determines how it runs, and the safety policy determines what it is allowed to do.
## Cuts

I intentionally optimized this take-home for a small, correct end-to-end vertical slice rather than production breadth.

The following were deliberately not implemented:

- A full operator web UI. Human intervention uses the terminal plus the same live Playwright browser session.
- Distributed workers, queues, schedulers, or cluster orchestration.
- Production multi-tenant persistence and tenant management. The multi-tenant approach is described as a design extension instead.
- A screenshot/vision-based surface adapter. The current implementation uses Playwright label, role, and CSS targeting while the architecture describes how non-semantic surfaces could be supported.
- Automatic retry or self-healing of broken capabilities. Failures are surfaced with structured evidence rather than silently retried.
- Risky or irreversible banking actions. The demonstrated capability is intentionally read-oriented, and the safety policy permits only the actions required by this workflow.
- Persistent storage of raw model observations, customer data, or browser screenshots. Evidence is minimized and sensitive values are redacted.
- A generalized capability marketplace or workflow orchestration layer.

Given more time, my next priorities would be stronger artifact schema validation, per-step replay telemetry, additional checkpoint types, vision/accessibility fallback targeting, and a small operator console for human handoff.

I would also move safety configuration into tenant-scoped external policy configuration and enforce domain, route, and action policies at every relevant browser transition.

The goal of these cuts was to keep the submission centered on the difficult architectural boundary: use an LLM to learn a task once, convert that successful run into a reviewable capability, and execute that capability repeatedly without depending on the model.

## Project Structure

```text
interface-ai-assignment/
|
|-- discovery.py
|   LLM-driven observe-decide-act discovery loop
|
|-- replay.py
|   Deterministic capability executor with error handling and human handoff
|
|-- safety.py
|   Origin, action allowlist, and risk-classification policy
|
|-- requirements.txt
|   Python dependencies
|
|-- demo_app/
|   `-- index.html
|       Local legacy-style financial application used for the demo
|
|-- artifacts/
|   |-- discovered_lookup_savings_balance.json
|   |   Learned, parameterized capability
|   |
|   `-- broken_test.json
|       Intentionally broken capability used to demonstrate hard failure handling
|
|-- evidence/
|   |-- discovered_lookup_savings_balance.json
|   |   Saved capability included with submission evidence
|   |
|   |-- discovery_log.jsonl
|   |   Redacted evidence from the genuine LLM-driven discovery run
|   |
|   `-- replay_log.jsonl
|       Redacted deterministic replay evidence
|
|-- README.md
|   Setup and demo instructions
|
`-- REPORT.md
    Architecture, tradeoffs, safety, handoff, and design discussion
```

## Evidence

The `evidence/` directory contains evidence from actual executions of the prototype.

`discovery_log.jsonl` demonstrates the LLM-driven observe-decide-act discovery run. `replay_log.jsonl` contains deterministic replay outcomes, including successful execution, business outcomes, hard failures, and human handoff. Sensitive member values are redacted from persisted logs.

The saved capability is also copied into the evidence directory so the learned artifact can be reviewed alongside the execution evidence.

For architecture decisions, tradeoffs, multi-tenant design, safety, and implementation cuts, see `REPORT.md`.