import { NavLink } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: "▦" },
  { to: "/live-cameras", label: "Live Cameras", icon: "▣" },
  { to: "/cameras", label: "Cameras", icon: "◉", permission: "manage_cameras" },
  { to: "/events", label: "Events", icon: "☰" },
  { to: "/alerts", label: "Alerts", icon: "⚠" },
  { to: "/recordings", label: "Recordings", icon: "▶" },
  { to: "/rules", label: "Rules", icon: "⚙", permission: "manage_rules" },
  { to: "/zones", label: "Zones & Tripwires", icon: "◈", permission: "manage_rules" },
  { to: "/incidents", label: "Incidents", icon: "⛨" },
  { to: "/analytics", label: "AI Analytics", icon: "▨", permission: "view_reports" },
  { to: "/system-health", label: "System Health", icon: "♥" },
  { to: "/users", label: "Users", icon: "◍", permission: "manage_users" },
  { to: "/audit-logs", label: "Audit Logs", icon: "▤", permission: "manage_system_settings" },
];

export function Sidebar() {
  const { hasPermission } = useAuth();

  return (
    <aside className="w-60 shrink-0 border-r border-base-700 bg-base-900 flex flex-col">
      <div className="px-5 py-5 border-b border-base-700">
        <div className="text-lg font-bold tracking-tight text-slate-50">EZ SOLUTIONS</div>
        <div className="text-xs text-accent-500 font-medium">AI Camera Analytics</div>
      </div>
      <nav className="flex-1 overflow-y-auto py-3">
        {NAV_ITEMS.filter((item) => !item.permission || hasPermission(item.permission)).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-5 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-accent-600/15 text-accent-500 border-r-2 border-accent-500"
                  : "text-slate-400 hover:text-slate-100 hover:bg-base-800"
              }`
            }
          >
            <span className="text-base leading-none">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
