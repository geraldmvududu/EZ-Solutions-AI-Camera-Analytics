import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

export function Topbar({ title }: { title: string }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <header className="h-16 shrink-0 border-b border-base-700 bg-base-900/60 flex items-center justify-between px-6">
      <h1 className="text-lg font-semibold text-slate-100">{title}</h1>
      <div className="flex items-center gap-4">
        <div className="text-right leading-tight">
          <div className="text-sm text-slate-200">{user?.full_name || user?.email}</div>
          <div className="text-xs text-slate-500">{user?.role}</div>
        </div>
        <button
          onClick={handleLogout}
          className="text-sm px-3 py-1.5 rounded-md border border-base-600 text-slate-300 hover:bg-base-800"
        >
          Logout
        </button>
      </div>
    </header>
  );
}
