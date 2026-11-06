"""Classify Google API errors without displaying response text or identifiers."""

import json


REASONS = {
    "ACCESS_TOKEN_SCOPE_INSUFFICIENT", "SERVICE_DISABLED", "PERMISSION_DENIED",
    "insufficientPermissions", "forbidden", "domainPolicy", "accessNotConfigured",
    "rateLimitExceeded", "userRateLimitExceeded", "RESOURCE_EXHAUSTED",
}


def error_reason(exc):
    try:
        error = json.loads(exc.content).get("error", {})
        reasons = [entry.get("reason") for entry in error.get("errors", []) + error.get("details", [])]
        message = error.get("message", "").lower()
        if "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in reasons or "insufficient authentication scopes" in message:
            return "ACCESS_TOKEN_SCOPE_INSUFFICIENT"
        for reason in ("SERVICE_DISABLED", "accessNotConfigured", "domainPolicy"):
            if reason in reasons:
                return reason
        if "caller does not have permission" in message:
            return "CALLER_NO_PERMISSION"
        return next((reason for reason in reasons if reason in REASONS), "UNCLASSIFIED")
    except (ValueError, TypeError, AttributeError):
        return "UNCLASSIFIED"


def operation(exc):
    # Return only static API method names; never print the URL (course IDs etc.).
    uri = getattr(exc, "uri", "") or ""
    if "/courseWorkMaterials" in uri:
        return "courses.courseWorkMaterials.list"
    if "/courseWork" in uri:
        return "courses.courseWork.list"
    if "/announcements" in uri:
        return "courses.announcements.list"
    return "courses.list"
