import React from "react";

export default class AppErrorBoundary extends React.Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    console.error("The application could not render.", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main>
        <section className="page-section compact-section" role="alert">
          <div className="operations-panel">
            <h1>Something went wrong</h1>
            <p>The page could not be displayed. Try again or reload the app.</p>
            <div className="form-actions">
              <button className="primary-button" type="button" onClick={() => this.setState({ failed: false })}>Try again</button>
              <button className="secondary-button" type="button" onClick={() => window.location.reload()}>Reload</button>
            </div>
          </div>
        </section>
      </main>
    );
  }
}
