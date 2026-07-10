import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { getCityBriefing, getTravelReadiness, getWeatherSummary } from "../api/client";

function Card({ title, children }: { title: string; children: ReactNode }) {
  return <article className="snapshot-card"><h3>{title}</h3>{children}</article>;
}

export default function OperationsSnapshot() {
  const briefing = useQuery({ queryKey: ["briefing"], queryFn: getCityBriefing, retry: 1 });
  const travel = useQuery({ queryKey: ["travel", "general"], queryFn: () => getTravelReadiness("general"), retry: 1 });
  const weather = useQuery({ queryKey: ["weather"], queryFn: getWeatherSummary, retry: 1 });
  const error = [briefing.error, travel.error, weather.error].find(Boolean) as Error | undefined;
  if (error) return <section className="snapshot"><p className="inline-error">Live operational summary is unavailable: {error.message}</p></section>;
  return <section className="snapshot" aria-label="Live operational summary">
    <Card title="City briefing">{briefing.isLoading ? <p>Loading…</p> : <p>{briefing.data?.executive_summary || briefing.data?.summary || "No briefing available."}</p>}</Card>
    <Card title="Travel readiness">{travel.isLoading ? <p>Loading…</p> : <><strong>{travel.data?.recommendation || travel.data?.readiness || "Check conditions"}</strong><p>{travel.data?.summary || travel.data?.message}</p></>}</Card>
    <Card title="Tomorrow’s weather">{weather.isLoading ? <p>Loading…</p> : <><strong>{weather.data?.risk_level || weather.data?.weather_risk || "Forecast"}</strong><p>{weather.data?.summary || weather.data?.narrative}</p></>}</Card>
  </section>;
}
