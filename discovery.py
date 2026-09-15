import os
import sys
import json
from datetime import datetime, timezone

from dotenv import load_dotenv
from google import genai
from playwright.sync_api import sync_playwright
from safety import check_origin, check_action


# ---------------------------------------
# 1. Load Gemini API key
# ---------------------------------------

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        "GEMINI_API_KEY was not found. Check your .env file."
    )

client = genai.Client(api_key=api_key)


# ---------------------------------------
# 2. Define the natural-language goal
# ---------------------------------------

default_goal = (
    "Look up member 12345 and return "
    "their savings balance."
)

default_target = "http://localhost:8000"

goal = (
    sys.argv[1]
    if len(sys.argv) > 1
    else default_goal
)

target_url = (
    sys.argv[2]
    if len(sys.argv) > 2
    else default_target
)

print("\nGOAL:")
print(goal)

print("\nTARGET:")
print(target_url)


# ---------------------------------------
# 3. Prepare evidence logging
# ---------------------------------------

os.makedirs(
    "evidence",
    exist_ok=True
)

discovery_evidence = []


def add_evidence(
    event,
    step_number=None,
    action=None,
    status=None,
    details=None
):
    """
    Store structured discovery evidence.

    Sensitive member values and account
    information are intentionally not stored.
    """

    record = {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "event": event
    }

    if step_number is not None:
        record["step_number"] = step_number

    if action is not None:
        record["action"] = action

    if status is not None:
        record["status"] = status

    if details is not None:
        record["details"] = details

    discovery_evidence.append(
        record
    )


add_evidence(
    event="discovery_started",
    status="running",
    details={
        "goal": (
            "Look up a member and return "
            "their savings balance."
        ),
        "model": "gemini-3.6-flash",
        "target": target_url
    }
)


# ---------------------------------------
# 4. Start browser
# ---------------------------------------

