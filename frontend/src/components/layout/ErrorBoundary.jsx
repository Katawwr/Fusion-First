import React from "react";

// A render error in one page must never blank the whole app: show a calm fallback with a way out.
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Fusion UI error:", error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" style={{ padding: "5rem 1rem", textAlign: "center" }}>
        <h1 style={{ fontSize: "1.6rem", color: "var(--text)", marginBottom: "0.75rem" }}>
          Something went wrong on this page.
        </h1>
        <p style={{ color: "var(--muted)", marginBottom: "1.5rem" }}>
          Nothing was lost on the server. Try again, or start a new scan.
        </p>
        <button
          onClick={() => this.setState({ error: null })}
          style={{
            padding: "0.6rem 1.2rem",
            borderRadius: "0.5rem",
            border: "1px solid var(--border-strong)",
            background: "transparent",
            color: "var(--text)",
            cursor: "pointer",
            marginRight: "0.75rem",
          }}
        >
          Try again
        </button>
        <a href="/scan" style={{ color: "var(--accent-ink)" }}>
          New scan
        </a>
      </div>
    );
  }
}
