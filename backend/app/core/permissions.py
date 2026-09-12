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
        ]


VIEWER_PERMISSIONS = [
    Permissions.VIEW_CAMERAS,
    Permissions.VIEW_LIVE_VIDEO,
    Permissions.VIEW_RECORDINGS,
    Permissions.VIEW_REPORTS,
]

OPERATOR_PERMISSIONS = VIEWER_PERMISSIONS + [
    Permissions.DOWNLOAD_RECORDINGS,
    Permissions.MANAGE_ALERTS,
    Permissions.MANAGE_INCIDENTS,
    # Operators can review recognition events (section 12) but not enroll/manage
    # biometric profiles — that stays admin-only (section 17).
    Permissions.VIEW_BIOMETRIC_EVENTS,
]

ADMIN_PERMISSIONS = OPERATOR_PERMISSIONS + [
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
    "OPERATOR": OPERATOR_PERMISSIONS,
    "VIEWER": VIEWER_PERMISSIONS,
}

SYSTEM_ROLES = list(ROLE_PERMISSION_MAP.keys())
