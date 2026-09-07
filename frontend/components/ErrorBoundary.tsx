import { Component, type ErrorInfo, type ReactNode } from "react";

// Last-resort guard: a render-time exception anywhere in the dashboard tree
// shows a recoverable message instead of a blank white screen mid-demo. React
// error boundaries must be class components — there is no hook equivalent.

type Props = { children: ReactNode };
type State = { failed: boolean };

class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Dashboard render error:", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="crash">
        <h1>AEGIS</h1>
        <p>The dashboard hit an unexpected error. Live network state is unaffected.</p>
        <button onClick={() => window.location.reload()}>RELOAD DASHBOARD</button>
      </div>
    );
  }
}

export default ErrorBoundary;
