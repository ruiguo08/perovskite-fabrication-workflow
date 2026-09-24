import { Component, type ErrorInfo, type ReactNode } from "react";
import { ErrorState } from "./ErrorState";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Root render-crash guard. Without it a thrown rendering error unmounts the
 * whole React tree and the user is left on a blank page.
 */
export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled React render error", error, info.componentStack);
  }

  private readonly handleReload = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.error !== null) {
      return (
        <main className="app-loading">
          <ErrorState
            title="The application view crashed"
            message="An unexpected error interrupted this page. Reload to recover; unsaved changes are lost."
            action={
              <button
                type="button"
                className="button button--secondary"
                onClick={this.handleReload}
              >
                Reload
              </button>
            }
          />
        </main>
      );
    }
    return this.props.children;
  }
}