with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False
    )

    page = browser.new_page()

    check_origin(target_url)

    page.goto(target_url)


    # ---------------------------------------
    # 5. Prepare discovery run
    # ---------------------------------------

    max_steps = 5

    recorded_actions = []


    # ---------------------------------------
    # 6. Observe -> Decide -> Act loop
    # ---------------------------------------

    for step_number in range(
        1,
        max_steps + 1
    ):

        print(
            f"\n========== STEP {step_number} =========="
        )


        # -----------------------------------
        # OBSERVE
        # -----------------------------------

        observation = page.locator(
            "body"
        ).inner_text()

        member_id_value = page.get_by_label(
            "Member ID:"
        ).input_value()

        observation += (
            f"\nCurrent Member ID input value: "
            f"{member_id_value}"
        )

        print("\nCURRENT UI:")
        print(observation)


        # Store only safe observation metadata.
        # Do NOT persist the raw page contents.
        add_evidence(
            event="ui_observed",
            step_number=step_number,
            status="success",
            details={
                "surface": "browser",
                "url": page.url,
                "raw_observation_stored": False
            }
        )


        # -----------------------------------
        # DECIDE
        # -----------------------------------

        prompt = f"""
You are controlling a browser to complete a task.

GOAL:
{goal}

CURRENT WEBPAGE:
{observation}

You may choose exactly ONE action:

1. fill

Use this when you need to type into a field.

Example:

{{
  "action": "fill",
  "target": "Member ID:",
  "value": "12345"
}}


2. click

Use this when you need to click a button.

Example:

{{
  "action": "click",
  "target": "Search"
}}


3. complete

Use this ONLY when the goal has been completed
and the requested information is visible.

Example:

{{
  "action": "complete",
  "result": "Savings balance is $100.00"
}}


IMPORTANT:

Look at the current value of the input field.

If the correct Member ID is already in the field,
do NOT fill it again.

Choose the next necessary action.

Return only one JSON object.
Do not include explanations.
"""

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )

        print("\nGEMINI DECISION:")
        print(response.text)


        # -----------------------------------
        # PARSE GEMINI DECISION
        # -----------------------------------

        decision_text = response.text.strip()

        decision_text = decision_text.replace(
            "```json",
            ""
        ).replace(
            "```",
            ""
        ).strip()

        decision = json.loads(
            decision_text
        )

        print("\nPARSED DECISION:")
        print(decision)

        action = decision["action"]

        if action != "complete":
            check_action(action)

        # Record that the LLM made a decision,
        # but do not persist raw values/results.
        safe_decision_details = {
            "decision_source": "llm",
            "model": "gemini-3.6-flash"
        }

        if action == "fill":
            safe_decision_details[
                "target"
            ] = decision.get(
                "target"
            )

            safe_decision_details[
                "value"
            ] = "[REDACTED]"

        elif action == "click":
            safe_decision_details[
                "target"
            ] = decision.get(
                "target"
            )

        elif action == "complete":
            safe_decision_details[
                "result"
            ] = "[REDACTED]"

        add_evidence(
            event="llm_decision",
            step_number=step_number,
            action=action,
            status="selected",
            details=safe_decision_details
        )


        # -----------------------------------
        # ACT: FILL
        # -----------------------------------

        if action == "fill":

            target = decision["target"]
            value = decision["value"]

            print(
                f"\nExecuting FILL: "
                f"{target} = {value}"
            )

            page.get_by_label(
                target
            ).fill(
                value
            )

            recorded_actions.append({
                "action": "fill",
                "target": {
                    "strategy": "label",
                    "value": target
                },
                "value": value
            })

            add_evidence(
                event="browser_action",
                step_number=step_number,
                action="fill",
                status="success",
                details={
                    "target_strategy": "label",
                    "target": target,
                    "value": "[REDACTED]"
                }
            )


        # -----------------------------------
        # ACT: CLICK
        # -----------------------------------

        elif action == "click":

            target = decision["target"]

            print(
                f"\nExecuting CLICK: {target}"
            )

            page.get_by_role(
                "button",
                name=target
            ).click()

            recorded_actions.append({
                "action": "click",
                "target": {
                    "strategy": "role",
                    "role": "button",
                    "value": target
                }
            })

            add_evidence(
                event="browser_action",
                step_number=step_number,
                action="click",
                status="success",
                details={
                    "target_strategy": "role",
                    "role": "button",
                    "target": target
                }
            )


        # -----------------------------------
        # ACT: COMPLETE
        # -----------------------------------

        elif action == "complete":

            print("\nGOAL COMPLETED:")
            print(
                decision["result"]
            )


            add_evidence(
                event="goal_completed",
                step_number=step_number,
                action="complete",
                status="success",
                details={
                    "result": "[REDACTED]"
                }
            )


            # -----------------------------------
            # SHOW RECORDED ACTIONS
            # -----------------------------------

            print("\nRECORDED ACTIONS:")

            print(
                json.dumps(
                    recorded_actions,
                    indent=2
                )
            )


            # -----------------------------------
            # BUILD REUSABLE CAPABILITY STEPS
            # -----------------------------------

            capability_steps = []

            for index, recorded_action in enumerate(
                recorded_actions,
                start=1
            ):

                capability_step = (
                    recorded_action.copy()
                )

                capability_step["id"] = (
                    f"step_{index}"
                )


                # --------------------------------
                # PARAMETERIZE MEMBER ID
                # --------------------------------

                if (
                    capability_step["action"]
                    == "fill"
                    and capability_step.get(
                        "value"
                    ) == "12345"
                ):

                    capability_step["value"] = (
                        "{{member_id}}"
                    )


                capability_steps.append(
                    capability_step
                )


            # -----------------------------------
            # ADD OUTPUT EXTRACTION STEP
            # -----------------------------------

            capability_steps.append({
                "id": (
                    f"step_"
                    f"{len(capability_steps) + 1}"
                ),
                "action": "extract",
                "target": {
                    "strategy": "css",
                    "value": "#result"
                },
                "output": "result"
            })


            # -----------------------------------
            # BUILD CAPABILITY ARTIFACT
            # -----------------------------------

            capability = {

                "schema_version": "1.0",

                "capability_id": (
                    "lookup_savings_balance"
                ),

                "name": (
                    "Lookup Savings Balance"
                ),

                "inputs": {
                    "member_id": {
                        "type": "string",
                        "required": True
                    }
                },

                "outputs": {
                    "result": {
                        "type": "string"
                    }
                },

                "steps": capability_steps,

                "success_condition": {
                    "type": "text_present",
                    "value": "Member Details"
                }
            }


            # -----------------------------------
            # SAVE CAPABILITY ARTIFACT
            # -----------------------------------

            os.makedirs(
                "artifacts",
                exist_ok=True
            )

            artifact_path = (
                "artifacts/"
                "discovered_lookup_savings_balance.json"
            )

            with open(
                artifact_path,
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    capability,
                    file,
                    indent=2
                )


            print("\nCAPABILITY SAVED:")
            print(
                artifact_path
            )


            add_evidence(
                event="capability_saved",
                step_number=step_number,
                status="success",
                details={
                    "capability_id": (
                        "lookup_savings_balance"
                    ),
                    "schema_version": "1.0",
                    "artifact_path": artifact_path,
                    "recorded_browser_actions": len(
                        recorded_actions
                    ),
                    "parameterized": True
                }
            )


            break


        # -----------------------------------
        # UNSUPPORTED ACTION
        # -----------------------------------

        else:

            add_evidence(
                event="discovery_failed",
                step_number=step_number,
                action=action,
                status="failure",
                details={
                    "reason": (
                        "Unsafe or unsupported action"
                    )
                }
            )

            raise ValueError(
                f"Unsafe or unsupported action: "
                f"{action}"
            )


        page.wait_for_timeout(
            500
        )
    else:
        add_evidence(
            event="discovery_failed",
            step_number=max_steps,
            status="failure",
            details={
                "reason": "Maximum discovery steps exceeded",
                "error_code": "DISCOVERY_MAX_STEPS_EXCEEDED"
            }
        )

        print(
            "\nDISCOVERY STOPPED: "
            "maximum step limit reached."
        )

    # ---------------------------------------
    # 7. Save discovery evidence
    # ---------------------------------------

    evidence_path = (
        "evidence/discovery_log.jsonl"
    )

    with open(
        evidence_path,
        "w",
        encoding="utf-8"
    ) as evidence_file:

        for evidence_record in discovery_evidence:

            evidence_file.write(
                json.dumps(
                    evidence_record
                )
                + "\n"
            )


    print(
        "\nDISCOVERY EVIDENCE SAVED:"
    )

    print(
        evidence_path
    )


    # ---------------------------------------
    # 8. Keep browser visible briefly
    # ---------------------------------------

    page.wait_for_timeout(
        3000
    )

    browser.close()