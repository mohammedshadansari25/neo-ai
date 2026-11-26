import { useEffect, useState, type FormEvent } from "react";
import { AlertCircle, Loader2, WifiOff } from "lucide-react";
import { ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";

export function LoginPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isOffline, setIsOffline] = useState(!navigator.onLine);

  useEffect(() => {
    const onOnline = () => setIsOffline(false);
    const onOffline = () => setIsOffline(true);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (isOffline) {
      setError("You appear to be offline. Check your connection and try again.");
      return;
    }
    setError(null);
    setIsLoading(true);
    try {
      if (mode === "login") {
        await login({ email, password });
      } else {
        await register({ email, password });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError("Invalid email or password.");
        } else if (err.status === 409) {
          setError("An account with this email already exists.");
        } else if (err.status === 422) {
          setError("Enter a valid email and an 8–72 character password.");
        } else {
          setError(err.message);
        }
      } else {
        setError("Unable to reach Neo AI backend.");
      }
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1.5rem",
        backgroundColor: "var(--bg-canvas)",
      }}
    >
      <div className="neo-card" style={{ maxWidth: 400, width: "100%", padding: "2rem" }}>
        <div style={{ marginBottom: "1.5rem" }}>
          <h1 style={{ margin: "0 0 0.25rem", fontSize: "1.5rem", fontWeight: 700 }}>
            Neo AI
          </h1>
          <p style={{ margin: 0, color: "var(--text-muted)" }}>
            {mode === "login"
              ? "Sign in to your personal intelligence workspace."
              : "Create your isolated Neo AI workspace."}
          </p>
        </div>

        {isOffline && (
          <div
            role="status"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.625rem 0.75rem",
              marginBottom: "1rem",
              borderRadius: "0.375rem",
              border: "1px solid var(--status-amber)",
              color: "var(--status-amber)",
              backgroundColor: "rgba(245, 158, 11, 0.08)",
            }}
          >
            <WifiOff size={16} />
            <span>Offline — reconnect to sign in.</span>
          </div>
        )}

        {error && (
          <div
            role="alert"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.625rem 0.75rem",
              marginBottom: "1rem",
              borderRadius: "0.375rem",
              border: "1px solid var(--status-red)",
              color: "var(--status-red)",
              backgroundColor: "rgba(239, 68, 68, 0.08)",
            }}
          >
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "grid", gap: "1rem" }}>
          <label style={{ display: "grid", gap: "0.375rem" }}>
            <span style={{ fontWeight: 500 }}>Email</span>
            <input
              className="neo-input"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </label>

          <label style={{ display: "grid", gap: "0.375rem" }}>
            <span style={{ fontWeight: 500 }}>Password</span>
            <input
              className="neo-input"
              type="password"
              required
              minLength={8}
              maxLength={72}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Min 8 characters"
            />
          </label>

          <button
            type="submit"
            className="neo-btn-primary"
            disabled={isLoading || isOffline}
            style={{ width: "100%", marginTop: "0.25rem" }}
          >
            {isLoading && <Loader2 size={16} />}
            {mode === "login" ? "Sign In" : "Create Account"}
          </button>
        </form>

        <div
          style={{
            marginTop: "1.25rem",
            paddingTop: "1rem",
            borderTop: "1px solid var(--border-subtle)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            color: "var(--text-muted)",
          }}
        >
          <span>{mode === "login" ? "New to Neo AI?" : "Already have an account?"}</span>
          <button
            type="button"
            className="neo-btn-ghost"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError(null);
            }}
          >
            {mode === "login" ? "Register" : "Sign In"}
          </button>
        </div>
      </div>
    </div>
  );
}
