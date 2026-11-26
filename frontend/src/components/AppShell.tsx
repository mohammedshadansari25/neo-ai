import { useState, type ReactNode } from "react";
import {
  Activity,
  Brain,
  Compass,
  LayoutDashboard,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";

export type AppRoute = "/" | "/memories" | "/workspace" | "/agents";

interface AppShellProps {
  currentRoute: AppRoute;
  onNavigate: (route: AppRoute) => void;
  children: ReactNode;
}

const NAV_ITEMS: Array<{ route: AppRoute; label: string; icon: typeof LayoutDashboard }> = [
  { route: "/", label: "Command Center", icon: LayoutDashboard },
  { route: "/memories", label: "Memory Explorer", icon: Brain },
  { route: "/workspace", label: "Research & Goals", icon: Compass },
  { route: "/agents", label: "Agent Center", icon: Activity },
];

export function AppShell({ currentRoute, onNavigate, children }: AppShellProps) {
  const { user, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  const sidebarContent = (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        padding: "1rem",
        gap: "1rem",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: "1.125rem", fontWeight: 700, letterSpacing: "-0.01em" }}>
          Neo AI
        </span>
        <span
          className="mono"
          style={{
            fontSize: "0.75rem",
            padding: "0.125rem 0.5rem",
            borderRadius: "9999px",
            backgroundColor: "rgba(99, 102, 241, 0.15)",
            color: "var(--accent-indigo)",
          }}
        >
          V1
        </span>
      </div>

      <nav style={{ display: "grid", gap: "0.25rem", flex: 1, alignContent: "start" }}>
        {NAV_ITEMS.map(({ route, label, icon: Icon }) => {
          const active = currentRoute === route;
          return (
            <button
              key={route}
              type="button"
              onClick={() => {
                onNavigate(route);
                setMobileOpen(false);
              }}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.625rem",
                width: "100%",
                padding: "0.625rem 0.75rem",
                borderRadius: "0.375rem",
                border: "1px solid transparent",
                backgroundColor: active ? "rgba(99, 102, 241, 0.15)" : "transparent",
                borderColor: active ? "rgba(99, 102, 241, 0.4)" : "transparent",
                color: active ? "var(--text-primary)" : "var(--text-muted)",
                cursor: "pointer",
                textAlign: "left",
                fontWeight: active ? 600 : 400,
                transition: "background-color 150ms ease, color 150ms ease",
              }}
            >
              <Icon size={16} />
              <span>{label}</span>
            </button>
          );
        })}
      </nav>

      <div
        style={{
          paddingTop: "0.75rem",
          borderTop: "1px solid var(--border-subtle)",
          display: "grid",
          gap: "0.5rem",
        }}
      >
        <div
          className="mono"
          style={{
            fontSize: "0.75rem",
            color: "var(--text-muted)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {user?.email}
        </div>
        <button type="button" className="neo-btn-ghost" onClick={() => void logout()}>
          <LogOut size={15} />
          <span>Sign Out</span>
        </button>
      </div>
    </div>
  );

  return (
    <div style={{ display: "flex", minHeight: "100vh", backgroundColor: "var(--bg-canvas)" }}>
      <aside
        className="desktop-sidebar"
        style={{
          width: 240,
          flexShrink: 0,
          backgroundColor: "var(--bg-surface)",
          borderRight: "1px solid var(--border-subtle)",
        }}
      >
        {sidebarContent}
      </aside>

      {mobileOpen && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 50,
            backgroundColor: "rgba(0,0,0,0.6)",
            display: "flex",
          }}
          onClick={() => setMobileOpen(false)}
        >
          <aside
            style={{
              width: 240,
              height: "100%",
              backgroundColor: "var(--bg-surface)",
              borderRight: "1px solid var(--border-subtle)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "flex-end", padding: "0.5rem" }}>
              <button
                type="button"
                className="neo-btn-ghost"
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation"
              >
                <X size={16} />
              </button>
            </div>
            {sidebarContent}
          </aside>
        </div>
      )}

      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0.75rem 1.5rem",
            borderBottom: "1px solid var(--border-subtle)",
          }}
        >
          <button
            type="button"
            className="neo-btn-ghost"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={16} />
          </button>
          <span className="mono" style={{ fontSize: "0.75rem", color: "var(--status-emerald)" }}>
            ● Connected
          </span>
        </header>

        <main style={{ flex: 1, padding: "1.5rem" }}>{children}</main>
      </div>
    </div>
  );
}
