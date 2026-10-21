"""Things the agent leaves for the person: approvals to answer, and messages.

`db` stores items and the "allow always" rules. `api` lists, counts, answers and dismisses them.
"""

APPROVAL = "approval"
MESSAGE = "message"

OPEN = "open"
RESOLVED = "resolved"
DISMISSED = "dismissed"
EXPIRED = "expired"

ALLOW = "allow"
ALLOW_ALWAYS = "allow_always"
DENY = "deny"

SUPERSEDED = "superseded"

APPROVAL_HOURS = 24
