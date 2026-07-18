import { StrictMode, Component, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';

/** Catch render crashes so users see a message instead of a pure black void. */
class RootErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div
          style={{
            minHeight: '100%',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 24,
            background: '#000',
            color: '#fff',
            fontFamily: 'system-ui, sans-serif',
            textAlign: 'center',
            gap: 12,
          }}
        >
          <h1 style={{ fontSize: 18, margin: 0 }}>AQI Sentinel failed to start</h1>
          <p style={{ color: '#8E8E93', fontSize: 13, maxWidth: 420, lineHeight: 1.5, margin: 0 }}>
            {this.state.error.message || 'Unknown render error'}
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{
              marginTop: 8,
              padding: '10px 18px',
              borderRadius: 999,
              border: 'none',
              background: '#0A84FF',
              color: '#fff',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

const rootEl = document.getElementById('root');
if (!rootEl) {
  document.body.innerHTML =
    '<p style="color:#fff;font-family:system-ui;padding:24px">Missing #root element.</p>';
} else {
  createRoot(rootEl).render(
    <StrictMode>
      <RootErrorBoundary>
        <App />
      </RootErrorBoundary>
    </StrictMode>,
  );
}

