import { useState, useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import MapView from "../components/MapView";
import HexDetailPanel from "../components/HexDetailPanel";
import { getEnforcementPriority } from "../api/client";
import type { EnforcementPriorityResponse, RankedHexagon } from "../api/types";

const TOP_K_OPTIONS = [5, 10, 25, 50];

function dominantCategory(attr: RankedHexagon["source_attribution"]): string {
  let maxKey = "traffic";
  let maxVal = 0;
  for (const [key, val] of Object.entries(attr)) {
    if (val > maxVal) {
      maxVal = val;
      maxKey = key;
    }
  }
  return maxKey.charAt(0).toUpperCase() + maxKey.slice(1);
}

export default function EnforcementPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const highlightParam = searchParams.get("highlight");
  const [topK, setTopK] = useState(10);
  const [selectedCell, setSelectedCell] = useState<string | null>(highlightParam);
  const tableRef = useRef<HTMLTableElement>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["enforcementPriority", "bengaluru", topK],
    queryFn: () => getEnforcementPriority("bengaluru", topK),
    staleTime: 60_000,
  });

  useEffect(() => {
    if (highlightParam) {
      setSelectedCell(highlightParam);
      // Scroll to row after a short delay to allow render
      const timeout = setTimeout(() => {
        const row = tableRef.current?.querySelector(
          `[data-h3="${highlightParam}"]`
        ) as HTMLElement | null;
        row?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 100);
      return () => clearTimeout(timeout);
    }
  }, [highlightParam, data]);

  const selectedHex = selectedCell
    ? data?.ranked_hexagons.find((h) => h.h3_cell === selectedCell) ?? null
    : null;

  const handleRowClick = (h3: string) => {
    setSelectedCell((prev) => (prev === h3 ? null : h3));
  };

  const options = TOP_K_OPTIONS.map((k) => (
    <option key={k} value={k}>
      Top {k}
    </option>
  ));

  let tableContent;
  if (isLoading) {
    tableContent = (
      <tbody>
        {Array.from({ length: 10 }).map((_, i) => (
          <tr key={i}>
            {Array.from({ length: 6 }).map((_, j) => (
              <td key={j}>
                <div className="skeleton skeleton--text" style={{ width: `${60 + Math.random() * 30}%` }} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    );
  } else if (isError) {
    tableContent = (
      <tbody>
        <tr>
          <td colSpan={6} style={{ textAlign: "center", padding: 40 }}>
            <div className="error-message" style={{ justifyContent: "center" }}>
              <span>Couldn't load enforcement priorities</span>
              <button className="error-message__retry" onClick={() => refetch()} type="button">
                Retry
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    );
  } else if (data) {
    tableContent = (
      <tbody>
        {data.ranked_hexagons.map((hex) => (
          <tr
            key={hex.h3_cell}
            data-h3={hex.h3_cell}
            className={`enforcement-table__row${
              selectedCell === hex.h3_cell ? " enforcement-table__row--active" : ""
            }${
              highlightParam === hex.h3_cell ? " enforcement-table__row--highlighted" : ""
            }`}
            onClick={() => handleRowClick(hex.h3_cell)}
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                handleRowClick(hex.h3_cell);
              }
            }}
          >
            <td className="enforcement-table__mono">{hex.rank}</td>
            <td className="enforcement-table__mono" style={{ fontSize: 12 }}>
              {hex.h3_cell.slice(0, 10)}…
            </td>
            <td className="enforcement-table__score">{hex.priority_score.toFixed(4)}</td>
            <td className="enforcement-table__mono">{hex.scoring_breakdown.exposure_weight.toFixed(3)}</td>
            <td className="enforcement-table__mono">{hex.scoring_breakdown.attributable_magnitude.toFixed(3)}</td>
            <td className="enforcement-table__mono">{hex.scoring_breakdown.actionability_weight.toFixed(3)}</td>
          </tr>
        ))}
      </tbody>
    );
  }

  const mapData = data?.ranked_hexagons.map((h) => ({
    h3_cell: h.h3_cell,
    value: h.priority_score,
    fused_pm25: h.fused_pm25,
  })) as Array<{ h3_cell: string; value: number; fused_pm25: number | null }> | undefined;

  return (
    <div className="enforcement-page">
      <div className="enforcement-page__controls">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <h2>Enforcement Priorities</h2>
          {data && (
            <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
              {data.city} · {data.total_hexagons} hexagons · {data.computed_at.slice(0, 10)}
            </span>
          )}
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14 }}>
          Show:
          <select
            className="enforcement-page__top-k"
            value={topK}
            onChange={(e) => setTopK(Number(e.target.value))}
          >
            {options}
          </select>
        </label>
      </div>

      <div className="enforcement-page__content">
        <div className="enforcement-page__table-wrapper">
          <table className="enforcement-table" ref={tableRef}>
            <thead>
              <tr>
                <th>Rank</th>
                <th>Hexagon</th>
                <th>Priority Score</th>
                <th>Exposure</th>
                <th>Magnitude</th>
                <th>Actionability</th>
              </tr>
            </thead>
            {tableContent}
          </table>
        </div>

        <div className="enforcement-page__map-wrapper">
          <MapView
            city="bengaluru"
            colorBy="priority_score"
            onHexagonClick={(h3) => setSelectedCell(h3)}
            highlightedCells={selectedCell ? [selectedCell] : []}
            hexagonData={mapData as any}
            fullHeight
          />
        </div>
      </div>

      {selectedHex && (
        <HexDetailPanel
          hexagon={selectedHex}
          onClose={() => setSelectedCell(null)}
        />
      )}
    </div>
  );
}
