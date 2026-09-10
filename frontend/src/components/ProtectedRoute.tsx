import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export function ProtectedRoute({ children, permission }: { children: ReactNode; permission?: string }) {
  const { user, loading, hasPermission } = useAuth();

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-slate-500">Loading...</div>;
  }
  if (!user) return <Navigate to="/login" replace />;
  if (permission && !hasPermission(permission)) {
    return <Navigate to="/dashboard" replace />;
  }
  return <>{children}</>;
}
