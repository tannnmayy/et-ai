import type { RankedHexagon, HexagonAttribution } from "../api/types";

const ATTRIBUTION_COLORS: Record<string, string> = {
  traffic: "#2D5DA8",
  industrial: "#7E0023",
  construction: "#F58220",
  burning: "#E2401C",
};

const ATTRIBUTION_LABELS: Record<string, string> = {
  traffic: "Traffic",
  industrial: "Industrial",
  construction: "Construction",
  burning: "Burning",
};

const CPCB_BREAKPOINTS = [
  { max: 30, band: "Good", color: "#4CAF50", text: "#1D1D1F" },
  { max: 60, band: "Satisfactory", color: "#A9C93A", text: "#1D1D1F" },
  { max: 90, band: "Moderate", color: "#F5C518", text: "#1D1D1F" },
  { max: 120, band: "Poor", color: "#F58220", text: "#FFFFFF" },
  { max: 250, band: "Very Poor", color: "#E2401C", text: "#FFFFFF" },
  { max: Infinity, band: "Severe", color: "#7E0023", text: "#FFFFFF" },
];

function pm25ToStyle(pm25: number | null): { color: string; text: string } {
  if (pm25 === null || pm25 === undefined) return { color: "#F5C518", text: "#1D1D1F" };
  for (const bp of CPCB_BREAKPOINTS) {
    if (pm25 <= bp.max) return { color: bp.color, text: bp.text };
  }
  return { color: "#7E0023", text: "#FFFFFF" };
}

interface HexDetailPanelProps {
  hexagon: RankedHexagon | HexagonAttribution;
  onClose: () => void;
}

function hasSourceAttribution(hex: RankedHexagon | HexagonAttribution): hex is RankedHexagon | HexagonAttribution {
  return "source_attribution" in hex;
}

function hasFusedPm25(hex: RankedHexagon | HexagonAttribution): hex is RankedHexagon | (HexagonAttribution & { fused_pm25?: number | null }) {
  return "fused_pm25" in hex;
}

export default function HexDetailPanel({ hexagon, onClose }: HexDetailPanelProps) {
  const pm25 = hasFusedPm25(hexagon) ? hexagon.fused_pm25 ?? null : null;
  const pm25Style = pm25ToStyle(pm25);
  const attr = hasSourceAttribution(hexagon) ? hexagon.source_attribution : null;
  const method = "method" in hexagon ? hexagon.method : null;

  const total =
    attr
      ? attr.traffic + attr.industrial + attr.construction + attr.burning
      : 0;

  return (
    <div className="hex-detail-panel" role="dialog" aria-label="Hexagon details">
      <div className="hex-detail-panel__header">
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-secondary)" }}>
          {(hexagon as RankedHexagon).h3_cell || (hexagon as HexagonAttribution).h3_cell}
        </span>
        <button
          className="hex-detail-panel__close"
          onClick={onClose}
          type="button"
          aria-label="Close detail panel"
        >
          ✕
        </button>
      </div>

      <div className="hex-detail-panel__pm25" style={{ color: pm25Style.color }}>
        {pm25 !== null ? `${pm25.toFixed(1)}` : "—"}
      </div>
      <div className="hex-detail-panel__label">µg/m³ PM₂.₅</div>

      {'rank' in hexagon && (
        <div className="hex-detail-panel__section">
          <div className="hex-detail-panel__section-title">Priority Score</div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 600 }}>
            {hexagon.priority_score.toFixed(4)}
          </div>
        </div>
      )}

      {attr && total > 0 && (
        <div className="hex-detail-panel__section">
          <div className="hex-detail-panel__section-title">Source Attribution</div>
          <div className="attribution-bar">
            {(["traffic", "industrial", "construction", "burning"] as const).map((key) => {
              const frac = attr[key] / total;
              if (frac === 0) return null;
              return (
                <div
                  key={key}
                  className="attribution-bar__segment"
                  style={{
                    flex: frac,
                    backgroundColor: ATTRIBUTION_COLORS[key],
                  }}
                  title={`${ATTRIBUTION_LABELS[key]}: ${(frac * 100).toFixed(0)}%`}
                />
              );
            })}
          </div>
          <div className="attribution-labels">
            {(["traffic", "industrial", "construction", "burning"] as const).map((key) => {
              const frac = attr[key] / total;
              if (frac === 0) return null;
              return (
                <div key={key} className="attribution-label">
                  <span className="attribution-label__dot" style={{ backgroundColor: ATTRIBUTION_COLORS[key] }} />
                  <span>{ATTRIBUTION_LABELS[key]}</span>
                  <span className="attribution-label__value">{(frac * 100).toFixed(0)}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {method && (
        <div className="hex-detail-panel__section">
          <div className="hex-detail-panel__section-title">Method</div>
          <span className="hex-detail-panel__method">{method}</span>
        </div>
      )}
    </div>
  );
}
