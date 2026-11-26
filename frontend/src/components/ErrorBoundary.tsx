import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message || "Unexpected render error" };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Neo AI UI ErrorBoundary:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
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
          <div className="neo-card" style={{ maxWidth: 440, width: "100%", padding: "1.5rem" }}>
            <h2 style={{ margin: "0 0 0.5rem", fontSize: "1.125rem", color: "var(--status-red)" }}>
              Something went wrong
            </h2>
            <p style={{ margin: "0 0 1rem", color: "var(--text-muted)" }}>{this.state.message}</p>
            <button
              type="button"
              className="neo-btn-primary"
              onClick={() => window.location.reload()}
            >
              Reload workspace
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
