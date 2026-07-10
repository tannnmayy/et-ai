import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getEnforcementPriority } from "../api/client";
import type { RankedHexagon } from "../api/types";

const DOMINANT_LABELS: Record<string, string> = {
  traffic: "Traffic",
  industrial: "Industrial",
  construction: "Construction",
  burning: "Burning",
};

const REQUEST_TIMEOUT_MS = 15_000;

function dominantCategory(attr: RankedHexagon["source_attribution"]): string {
  let maxKey = "traffic";
  let maxVal = 0;

  for (const [key, value] of Object.entries(attr)) {
    if (value > maxVal) {
      maxVal = value;
      maxKey = key;
    }
  }

  return DOMINANT_LABELS[maxKey] || maxKey;
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      reject(
        new Error(
          `Enforcement data timed out after ${Math.round(timeoutMs / 1000)} seconds.`
        )
      );
    }, timeoutMs);

    promise
      .then((result) => {
        window.clearTimeout(timeoutId);
        resolve(result);
      })
      .catch((requestError) => {
        window.clearTimeout(timeoutId);
        reject(requestError);
      });
  });
}

interface TopEnforcementSectionProps {
  city?: string;
  limit?: number;
}

export default function TopEnforcementSection({
  city = "bengaluru",
  limit = 5,
}: TopEnforcementSectionProps) {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["enforcementPriority", city, limit],
    queryFn: () =>
      withTimeout(
        getEnforcementPriority(city, limit),
        REQUEST_TIMEOUT_MS
      ),
    staleTime: 60_000,
    retry: 1,
    retryDelay: 1_000,
  });

  return (
    <section className="top-enforcement">
      <div className="top-enforcement__header">
        <h2>Top Enforcement Priorities</h2>

        <Link to="/enforcement" className="top-enforcement__view-all">
          View all →
        </Link>
      </div>

      {isLoading && (
        <div>
          {Array.from({ length: limit }).map((_, index) => (
            <div key={index} className="skeleton skeleton--card" />
          ))}
        </div>
      )}

      {isError && (
        <div className="error-message" role="alert">
          <span>Couldn&apos;t load enforcement priorities.</span>

          <span style={{ fontSize: 12, opacity: 0.7 }}>
            {(error as Error)?.message}
          </span>

          <button
            className="error-message__retry"
            onClick={() => refetch()}
            type="button"
          >
            Retry
          </button>
        </div>
      )}

      {!isLoading &&
        !isError &&
        data?.ranked_hexagons.map((hex) => (
          <Link
            key={hex.h3_cell}
            to={`/enforcement?highlight=${hex.h3_cell}`}
            className="enforcement-card"
          >
            <div className="enforcement-card__top">
              <span className="enforcement-card__rank">#{hex.rank}</span>

              <span className="enforcement-card__score">
                {hex.priority_score.toFixed(4)}
              </span>
            </div>

            <div className="enforcement-card__details">
              <span className="enforcement-card__detail">
                <span className="enforcement-card__detail-label">
                  Dominant:
                </span>
                {dominantCategory(hex.source_attribution)}
              </span>

              {hex.fused_pm25 !== null && (
                <span className="enforcement-card__detail">
                  <span className="enforcement-card__detail-label">
                    PM₂.₅:
                  </span>

                  <span className="enforcement-card__pm25">
                    {hex.fused_pm25.toFixed(1)} µg/m³
                  </span>
                </span>
              )}
            </div>
          </Link>
        ))}

      {!isLoading &&
        !isError &&
        data?.ranked_hexagons.length === 0 && (
          <div className="error-message">
            No enforcement-priority cells are available for this city yet.
          </div>
        )}
    </section>
  );
}