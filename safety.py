# ---------------------------------------
# Safety policy
# ---------------------------------------

# Browser automation is allowed to operate
# only on these origins.
ALLOWED_ORIGINS = {
    "http://localhost:8000"
}


# Only these action types may be executed.
ALLOWED_ACTIONS = {
    "fill",
    "click",
    "extract"
}


# Actions in this demo are read-oriented
# and reversible / low risk.
SAFE_ACTIONS = {
    "fill",
    "click",
    "extract"
}


# No irreversible actions are permitted
# by this demo capability.
RISKY_ACTIONS = set()


def check_origin(url):
    """
    Reject navigation outside the configured
    application origin.
    """

    normalized_url = url.rstrip("/")

    if normalized_url not in ALLOWED_ORIGINS:
        raise ValueError(
            f"Safety policy blocked origin: {url}"
        )


def check_action(action):
    """
    Reject actions that are not explicitly
    allowed by policy.
    """

    if action not in ALLOWED_ACTIONS:
        raise ValueError(
            f"Safety policy blocked action: {action}"
        )


def classify_action(action):
    """
    Return the configured risk classification
    for an action.
    """

    if action in SAFE_ACTIONS:
        return "safe"

    if action in RISKY_ACTIONS:
        return "risky"

    return "unknown"