 # Interface.ai - Learn Once, Replay Reliably

A small end-to-end prototype for learning a browser-based workflow with an LLM and replaying the learned capability deterministically without calling the model again.

The demo uses a local legacy-style credit union administration application. During discovery, Gemini observes the live browser state, decides the next UI action, and drives the application through Playwright. A successful run is converted into a parameterized, versioned capability artifact.

That saved artifact can then be replayed with different inputs using deterministic Playwright actions only. The replay path includes checkpoint verification, structured error handling, human escalation in the same live browser session, safety allowlists, and redacted evidence logging.

## Core Flow

```text
Natural-language goal
        |
        v
LLM discovery (observe -> decide -> act)
        |
        v
Successful browser run
        |
        v
Versioned capability artifact
        |
        v
Deterministic replay (no LLM)
        |
        +---- success
        |
        +---- business outcome
        |
        +---- hard failure
        |
        +---- human intervention -> same session -> resume

## Setup

### Prerequisites

- Python 3.11+
- Git
- Google Gemini API key
- Internet access for the LLM discovery run

### Install dependencies

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

### Configure the Gemini API key

Create a `.env` file in the project root:

```text
GEMINI_API_KEY=your_api_key_here
```

The `.env` file is excluded from Git and must not be committed.

### Start the local demo application

From the project root, run:

```bash
python -m http.server 8000 --directory demo_app
```

Keep that terminal running. The demo application will be available at:

```text
http://localhost:8000
```
## Run LLM Discovery

Make sure the local demo application is running in a separate terminal.

Then run:

```bash
python discovery.py
```

The discovery process performs a genuine LLM-driven browser run. Gemini repeatedly observes the live application, decides the next action, and Playwright executes that action.

For the demo goal, the agent learns how to look up a member's savings balance.

After a successful run, discovery generates:

```text
artifacts/discovered_lookup_savings_balance.json
```

The saved capability is parameterized with:

```text
{{member_id}}
```

instead of storing the member ID used during discovery.

Structured discovery evidence is written to:

```text
evidence/discovery_log.jsonl
```

Sensitive values and raw member data are not persisted in the evidence log.

## Run Deterministic Replay

After a capability has been discovered, replay it with a different member ID:

```bash
python replay.py 67890
```

Replay loads the saved capability artifact and executes the recorded steps directly with Playwright.

**No LLM is called during replay.**

A successful replay returns a structured result similar to:

```json
{
  "status": "success",
  "capability_id": "lookup_savings_balance",
  "outputs": {
    "result": "Member Details ..."
  },
  "human_handoff_used": false
}
```

Replay evidence is appended to:

```text
evidence/replay_log.jsonl
```

Persisted evidence redacts member data rather than storing the raw result.

## Demo Error Handling and Human Handoff

The demo includes multiple replay outcomes.

### Business outcome

Use a member ID that does not exist:

```bash
python replay.py 99999
```

The replay completes with:

```text
status: business_outcome
```

This represents a valid application-level result rather than an automation failure.

### Hard failure

A deliberately broken capability artifact is included for testing:

```bash
python replay.py 67890 artifacts/broken_test.json
```

The artifact targets a button that does not exist. Replay terminates with a structured hard failure such as:

```text
status: hard_failure
error.code: TARGET_TIMEOUT
```

The failure identifies the step and action that could not be completed.

### Human intervention

Member `11111` is configured to require manual verification:

```bash
python replay.py 11111
```

When the application reports `Manual Verification Required`, replay pauses while keeping the same Playwright browser session alive.

In the open browser:

1. Click `Operator Approve`.
2. Return to the terminal.
3. Press Enter.

Automation then resumes in the same live session, verifies the updated application state, extracts the result, and returns:

```text
status: success
human_handoff_used: true
```

This demonstrates an actual control transfer to a human and back to automation rather than restarting the workflow in a new session.

## Safety

Replay is constrained by an explicit safety policy in `safety.py`.

The current demo policy:

- Allows automation only on `http://localhost:8000`.
- Allows only the `fill`, `click`, and `extract` action types.
- Classifies the implemented actions as safe, reversible operations.
- Permits no irreversible action types in this capability.
- Rejects actions that are not explicitly allowlisted.
- Keeps the Gemini API key in `.env`, which is excluded from Git.
- Redacts member identifiers and member data from persisted evidence logs.

Safety checks are enforced by `replay.py` before executing recorded actions. A capability artifact therefore cannot introduce an arbitrary unsupported action without being rejected by the replay policy.
## Project Structure

```text
interface-ai-assignment/
|-- discovery.py
|-- replay.py
|-- safety.py
|-- requirements.txt
|-- demo_app/
|   `-- index.html
|-- artifacts/
|   |-- discovered_lookup_savings_balance.json
|   `-- broken_test.json
|-- evidence/
|   |-- discovered_lookup_savings_balance.json
|   |-- discovery_log.jsonl
|   `-- replay_log.jsonl
|-- README.md
`-- REPORT.md

## Evidence

The evidence directory contains the saved capability plus structured logs from the genuine LLM discovery run and deterministic replay. Sensitive member values are redacted from persisted logs.

For architecture decisions, tradeoffs, multi-tenant design, safety, and implementation cuts, see REPORT.md.
