import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  Download,
  Printer,
  Shield,
  MapPin,
  FileText,
  CheckCircle,
  History,
  User,
  ClipboardList,
  AlertCircle,
  Database,
  RefreshCw,
} from 'lucide-react';
import { useSession } from '../context/SessionContext';
import {
  type DispatchRecord,
  type DispatchStatus,
  loadDispatchHistory,
  logAuditEvent,
  recordDispatch,
  updateDispatchStatusApi,
  upsertLocalDispatch,
} from '../services/persistenceService';

const MAX_DISPLAY = 40;

function statusStyles(status: DispatchStatus) {
  if (status === 'resolved') {
    return 'text-brand-green bg-brand-green/15 border-brand-green/30';
  }
  if (status === 'in_progress') {
    return 'text-brand-blue bg-brand-blue/15 border-brand-blue/30';
  }
  return 'text-brand-orange bg-brand-orange/15 border-brand-orange/30';
}

function statusLabel(status: DispatchStatus) {
  if (status === 'resolved') return 'Resolved';
  if (status === 'in_progress') return 'In Progress';
  return 'Open';
}

/**
 * Full-screen enforcement dispatch sheet with validation, SQLite+local history,
 * and print/PDF.
 */
export default function DispatchPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { session } = useSession();

  const prefillTarget = params.get('target') || params.get('hex') || '';
  const prefillHex = params.get('hex') || '';
  const prefillSource = params.get('source') || 'mixed urban sources';
  const prefillScore = params.get('score') || '—';
  const prefillAction =
    params.get('action') ||
    'Inspect site for dust suppression / emissions compliance and document evidence.';

  const [target, setTarget] = useState(prefillTarget);
  const [hexId, setHexId] = useState(prefillHex);
  const [source, setSource] = useState(prefillSource);
  const [score, setScore] = useState(prefillScore);
  const [action, setAction] = useState(prefillAction);
  const [notes, setNotes] = useState('');
  const [officer, setOfficer] = useState(session?.name || '');
  const [operator, setOperator] = useState(session?.name || 'AQI Sentinel Operator');
  const [status, setStatus] = useState<DispatchStatus>('open');
  const [signedOperator, setSignedOperator] = useState(false);
  const [signedLead, setSignedLead] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [submitted, setSubmitted] = useState<DispatchRecord | null>(null);
  const [history, setHistory] = useState<DispatchRecord[]>([]);
  const [historySource, setHistorySource] = useState<'sqlite' | 'local' | 'merged'>('local');
  const [historyLoading, setHistoryLoading] = useState(true);
  const [showHistory, setShowHistory] = useState(true);
  const [saving, setSaving] = useState(false);
  const [remoteOk, setRemoteOk] = useState<boolean | null>(null);

  const unitId = useMemo(
    () => `EN-${Math.floor(100 + Math.random() * 900)}-${Date.now().toString().slice(-4)}`,
    [],
  );
  const issuedAt = useMemo(() => new Date().toLocaleString(), []);

  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const { items, source: src } = await loadDispatchHistory();
      setHistory(items.slice(0, MAX_DISPLAY));
      setHistorySource(src);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshHistory();
  }, [refreshHistory]);

  useEffect(() => {
    setTarget(prefillTarget);
    setHexId(prefillHex);
    setSource(prefillSource);
    setScore(prefillScore);
    setAction(prefillAction);
  }, [prefillTarget, prefillHex, prefillSource, prefillScore, prefillAction]);

  const validate = (): string[] => {
    const e: string[] = [];
    if (!target.trim()) e.push('Target location is required.');
    if (!officer.trim()) e.push('Lead officer name is required.');
    if (!operator.trim()) e.push('Operator name is required.');
    if (!action.trim()) e.push('Recommended action is required.');
    if (!signedOperator) e.push('AQI Sentinel Operator must acknowledge.');
    if (!signedLead) e.push('Lead Officer In-Charge must sign.');
    return e;
  };

  const handleSubmit = async () => {
    const e = validate();
    setErrors(e);
    if (e.length) return;

    const record: DispatchRecord = {
      id: `dsp-${Date.now()}`,
      unitId,
      target: target.trim(),
      hexId: hexId.trim(),
      source: source.trim(),
      score: score.trim(),
      action: action.trim(),
      notes: notes.trim(),
      officer: officer.trim(),
      operator: operator.trim(),
      status,
      issuedAt: new Date().toISOString(),
      signedOperator,
      signedLead,
    };

    setSaving(true);
    try {
      const { items, persistedRemote } = await recordDispatch(record);
      setHistory(items.slice(0, MAX_DISPLAY));
      setHistorySource(persistedRemote ? 'merged' : 'local');
      setRemoteOk(persistedRemote);
      setSubmitted(record);
      setShowHistory(true);
      void logAuditEvent(
        'dispatch_submitted',
        { dispatchId: record.id, target: record.target, status: record.status },
        record.operator,
      );
    } finally {
      setSaving(false);
    }
  };

  const handleExportPdf = () => {
    window.print();
  };

  const loadFromHistory = (r: DispatchRecord) => {
    setTarget(r.target);
    setHexId(r.hexId);
    setSource(r.source);
    setScore(r.score);
    setAction(r.action);
    setNotes(r.notes);
    setOfficer(r.officer);
    setOperator(r.operator);
    setStatus(r.status === 'resolved' || r.status === 'in_progress' ? r.status : 'open');
    setSignedOperator(r.signedOperator);
    setSignedLead(r.signedLead);
    setSubmitted(null);
    setErrors([]);
    // Keep history open so officers can switch records quickly
    void logAuditEvent('dispatch_reloaded', { dispatchId: r.id, target: r.target });
  };

  const cycleStatusInHistory = async (r: DispatchRecord, e: React.MouseEvent) => {
    e.stopPropagation();
    const order: DispatchStatus[] = ['open', 'in_progress', 'resolved'];
    const next = order[(order.indexOf(r.status) + 1) % order.length];
    const updated: DispatchRecord = { ...r, status: next };
    const items = upsertLocalDispatch(updated);
    setHistory(items.slice(0, MAX_DISPLAY));
    void updateDispatchStatusApi(r.id, next);
    void logAuditEvent('dispatch_status_cycled', { dispatchId: r.id, status: next });
  };

  return (
    <div className="w-full h-full overflow-y-auto bg-black landing-mesh">
      <div className="max-w-3xl mx-auto px-5 md:px-8 py-8 pb-20">
        {/* Toolbar — hidden when printing */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6 print:hidden">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="min-h-[44px] inline-flex items-center gap-2 px-4 rounded-full glass-panel text-sm font-semibold text-white/90 hover:bg-white/10 transition-colors"
          >
            <ArrowLeft size={16} />
            Back
          </button>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setShowHistory((v) => !v)}
              className={`min-h-[44px] inline-flex items-center gap-2 px-4 rounded-full text-sm font-semibold border transition-colors ${
                showHistory
                  ? 'bg-brand-blue/20 border-brand-blue/40 text-brand-blue'
                  : 'glass-panel border-white/10'
              }`}
            >
              <History size={16} />
              History ({history.length})
            </button>
            <button
              type="button"
              onClick={() => void refreshHistory()}
              className="min-h-[44px] inline-flex items-center gap-2 px-3 rounded-full glass-panel text-sm font-semibold"
              title="Refresh history from server"
            >
              <RefreshCw size={15} className={historyLoading ? 'animate-spin' : ''} />
            </button>
            <button
              type="button"
              onClick={handleExportPdf}
              className="min-h-[44px] inline-flex items-center gap-2 px-4 rounded-full bg-brand-blue text-white text-sm font-bold shadow-lg shadow-brand-blue/20 hover:bg-brand-blue/90"
            >
              <Download size={16} />
              Export PDF
            </button>
            <button
              type="button"
              onClick={() => window.print()}
              className="min-h-[44px] inline-flex items-center gap-2 px-4 rounded-full glass-panel text-sm font-semibold"
            >
              <Printer size={16} />
              Print
            </button>
          </div>
        </div>

        {/* History panel — always useful for demos */}
        {showHistory && (
          <div className="glass-panel rounded-3xl p-5 mb-6 border border-white/10 print:hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
              <h2 className="text-sm font-bold text-white flex items-center gap-2">
                <History size={16} className="text-brand-blue" />
                Dispatch history
              </h2>
              <span className="inline-flex items-center gap-1.5 text-[10px] font-mono text-apple-secondary">
                <Database size={11} className="text-brand-blue" />
                {historyLoading
                  ? 'Loading…'
                  : historySource === 'sqlite'
                    ? 'SQLite'
                    : historySource === 'merged'
                      ? 'SQLite + local'
                      : 'This browser (local)'}
              </span>
            </div>
            <p className="text-[11px] text-apple-secondary mb-3">
              Click a record to reload it into the form. Click the status badge to cycle Open → In
              Progress → Resolved.
            </p>
            {history.length === 0 ? (
              <p className="text-xs text-apple-secondary">
                {historyLoading ? 'Loading dispatches…' : 'No dispatches saved yet.'}
              </p>
            ) : (
              <ul className="space-y-2 max-h-72 overflow-y-auto">
                {history.map((r) => (
                  <li key={r.id}>
                    <div className="w-full rounded-2xl bg-white/[0.04] border border-white/10 hover:border-brand-blue/40 px-3 py-2.5 transition-colors flex gap-2 items-start">
                      <button
                        type="button"
                        onClick={() => loadFromHistory(r)}
                        className="flex-1 text-left min-w-0"
                      >
                        <div className="flex justify-between gap-2">
                          <span className="text-xs font-semibold text-white truncate">
                            {r.target}
                          </span>
                        </div>
                        <div className="text-[10px] font-mono text-apple-secondary mt-0.5">
                          {r.unitId} · {new Date(r.issuedAt).toLocaleString()}
                          {r.officer ? ` · ${r.officer}` : ''}
                        </div>
                        {r.action && (
                          <p className="text-[10px] text-apple-secondary/80 mt-1 line-clamp-1">
                            {r.action}
                          </p>
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={(ev) => void cycleStatusInHistory(r, ev)}
                        className={`text-[9px] font-bold uppercase shrink-0 px-2 py-1 rounded-full border ${statusStyles(r.status)}`}
                        title="Click to cycle status"
                      >
                        {statusLabel(r.status)}
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Success banner */}
        {submitted && (
          <div className="mb-6 rounded-2xl bg-brand-green/15 border border-brand-green/30 px-4 py-3 flex flex-wrap items-center gap-3 print:hidden">
            <CheckCircle size={18} className="text-brand-green shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-brand-green">Dispatch recorded</p>
              <p className="text-[11px] text-apple-secondary">
                Unit {submitted.unitId} saved
                {remoteOk === true
                  ? ' to database and browser history'
                  : remoteOk === false
                    ? ' to browser history (server unavailable — will retry on next open)'
                    : ' to history'}
                . You can export a PDF for the field team.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowHistory(true)}
              className="text-xs font-bold text-brand-green underline"
            >
              View in history
            </button>
            <button
              type="button"
              onClick={handleExportPdf}
              className="text-xs font-bold px-3 py-1.5 rounded-full bg-brand-green/20 text-brand-green border border-brand-green/30"
            >
              Export PDF
            </button>
          </div>
        )}

        {/* Printable form */}
        <div
          id="dispatch-print-root"
          className="glass-panel-strong rounded-[28px] p-6 md:p-10 border border-white/10 print:bg-white print:text-black print:shadow-none print:border-gray-200"
        >
          {/* Header / letterhead */}
          <div className="flex items-start justify-between gap-4 mb-8 border-b border-white/10 print:border-gray-300 pb-6">
            <div>
              <div className="flex items-center gap-2 text-brand-blue print:text-black mb-2">
                <Shield size={22} />
                <span className="text-[10px] font-mono uppercase tracking-[0.2em]">
                  AQI Sentinel · Bengaluru Operations
                </span>
              </div>
              <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-white print:text-black">
                Unit Dispatch Order
              </h1>
              <p className="text-sm text-apple-secondary print:text-gray-600 mt-1">
                Evidence-backed field action sheet for pollution control operations
              </p>
            </div>
            <div className="text-right shrink-0">
              <div className="text-[10px] font-mono uppercase text-apple-secondary print:text-gray-500">
                Unit ID
              </div>
              <div className="text-lg font-mono font-bold text-white print:text-black">{unitId}</div>
              <div className="text-[10px] font-mono text-apple-secondary print:text-gray-500 mt-2">
                Issued {issuedAt}
              </div>
            </div>
          </div>

          {errors.length > 0 && (
            <div className="mb-5 rounded-2xl bg-brand-red/10 border border-brand-red/25 px-4 py-3 print:hidden">
              <div className="flex items-center gap-2 text-brand-red text-xs font-bold mb-1">
                <AlertCircle size={14} /> Validation
              </div>
              <ul className="text-[11px] text-brand-red/90 space-y-0.5 list-disc pl-4">
                {errors.map((err) => (
                  <li key={err}>{err}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Section: Dispatch details */}
          <section className="mb-6">
            <h2 className="text-[11px] font-mono font-bold uppercase tracking-widest text-brand-blue print:text-black mb-3 flex items-center gap-2">
              <ClipboardList size={14} />
              Dispatch details
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="block sm:col-span-2">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-apple-secondary print:text-gray-600">
                  Status *
                </span>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value as DispatchStatus)}
                  className="mt-1.5 w-full min-h-[44px] rounded-2xl bg-black/40 border border-white/10 px-4 text-sm text-white focus:outline-none focus:border-brand-blue/50 print:bg-white print:text-black print:border-gray-300"
                >
                  <option value="open" className="bg-apple-card">
                    Open — field action pending
                  </option>
                  <option value="in_progress" className="bg-apple-card">
                    In Progress — team deployed
                  </option>
                  <option value="resolved" className="bg-apple-card">
                    Resolved — issue closed
                  </option>
                </select>
              </label>
            </div>
          </section>

          {/* Section: Target (pre-filled) */}
          <section className="mb-6">
            <h2 className="text-[11px] font-mono font-bold uppercase tracking-widest text-brand-blue print:text-black mb-3 flex items-center gap-2">
              <MapPin size={14} />
              Target information
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="block sm:col-span-2">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-apple-secondary print:text-gray-600">
                  Location / target *
                </span>
                <input
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  className="mt-1.5 w-full min-h-[44px] rounded-2xl bg-black/40 border border-white/10 px-4 text-sm text-white focus:outline-none focus:border-brand-blue/50 print:bg-white print:text-black print:border-gray-300"
                  placeholder="e.g. Yeshwanthpur"
                />
              </label>
              <label className="block">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-apple-secondary print:text-gray-600">
                  H3 cell (debug)
                </span>
                <input
                  value={hexId}
                  onChange={(e) => setHexId(e.target.value)}
                  className="mt-1.5 w-full min-h-[44px] rounded-2xl bg-black/40 border border-white/10 px-4 text-sm font-mono text-white focus:outline-none focus:border-brand-blue/50 print:bg-white print:text-black print:border-gray-300"
                  placeholder="optional"
                />
              </label>
              <label className="block">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-apple-secondary print:text-gray-600">
                  Priority score
                </span>
                <input
                  value={score}
                  onChange={(e) => setScore(e.target.value)}
                  className="mt-1.5 w-full min-h-[44px] rounded-2xl bg-black/40 border border-white/10 px-4 text-sm font-mono text-white focus:outline-none focus:border-brand-blue/50 print:bg-white print:text-black print:border-gray-300"
                />
              </label>
              <label className="block sm:col-span-2">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-apple-secondary print:text-gray-600">
                  Dominant source / cause
                </span>
                <input
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  className="mt-1.5 w-full min-h-[44px] rounded-2xl bg-black/40 border border-white/10 px-4 text-sm text-white focus:outline-none focus:border-brand-blue/50 print:bg-white print:text-black print:border-gray-300 capitalize"
                />
              </label>
              <label className="block sm:col-span-2">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-apple-secondary print:text-gray-600">
                  Recommended action *
                </span>
                <textarea
                  value={action}
                  onChange={(e) => setAction(e.target.value)}
                  rows={3}
                  className="mt-1.5 w-full rounded-2xl bg-black/40 border border-white/10 px-4 py-3 text-sm text-white focus:outline-none focus:border-brand-blue/50 print:bg-white print:text-black print:border-gray-300"
                />
              </label>
            </div>
            <p className="text-[10px] text-apple-secondary print:text-gray-500 mt-2 leading-relaxed">
              Ranking and source mix are investigation aids based on sensors, geospatial layers, and
              satellite context — not a legal determination of fault.
            </p>
          </section>

          {/* Section: Officer details */}
          <section className="mb-6">
            <h2 className="text-[11px] font-mono font-bold uppercase tracking-widest text-brand-blue print:text-black mb-3 flex items-center gap-2">
              <User size={14} />
              Officer details
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="block">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-apple-secondary print:text-gray-600">
                  AQI Sentinel operator *
                </span>
                <input
                  value={operator}
                  onChange={(e) => setOperator(e.target.value)}
                  className="mt-1.5 w-full min-h-[44px] rounded-2xl bg-black/40 border border-white/10 px-4 text-sm text-white focus:outline-none focus:border-brand-blue/50 print:bg-white print:text-black print:border-gray-300"
                />
              </label>
              <label className="block">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-apple-secondary print:text-gray-600">
                  Lead officer in-charge *
                </span>
                <input
                  value={officer}
                  onChange={(e) => setOfficer(e.target.value)}
                  className="mt-1.5 w-full min-h-[44px] rounded-2xl bg-black/40 border border-white/10 px-4 text-sm text-white focus:outline-none focus:border-brand-blue/50 print:bg-white print:text-black print:border-gray-300"
                />
              </label>
            </div>
          </section>

          {/* Notes */}
          <section className="mb-8">
            <h2 className="text-[11px] font-mono font-bold uppercase tracking-widest text-brand-blue print:text-black mb-3 flex items-center gap-2">
              <FileText size={14} />
              Status & notes
            </h2>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={4}
              placeholder="Field observations, evidence collected, follow-ups…"
              className="w-full rounded-2xl bg-black/40 border border-white/10 px-4 py-3 text-sm text-white placeholder:text-apple-secondary/50 focus:outline-none focus:border-brand-blue/50 print:bg-white print:text-black print:border-gray-300"
            />
          </section>

          {/* Signature blocks */}
          <section className="grid grid-cols-1 sm:grid-cols-2 gap-6 pt-4 border-t border-white/10 print:border-gray-300">
            <div>
              <span className="text-[10px] font-semibold uppercase tracking-wider text-apple-secondary print:text-gray-600">
                AQI Sentinel Operator
              </span>
              <button
                type="button"
                onClick={() => setSignedOperator(true)}
                className={`mt-2 w-full min-h-[100px] rounded-2xl border border-dashed flex flex-col items-center justify-center gap-2 transition-colors print:border-gray-400 print:min-h-[90px] ${
                  signedOperator
                    ? 'border-brand-green/50 bg-brand-green/10 text-brand-green'
                    : 'border-white/20 bg-black/20 text-apple-secondary hover:border-white/40 print:bg-white'
                }`}
              >
                {signedOperator ? (
                  <>
                    <CheckCircle size={20} />
                    <span className="text-xs font-semibold font-mono text-center px-2">
                      Signed · {operator || 'Operator'}
                    </span>
                  </>
                ) : (
                  <span className="text-xs text-center px-3">Tap to acknowledge dispatch</span>
                )}
              </button>
            </div>
            <div>
              <span className="text-[10px] font-semibold uppercase tracking-wider text-apple-secondary print:text-gray-600">
                Lead Officer In-Charge
              </span>
              <button
                type="button"
                onClick={() => setSignedLead(true)}
                className={`mt-2 w-full min-h-[100px] rounded-2xl border border-dashed flex flex-col items-center justify-center gap-2 transition-colors print:border-gray-400 print:min-h-[90px] ${
                  signedLead
                    ? 'border-brand-green/50 bg-brand-green/10 text-brand-green'
                    : 'border-white/20 bg-black/20 text-apple-secondary hover:border-white/40 print:bg-white'
                }`}
              >
                {signedLead ? (
                  <>
                    <CheckCircle size={20} />
                    <span className="text-xs font-semibold font-mono text-center px-2">
                      Signed · {officer || 'Lead officer'}
                    </span>
                  </>
                ) : (
                  <span className="text-xs text-center px-3">Tap to sign as lead officer</span>
                )}
              </button>
            </div>
          </section>

          <p className="mt-6 text-[9px] font-mono text-apple-secondary/70 print:text-gray-500 text-center">
            AQI SENTINEL · CONFIDENTIAL OPERATIONAL USE · NOT A LEGAL FINDING
          </p>
        </div>

        {/* Submit — screen only */}
        <div className="mt-6 flex flex-wrap gap-3 justify-end print:hidden">
          <button
            type="button"
            onClick={handleExportPdf}
            className="min-h-[48px] px-5 rounded-2xl glass-panel text-sm font-semibold inline-flex items-center gap-2"
          >
            <Printer size={16} />
            Preview / Print PDF
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={saving}
            className="min-h-[48px] px-6 rounded-2xl bg-brand-blue hover:bg-brand-blue/90 text-white text-sm font-bold shadow-lg shadow-brand-blue/20 inline-flex items-center gap-2 disabled:opacity-60"
          >
            <Shield size={16} />
            {saving ? 'Saving…' : 'Record dispatch'}
          </button>
        </div>
      </div>

      {/* Print CSS helpers */}
      <style>{`
        @media print {
          body * { visibility: hidden !important; }
          #dispatch-print-root, #dispatch-print-root * { visibility: visible !important; }
          #dispatch-print-root {
            position: absolute !important;
            left: 0; top: 0; width: 100%;
            background: white !important;
            color: black !important;
            box-shadow: none !important;
            border: none !important;
          }
        }
      `}</style>
    </div>
  );
}
