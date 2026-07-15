import React, { useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  Download,
  Printer,
  Shield,
  MapPin,
  FileText,
  CheckCircle,
} from 'lucide-react';
import { useSession } from '../context/SessionContext';

/**
 * Full-screen enforcement dispatch sheet.
 * Supports browser print / PDF export and a signature field for demo use.
 */
export default function DispatchPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { session } = useSession();
  const printRef = useRef<HTMLDivElement>(null);

  const target = params.get('target') || params.get('hex') || 'Priority hexagon';
  const source = params.get('source') || 'mixed urban sources';
  const score = params.get('score') || '—';
  const action = params.get('action') || 'Inspect site for dust control compliance and document evidence.';

  const [notes, setNotes] = useState('');
  const [officer, setOfficer] = useState(session?.name || '');
  const [signed, setSigned] = useState(false);
  const unitId = useMemo(
    () => `EN-${Math.floor(100 + Math.random() * 900)}-${Date.now().toString().slice(-4)}`,
    [],
  );
  const issuedAt = useMemo(() => new Date().toLocaleString(), []);

  const handleExportPdf = () => {
    // Browser print-to-PDF keeps dependencies light and works offline in demos
    window.print();
  };

  return (
    <div className="w-full h-full overflow-y-auto bg-black landing-mesh">
      <div className="max-w-3xl mx-auto px-5 md:px-8 py-8 pb-20">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6 print:hidden">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="min-h-[44px] inline-flex items-center gap-2 px-4 rounded-full glass-panel text-sm font-semibold text-white/90 hover:bg-white/10 transition-colors"
          >
            <ArrowLeft size={16} />
            Back
          </button>
          <div className="flex items-center gap-2">
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

        <div
          ref={printRef}
          className="glass-panel-strong rounded-[28px] p-6 md:p-10 border border-white/10 print:bg-white print:text-black print:shadow-none"
        >
          <div className="flex items-start justify-between gap-4 mb-8 border-b border-white/10 print:border-black/20 pb-6">
            <div>
              <div className="flex items-center gap-2 text-brand-blue print:text-black mb-2">
                <Shield size={20} />
                <span className="text-[10px] font-mono uppercase tracking-[0.2em]">
                  AQI Sentinel · Enforcement Dispatch
                </span>
              </div>
              <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-white print:text-black">
                Unit Dispatch Order
              </h1>
              <p className="text-sm text-apple-secondary print:text-gray-600 mt-1">
                Evidence-backed field action sheet for Bengaluru operations
              </p>
            </div>
            <div className="text-right">
              <div className="text-[10px] font-mono uppercase text-apple-secondary print:text-gray-500">
                Unit ID
              </div>
              <div className="text-lg font-mono font-bold text-white print:text-black">{unitId}</div>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
            <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-4 print:bg-gray-50 print:border-gray-200">
              <div className="text-[10px] font-mono uppercase text-apple-secondary print:text-gray-500 mb-1 flex items-center gap-1.5">
                <MapPin size={12} /> Target
              </div>
              <div className="text-sm font-semibold text-white print:text-black break-all">{target}</div>
            </div>
            <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-4 print:bg-gray-50 print:border-gray-200">
              <div className="text-[10px] font-mono uppercase text-apple-secondary print:text-gray-500 mb-1">
                Priority score
              </div>
              <div className="text-sm font-mono font-bold text-white print:text-black">{score}</div>
            </div>
            <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-4 print:bg-gray-50 print:border-gray-200">
              <div className="text-[10px] font-mono uppercase text-apple-secondary print:text-gray-500 mb-1">
                Dominant source signal
              </div>
              <div className="text-sm font-semibold text-white print:text-black capitalize">
                {source.replace(/_/g, ' ')}
              </div>
            </div>
            <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-4 print:bg-gray-50 print:border-gray-200">
              <div className="text-[10px] font-mono uppercase text-apple-secondary print:text-gray-500 mb-1">
                Issued
              </div>
              <div className="text-sm font-mono text-white print:text-black">{issuedAt}</div>
            </div>
          </div>

          <div className="mb-6">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-apple-secondary print:text-gray-600 mb-2">
              <FileText size={14} />
              Recommended action
            </div>
            <p className="text-sm text-white/90 print:text-black leading-relaxed bg-brand-blue/10 print:bg-blue-50 border border-brand-blue/20 print:border-blue-100 rounded-2xl p-4">
              {action}
            </p>
            <p className="text-[11px] text-apple-secondary print:text-gray-500 mt-2 leading-relaxed">
              This ranking is an investigation aid based on sensor fusion and geospatial context.
              It is not a legal determination of fault.
            </p>
          </div>

          <label className="block mb-6">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-apple-secondary print:text-gray-600">
              Field notes
            </span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={4}
              placeholder="Observations, site conditions, evidence collected…"
              className="mt-2 w-full rounded-2xl bg-black/40 border border-white/10 px-4 py-3 text-sm text-white placeholder:text-apple-secondary/50 focus:outline-none focus:border-brand-blue/50 print:bg-white print:text-black print:border-gray-300"
            />
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 pt-4 border-t border-white/10 print:border-gray-200">
            <label className="block">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-apple-secondary print:text-gray-600">
                Officer name
              </span>
              <input
                value={officer}
                onChange={(e) => setOfficer(e.target.value)}
                className="mt-2 w-full min-h-[44px] rounded-2xl bg-black/40 border border-white/10 px-4 text-sm text-white focus:outline-none focus:border-brand-blue/50 print:bg-white print:text-black print:border-gray-300"
              />
            </label>
            <div>
              <span className="text-[11px] font-semibold uppercase tracking-wider text-apple-secondary print:text-gray-600">
                Signature
              </span>
              <button
                type="button"
                onClick={() => setSigned(true)}
                className={`mt-2 w-full min-h-[88px] rounded-2xl border border-dashed flex flex-col items-center justify-center gap-2 transition-colors print:border-gray-400 ${
                  signed
                    ? 'border-brand-green/50 bg-brand-green/10 text-brand-green'
                    : 'border-white/20 bg-black/20 text-apple-secondary hover:border-white/40 print:bg-white'
                }`}
              >
                {signed ? (
                  <>
                    <CheckCircle size={20} />
                    <span className="text-xs font-semibold font-mono">
                      Signed · {officer || 'Officer'}
                    </span>
                  </>
                ) : (
                  <span className="text-xs">Tap to acknowledge dispatch</span>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
