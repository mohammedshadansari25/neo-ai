import { useEffect, useState } from "react";
import { AppShell, type AppRoute } from "./components/AppShell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { LoginPage } from "./pages/LoginPage";

function normalizeRoute(pathname: string): AppRoute {
  if (pathname === "/memories" || pathname === "/workspace" || pathname === "/agents") {
    return pathname;
  }
  return "/";
}

const ROUTE_TITLES: Record<AppRoute, string> = {
  "/": "Command Center",
  "/memories": "Memory & Knowledge Explorer",
  "/workspace": "Research & Goal Workspace",
  "/agents": "Agent Center",
};

function AuthenticatedApp() {
  const { user, isInitializing } = useAuth();
  const [route, setRoute] = useState<AppRoute>(() => normalizeRoute(window.location.pathname));

  useEffect(() => {
    const onPopState = () => setRoute(normalizeRoute(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  function navigate(nextRoute: AppRoute) {
    if (nextRoute !== route) {
      window.history.pushState({}, "", nextRoute);
      setRoute(nextRoute);
    }
  }

  if (isInitializing) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-muted)",
        }}
      >
        Initializing Neo AI...
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  return (
    <AppShell currentRoute={route} onNavigate={navigate}>
      <div className="neo-card" style={{ padding: "1.5rem" }}>
        <h1 style={{ margin: "0 0 0.5rem", fontSize: "1.5rem", fontWeight: 700 }}>
          {ROUTE_TITLES[route]}
        </h1>
        <p style={{ margin: 0, color: "var(--text-muted)" }}>
          Signed in as <span className="mono">{user.email}</span>. Workspace modules unlock in Days 2–13.
        </p>
      </div>
    </AppShell>
  );
}

export function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <AuthenticatedApp />
      </AuthProvider>
    </ErrorBoundary>
  );
}

export default App;
