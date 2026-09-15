import json
import sys
from datetime import datetime, timezone

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError
)

from safety import check_origin, check_action, classify_action
# ---------------------------------------
# 1. Read input from command line
# ---------------------------------------

if len(sys.argv) < 2:
    print("Please provide a Member ID.")
    print("Example: python replay.py 12345")
    sys.exit(1)

member_id = sys.argv[1]


# ---------------------------------------
# 2. Choose capability artifact
# ---------------------------------------

artifact_path = (
    "artifacts/discovered_lookup_savings_balance.json"
)

# Optional second argument allows us
# to test another artifact.
#
# Example:
# python replay.py 67890 artifacts/broken_test.json
if len(sys.argv) >= 3:
    artifact_path = sys.argv[2]


# ---------------------------------------
# 3. Load capability artifact
# ---------------------------------------

with open(
    artifact_path,
    "r",
    encoding="utf-8"
) as file:
    capability = json.load(file)


print(f"\nCapability: {capability['name']}")
print(f"Artifact: {artifact_path}")
print(f"Input member_id: {member_id}")
print("\nStarting deterministic replay...\n")


# ---------------------------------------
# 4. Start browser
# ---------------------------------------

with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False
    )

    page = browser.new_page()

    page.goto(
        "http://localhost:8000"
    )
    # ---------------------------------------
    # SAFETY: ORIGIN CHECK
    # ---------------------------------------

    # Automation must remain on an explicitly
    # allowed application origin.
    check_origin(page.url)

    print(
        f"Safety check: origin is allowed ({page.url})"
    )

    # ---------------------------------------
    # 5. Prepare replay state
    # ---------------------------------------

    outputs = {}

    replay_failed = False

    failure_details = None

    human_handoff_used = False


    # ---------------------------------------
    # 6. Execute capability steps
    # ---------------------------------------

    for step in capability["steps"]:

        print(
            f"Executing {step['id']}: "
            f"{step['action']}"
        )

        action = step["action"]

        target = step["target"]


        try:

            # --------------------------------
            # SAFETY: ACTION CHECK
            # --------------------------------

            check_action(action)

            print(
                f"Safety check: {action} is allowed "
                f"({classify_action(action)})"
            )

            # --------------------------------
            # FILL
            # --------------------------------

            if action == "fill":

                value = step["value"]

                if value == "{{member_id}}":
                    value = member_id

                if target["strategy"] == "label":

                    page.get_by_label(
                        target["value"]
                    ).fill(
                        value,
                        timeout=5000
                    )

                else:

                    raise ValueError(
                        "Unsupported fill target strategy: "
                        f"{target['strategy']}"
                    )


            # --------------------------------
            # CLICK
            # --------------------------------

            elif action == "click":

                if target["strategy"] == "role":

                    page.get_by_role(
                        target["role"],
                        name=target["value"]
                    ).click(
                        timeout=5000
                    )

                else:

                    raise ValueError(
                        "Unsupported click target strategy: "
                        f"{target['strategy']}"
                    )


            # --------------------------------
            # EXTRACT
            # --------------------------------

            elif action == "extract":

                if target["strategy"] == "css":

                    extracted_value = page.locator(
                        target["value"]
                    ).inner_text(
                        timeout=5000
                    )

                    outputs[
                        step["output"]
                    ] = extracted_value

                else:

                    raise ValueError(
                        "Unsupported extract target strategy: "
                        f"{target['strategy']}"
                    )


            # --------------------------------
            # UNSUPPORTED ACTION
            # --------------------------------

            else:

                raise ValueError(
                    f"Unsupported action: {action}"
                )


        # -----------------------------------
        # TARGET TIMEOUT
        # -----------------------------------

        except PlaywrightTimeoutError:

            replay_failed = True

            # Capture richer failure evidence for debugging.
            failure_screenshot = (
                f"evidence/failure_{step['id']}_{action}.png"
            )

            page.screenshot(
                path=failure_screenshot,
                full_page=True
            )

            print(
                f"Failure screenshot saved: {failure_screenshot}"
            )

            failure_details = {
                "code": "TARGET_TIMEOUT",
                "step_id": step["id"],
                "action": action,
                "message": (
                    "The target could not be found or "
                    "used within 5 seconds."
                )
            }

            print(
                f"\nHARD FAILURE at {step['id']}: "
                "target timed out."
            )

            break


        # -----------------------------------
        # OTHER EXECUTION FAILURE
        # -----------------------------------

        except Exception as error:

            replay_failed = True

            failure_details = {
                "code": "STEP_EXECUTION_ERROR",
                "step_id": step["id"],
                "action": action,
                "message": str(error)
            }

            print(
                f"\nHARD FAILURE at {step['id']}: "
                f"{error}"
            )

            break


    # ---------------------------------------
    # 7. Determine final page state
    # ---------------------------------------

    if replay_failed:

        status = "hard_failure"

    else:

        success_text = capability[
            "success_condition"
        ]["value"]

        page_text = page.locator(
            "body"
        ).inner_text()


        # -----------------------------------
        # SUCCESS
        # -----------------------------------

        if success_text in page_text:

            status = "success"


        # -----------------------------------
        # HUMAN HANDOFF
        # -----------------------------------

        elif "Manual Verification Required" in page_text:
    
            status = "human_intervention_required"

            # Capture the state at the moment automation
            # transfers control to the human operator.
            handoff_screenshot = (
                "evidence/human_handoff_required.png"
            )

            page.screenshot(
                path=handoff_screenshot,
                full_page=True
            )

            print(
                f"Handoff screenshot saved: "
                f"{handoff_screenshot}"
            )

            print(
                "\n======================================"
            )

            print(
                "HUMAN INTERVENTION REQUIRED"
            )

            print(
                "======================================"
            )

            print(
                "\nReason: Manual verification is "
                "required for this member."
            )

            print(
                f"Member ID: {member_id}"
            )

            print(
                "\nThe SAME browser session is still open."
            )

            print(
                "In the browser, click:"
            )

            print(
                "Operator Approve"
            )

            print(
                "\nAfter you finish the manual action,"
            )

            input(
                "return here and press ENTER "
                "to give control back to automation..."
            )

            append_evidence({
                "event": "human_action_completed",
                "capability_id": capability["capability_id"],
                "action": "operator_approved_manual_verification",
                "control": "returned_to_automation"
            })


            # --------------------------------
            # CONTROL RETURNS TO AUTOMATION
            # --------------------------------

            human_handoff_used = True

            print(
                "\nControl returned to automation."
            )

            print(
                "Checking the SAME browser session..."
            )

            # Capture the state after the human
            # returns control to automation.
            handoff_resumed_screenshot = (
                "evidence/human_handoff_resumed.png"
            )

            page.screenshot(
                path=handoff_resumed_screenshot,
                full_page=True
            )

            print(
                f"Post-handoff screenshot saved: "
                f"{handoff_resumed_screenshot}"
            )

            page_text = page.locator(
                "body"
            ).inner_text()


            # --------------------------------
            # HUMAN RESOLVED BLOCKER
            # --------------------------------

            if success_text in page_text:

                status = "success"

                approved_result = page.locator(
                    "#result"
                ).inner_text(
                    timeout=5000
                )

                outputs[
                    "result"
                ] = approved_result

                print(
                    "\nHuman intervention succeeded."
                )

                print(
                    "Automation resumed successfully."
                )


            # --------------------------------
            # HUMAN DID NOT RESOLVE BLOCKER
            # --------------------------------

            else:

                status = "hard_failure"

                failure_details = {
                    "code": (
                        "HUMAN_INTERVENTION_UNRESOLVED"
                    ),
                    "step_id": None,
                    "action": "human_handoff",
                    "message": (
                        "Human intervention was completed, "
                        "but the expected success condition "
                        "was still not present."
                    )
                }


        # -----------------------------------
        # BUSINESS OUTCOME
        # -----------------------------------

        elif "Member Not Found" in page_text:

            status = "business_outcome"


        # -----------------------------------
        # CHECKPOINT FAILURE
        # -----------------------------------

        else:

            status = "hard_failure"

            failure_details = {
                "code": "CHECKPOINT_FAILED",
                "step_id": None,
                "action": None,
                "message": (
                    "Replay completed but the expected "
                    "success condition was not found."
                )
            }


    # ---------------------------------------
    # 8. Build structured replay result
    # ---------------------------------------

    result = {
        "status": status,
        "capability_id": capability[
            "capability_id"
        ],
        "outputs": outputs,
        "human_handoff_used": human_handoff_used
    }


    if failure_details is not None:

        result[
            "error"
        ] = failure_details


    # ---------------------------------------
    # 9. Print structured result
    # ---------------------------------------

    print("\nREPLAY RESULT:")

    print(
        json.dumps(
            result,
            indent=2
        )
    )


    # ---------------------------------------
    # 10. Save REDACTED structured evidence
    # ---------------------------------------

    evidence_record = {

        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),

        "event": "replay_completed",

        "capability_id": capability[
            "capability_id"
        ],

        "status": status,

        "human_handoff_used": (
            human_handoff_used
        ),

        # Never persist raw member details,
        # names, IDs, or balances in logs.
        "outputs": {
            "result": (
                "[REDACTED - sensitive member data]"
                if "result" in outputs
                else None
            )
        }
    }


    if failure_details is not None:

        evidence_record[
            "error"
        ] = failure_details


    with open(
        "evidence/replay_log.jsonl",
        "a",
        encoding="utf-8"
    ) as evidence_file:

        evidence_file.write(
            json.dumps(
                evidence_record
            )
            + "\n"
        )


    print(
        "\nEvidence saved to "
        "evidence/replay_log.jsonl"
    )


    # ---------------------------------------
    # 11. Keep browser visible briefly
    # ---------------------------------------

    page.wait_for_timeout(
        3000
    )

    browser.close()