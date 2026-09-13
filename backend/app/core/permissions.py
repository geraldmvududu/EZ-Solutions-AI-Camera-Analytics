class Permissions:
    VIEW_CAMERAS = "view_cameras"
    VIEW_LIVE_VIDEO = "view_live_video"
    VIEW_RECORDINGS = "view_recordings"
    DOWNLOAD_RECORDINGS = "download_recordings"
    MANAGE_CAMERAS = "manage_cameras"
    MANAGE_AI = "manage_ai"
    MANAGE_ALERTS = "manage_alerts"
    MANAGE_RULES = "manage_rules"
    MANAGE_USERS = "manage_users"
    MANAGE_INCIDENTS = "manage_incidents"
    VIEW_REPORTS = "view_reports"
    MANAGE_SYSTEM_SETTINGS = "manage_system_settings"
    # Facial Recognition & Identity Analytics: deliberately its own permission, not
    # folded into MANAGE_AI — enrollment/management of biometric data is admin-only
    # per spec section 17, distinct from general AI/camera configuration.
    MANAGE_BIOMETRICS = "manage_biometrics"
    VIEW_BIOMETRIC_EVENTS = "view_biometric_events"
    # Event-First Cloud Storage Phase 1 (section 1) — Sites are a new organizational
    # layer (Customer -> Site -> Camera); viewing/managing them is deliberately its
    # own permission pair rather than folded into MANAGE_CAMERAS, since a Security
    # Manager (see ROLE_PERMISSION_MAP below) can review sites/events but shouldn't
    # necessarily be able to restructure a tenant's site layout.
    VIEW_SITES = "view_sites"
    MANAGE_SITES = "manage_sites"
    # Retention-tier policy (section 10) is deliberately Platform-Administrator-only
    # (SUPER_ADMIN) — not exposed here as a per-tenant permission at all; see
    # app/api/routes/retention_tiers.py, which gates directly on the SUPER_ADMIN role.

    @classmethod
    def all(cls) -> list[str]:
        return [
            cls.VIEW_CAMERAS,
            cls.VIEW_LIVE_VIDEO,
            cls.VIEW_RECORDINGS,
            cls.DOWNLOAD_RECORDINGS,
            cls.MANAGE_CAMERAS,
            cls.MANAGE_AI,
            cls.MANAGE_ALERTS,
            cls.MANAGE_RULES,
            cls.MANAGE_USERS,
            cls.MANAGE_INCIDENTS,
            cls.VIEW_REPORTS,
            cls.MANAGE_SYSTEM_SETTINGS,
            cls.MANAGE_BIOMETRICS,
            cls.VIEW_BIOMETRIC_EVENTS,
            cls.VIEW_SITES,
            cls.MANAGE_SITES,
        ]


VIEWER_PERMISSIONS = [
    Permissions.VIEW_CAMERAS,
    Permissions.VIEW_LIVE_VIDEO,
    Permissions.VIEW_RECORDINGS,
    Permissions.VIEW_REPORTS,
    Permissions.VIEW_SITES,
]

OPERATOR_PERMISSIONS = VIEWER_PERMISSIONS + [
    Permissions.DOWNLOAD_RECORDINGS,
    Permissions.MANAGE_ALERTS,
    Permissions.MANAGE_INCIDENTS,
    # Operators can review recognition events (section 12) but not enroll/manage
    # biometric profiles — that stays admin-only (section 17).
    Permissions.VIEW_BIOMETRIC_EVENTS,
]

# Event-First Cloud Storage Phase 1 (section 22) — spec's "Security Manager": can
# investigate events/evidence and view reports (same as Operator) plus manage sites,
# but — unlike Admin — cannot manage cameras/users/AI configuration/retention policy.
SECURITY_MANAGER_PERMISSIONS = OPERATOR_PERMISSIONS + [
    Permissions.MANAGE_SITES,
]

ADMIN_PERMISSIONS = SECURITY_MANAGER_PERMISSIONS + [
    Permissions.MANAGE_CAMERAS,
    Permissions.MANAGE_AI,
    Permissions.MANAGE_RULES,
    Permissions.MANAGE_USERS,
    Permissions.MANAGE_SYSTEM_SETTINGS,
    Permissions.MANAGE_BIOMETRICS,
]

SUPER_ADMIN_PERMISSIONS = Permissions.all()

ROLE_PERMISSION_MAP = {
    "SUPER_ADMIN": SUPER_ADMIN_PERMISSIONS,
    "ADMIN": ADMIN_PERMISSIONS,
    "SECURITY_MANAGER": SECURITY_MANAGER_PERMISSIONS,
    "OPERATOR": OPERATOR_PERMISSIONS,
    "VIEWER": VIEWER_PERMISSIONS,
}

SYSTEM_ROLES = list(ROLE_PERMISSION_MAP.keys())
