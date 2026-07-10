import { useState, useEffect } from "react";
import type { FormEvent } from "react";
import { askCopilot } from "../api/client";

const SUGGESTIONS = ["What is the city briefing for tomorrow?", "Which stations need inspection first?", "How should an outdoor worker prepare tomorrow?"];
const BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

interface StationOption {
  station_id: string;
  display_name: string;
}

export default function CopilotPage() {
  const [query, setQuery] = useState(SUGGESTIONS[0]);
  const [answer, setAnswer] = useState<any>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [stations, setStations] = useState<StationOption[]>([]);
  const [stationId, setStationId] = useState("");

  useEffect(() => {
    fetch(`${BASE_URL}/stations?city=bengaluru`)
      .then((r) => r.json())
      .then((data) => setStations(data.stations ?? []))
      .catch(() => {});
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault(); setLoading(true); setError("");
    try {
      const body: { query: string; station_id?: string } = { query };
      if (stationId) body.station_id = stationId;
      setAnswer(await askCopilot(body));
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to reach the copilot."); } finally { setLoading(false); }
  }
  return <main className="tool-page"><div className="page-intro"><h1>Air-quality Copilot</h1><p>Ask about forecasts, health guidance, inspection planning, or local conditions.</p></div>
    <form className="tool-form" onSubmit={submit}>
      <label htmlFor="station-select">Station <span style={{ fontWeight: 400, color: "var(--text-secondary)" }}>(optional — for station-specific questions)</span></label>
      <select id="station-select" value={stationId} onChange={(e) => setStationId(e.target.value)}>
        <option value="">-- No station selected (city-wide query) --</option>
        {stations.map((s) => <option key={s.station_id} value={s.station_id}>{s.display_name}</option>)}
      </select>
      <label htmlFor="question">Your question</label>
      <textarea id="question" value={query} onChange={(e) => setQuery(e.target.value)} required rows={4}/>
      <div className="suggestions">{SUGGESTIONS.map((item) => <button type="button" key={item} onClick={() => setQuery(item)}>{item}</button>)}</div>
      <button className="primary-button" disabled={loading}>{loading ? "Analyzing…" : "Ask Copilot"}</button>
    </form>
    {error && <p className="inline-error">{error}</p>}
    {answer && <section className="answer-card"><div className="answer-card__meta">{answer.intent?.replaceAll("_", " ")} · {answer.fallback_used ? "Data-backed response" : "AI-assisted response"}</div><p>{answer.answer}</p>{answer.warnings?.length > 0 && <small>{answer.warnings.join(" ")}</small>}</section>}
  </main>;
}
