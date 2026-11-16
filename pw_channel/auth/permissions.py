PERMISSIONS: tuple[dict, ...] = (
    {"key": "overview.view", "label": "View overview", "group": "Monitoring",
     "description": "See the Overview screen: stack health, channels and call counts."},
    {"key": "logs.view", "label": "View logs", "group": "Monitoring",
     "description": "Read and live-tail the production logs."},
    {"key": "calls.live.view", "label": "View live calls", "group": "Calls",
     "description": "See call history, live calls on a line and their transcripts."},
    {"key": "calls.place", "label": "Place calls", "group": "Calls",
     "description": "Dial test calls and use the Playground."},
    {"key": "ingestion.view", "label": "View QMS and history", "group": "Calls",
     "description": "See the intake APIs, what they received and every call that was or was not placed."},
    {"key": "ingestion.cancel", "label": "Cancel scheduled calls", "group": "Calls",
     "description": "Stop a queued call before it rings."},
    {"key": "usecases.view", "label": "View agents", "group": "Agents",
     "description": "See agents and their prompts."},
    {"key": "usecases.edit", "label": "Edit agents", "group": "Agents",
     "description": "Create and change agents."},
    {"key": "usecases.delete", "label": "Delete agents", "group": "Agents",
     "description": "Remove agents."},
    {"key": "tools.view", "label": "View tools", "group": "Tools",
     "description": "See the tools the bot can call."},
    {"key": "tools.edit", "label": "Edit tools", "group": "Tools",
     "description": "Change tool configuration."},
    {"key": "settings.view", "label": "View settings", "group": "Settings",
     "description": "Read pipeline and brain settings and variables. Secrets stay masked."},
    {"key": "settings.edit", "label": "Edit settings", "group": "Settings",
     "description": "Change, reset and apply settings and variables."},
    {"key": "secrets.reveal", "label": "Reveal secrets", "group": "Settings",
     "description": "Show the clear value of a secret variable."},
    {"key": "data.view", "label": "View database", "group": "Data",
     "description": "Browse the call and conversation tables on the Database screen."},
    {"key": "data.delete", "label": "Delete database rows", "group": "Data",
     "description": "Delete rows and purge tables."},
    {"key": "team.view", "label": "View team", "group": "Team",
     "description": "See who has dashboard access and the roles available."},
    {"key": "team.manage", "label": "Manage team", "group": "Team",
     "description": "Invite, edit, deactivate and remove users, and reset their passwords."},
    {"key": "roles.manage", "label": "Manage roles", "group": "Team",
     "description": "Create, edit and delete roles."},
)

GROUPS = ("Monitoring", "Calls", "Agents", "Tools", "Settings", "Data", "Team")

KEYS = frozenset(p["key"] for p in PERMISSIONS)
LABELS = {p["key"]: p["label"] for p in PERMISSIONS}

SUPER_ADMIN = "super_admin"
FALLBACK_ROLE = "viewer"

_ALL = [p["key"] for p in PERMISSIONS]

DEFAULT_ROLES: tuple[dict, ...] = (
    {
        "name": SUPER_ADMIN,
        "label": "Super admin",
        "description": "Everything, including managing roles. Cannot be changed.",
        "permissions": _ALL,
        "is_system": True,
    },
    {
        "name": "admin",
        "label": "Admin",
        "description": "Everything except managing roles.",
        "permissions": [k for k in _ALL if k != "roles.manage"],
        "is_system": True,
    },
    {
        "name": "operator",
        "label": "Operator",
        "description": "Runs calls day to day. Can read settings but not change them.",
        "permissions": [
            "overview.view", "calls.live.view", "calls.place", "ingestion.view",
            "ingestion.cancel", "usecases.view", "tools.view", "settings.view",
            "data.view", "logs.view", "team.view",
        ],
        "is_system": False,
    },
    {
        "name": "client",
        "label": "Client",
        "description": "A client's people: see and test the agents given to their organization, "
                       "with their calls and leads. Nothing else.",
        "permissions": [
            "overview.view", "usecases.view", "calls.place", "calls.live.view", "ingestion.view",
        ],
        "is_system": False,
    },
    {
        "name": "viewer",
        "label": "Viewer",
        "description": "Read-only access to monitoring, calls and configuration.",
        "permissions": [
            "overview.view", "calls.live.view", "ingestion.view", "usecases.view",
            "tools.view", "settings.view", "data.view", "logs.view",
        ],
        "is_system": False,
    },
)


class Rejected(Exception):

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def label_for(key: str) -> str:
    return LABELS.get(key, key)


def denied(key: str) -> str:
    return f"You need the '{label_for(key)}' permission"
