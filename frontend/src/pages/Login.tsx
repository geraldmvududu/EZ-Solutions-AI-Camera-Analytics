import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password, rememberMe);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to reach the server");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-base-950 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-2xl font-bold text-slate-50 tracking-tight">EZ SOLUTIONS</div>
          <div className="text-sm text-accent-500 font-medium mt-1">AI Camera Analytics Platform</div>
        </div>

        <form onSubmit={handleSubmit} className="bg-base-900 border border-base-700 rounded-xl p-6 space-y-4">
          <h2 className="text-slate-200 font-semibold text-center mb-2">Sign in</h2>

          {error && (
            <div className="text-sm text-severity-critical bg-severity-critical/10 border border-severity-critical/30 rounded px-3 py-2">
              {error}
            </div>
          )}

          <div>
            <label className="block text-xs text-slate-400 mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md bg-base-800 border border-base-600 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-accent-500"
              placeholder="admin@ezsolutions.local"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md bg-base-800 border border-base-600 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-accent-500"
            />
          </div>

          <label className="flex items-center gap-2 text-xs text-slate-400">
            <input type="checkbox" checked={rememberMe} onChange={(e) => setRememberMe(e.target.checked)} />
            Remember me
          </label>

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-accent-600 hover:bg-accent-500 disabled:opacity-50 text-white font-medium py-2 text-sm transition-colors"
          >
            {submitting ? "Signing in..." : "Sign in"}
          </button>

          <div className="text-center text-xs text-slate-500 pt-1">
            <button type="button" className="hover:text-slate-300">
              Forgot password?
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
