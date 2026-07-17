import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  useSendMessage,
  fetchCopilotSuggestions,
  prefetchCopilot,
  isGenericCopilotRefuse,
  deriveCopilotMode,
  formatCopilotError,
  type CopilotSuggestion,
  type ConversationTurn,
} from '../services/copilotService';
import { useMapCopilotContext } from '../context/MapCopilotContext';
import { ChatMessage, ReasoningStep } from '../types';
import { useNavigate } from 'react-router-dom';
import { useSession } from '../context/SessionContext';
import { useT } from '../i18n/useT';
import {
  Bot,
  Send,
  ChevronRight,
  ChevronDown,
  CheckCircle,
  XCircle,
  Shield,
  Map,
  AlertCircle,
  BookOpen,
  KeyRound,
  Route,
  Sparkles,
  Scale,
  Wind,
  Eye,
  EyeOff,
  Zap,
  Database,
  Wrench,
  Loader2,
  FlaskConical,
  MessageSquare,
  X,
  MapPin,
} from 'lucide-react';

/** Build a rich reasoning list from audit_trail.reasoning_trace (+ tools fallback). */
function buildReasoningSteps(data: any): ReasoningStep[] {
  const audit = data?.audit_trail ?? {};
  const trace: any[] = Array.isArray(audit.reasoning_trace) ? audit.reasoning_trace : [];
  const steps: ReasoningStep[] = [];

  if (trace.length > 0) {
    trace.forEach((entry, index) => {
      const type = String(entry.type || 'step');
      let step = String(entry.detail || type);
      if (type === 'tool' && entry.tool) {
        const name = String(entry.tool).replace(/^tool_/, '').replace(/_/g, ' ');
        step = entry.success ? `Tool OK: ${name}` : `Tool failed: ${name}`;
        if (entry.arguments && Object.keys(entry.arguments).length > 0) {
          const keys = Object.keys(entry.arguments)
            .filter((k) => !k.startsWith('_'))
            .slice(0, 3)
            .map((k) => `${k}=${String(entry.arguments[k]).slice(0, 24)}`)
            .join(', ');
          if (keys) step += ` (${keys})`;
        }
      }
      steps.push({
        id: `trace-${index}`,
        step,
        completed: entry.success !== false,
        type,
        meta: entry.backend
          ? `backend=${entry.backend}`
          : entry.provider
            ? `provider=${entry.provider}${entry.gemini_key_index ? ` key#${entry.gemini_key_index}` : ''}`
            : entry.cache_key
              ? `key=${String(entry.cache_key).slice(0, 12)}…`
              : undefined,
      });
    });
  } else {
    (audit.tools_called ?? []).forEach((tool: any, index: number) => {
      steps.push({
        id: `tool-${index}`,
        step: `${tool.success ? 'Retrieved' : 'Could not retrieve'} ${String(tool.tool || '')
          .replace(/^tool_/, '')
          .replace(/_/g, ' ')}`,
        completed: Boolean(tool.success),
        type: 'tool',
      });
    });
  }

  if (audit.knowledge_base_used && !steps.some((s) => s.type === 'knowledge_base')) {
    steps.push({
      id: 'kb',
      step: `Knowledge base used (${audit.knowledge_backend || 'rag'})`,
      completed: true,
      type: 'knowledge_base',
    });
  }

  if ((audit.fallback_used || data.fallback_used) && !steps.some((s) => s.type === 'fallback')) {
    steps.push({
      id: 'fallback',
      step: 'Fell back to deterministic / grounded agents',
      completed: true,
      type: 'fallback',
    });
  }

  return steps;
}

function stepIcon(type?: string, completed?: boolean) {
  if (type === 'knowledge_base') return <BookOpen size={12} className="text-emerald-400 shrink-0 mt-0.5" />;
  if (type === 'cache') return <Database size={12} className="text-violet-400 shrink-0 mt-0.5" />;
  if (type === 'whatif') return <FlaskConical size={12} className="text-fuchsia-400 shrink-0 mt-0.5" />;
  if (type === 'map') return <Map size={12} className="text-fuchsia-400 shrink-0 mt-0.5" />;
  if (type === 'memory') return <MessageSquare size={12} className="text-cyan-400 shrink-0 mt-0.5" />;
  if (type === 'llm' || type === 'plan') return <KeyRound size={12} className="text-amber-400 shrink-0 mt-0.5" />;
  if (type === 'route' || type === 'agent' || type === 'mode')
    return <Route size={12} className="text-sky-400 shrink-0 mt-0.5" />;
  if (type === 'grounding') return <Shield size={12} className="text-teal-400 shrink-0 mt-0.5" />;
  if (type === 'fallback' || type === 'llm_error' || type === 'llm_unavailable') {
    return <AlertCircle size={12} className="text-orange-400 shrink-0 mt-0.5" />;
  }
  if (completed === false) return <XCircle size={12} className="text-brand-red shrink-0 mt-0.5" />;
  return <CheckCircle size={12} className="text-brand-green shrink-0 mt-0.5" />;
}

function categoryIcon(category: string) {
  const c = category.toLowerCase();
  if (c.includes('policy')) return <Scale size={12} className="text-emerald-400" />;
  if (c.includes('enforce')) return <Shield size={12} className="text-brand-orange" />;
  if (c.includes('what')) return <FlaskConical size={12} className="text-fuchsia-400" />;
  if (c.includes('weather')) return <Wind size={12} className="text-sky-400" />;
  return <Sparkles size={12} className="text-brand-blue" />;
}

function modeBadgeStyle(mode: string): string {
  if (mode === 'heuristic_fallback')
    return 'bg-orange-900/40 border-orange-700/40 text-orange-300';
  if (mode === 'fast_path') return 'bg-sky-900/40 border-sky-700/40 text-sky-300';
  if (mode === 'tool_agent') return 'bg-indigo-900/40 border-indigo-700/40 text-indigo-300';
  return 'bg-apple-card border-apple-border text-apple-secondary';
}

function modeIcon(mode: string) {
  if (mode === 'heuristic_fallback') return <AlertCircle size={10} />;
  if (mode === 'fast_path') return <Zap size={10} />;
  return <Wrench size={10} />;
}

const LOADING_HINT_KEYS = [
  'copilot.loading.resolve',
  'copilot.loading.tools',
  'copilot.loading.scenario',
  'copilot.loading.compose',
] as const;

const CATEGORY_ORDER = [
  'What-If',
  'Policy',
  'Enforcement',
  'General AQI',
  'Weather + Pollution',
];

function buildHistoryFromMessages(msgs: ChatMessage[], maxTurns = 6): ConversationTurn[] {
  const turns: ConversationTurn[] = [];
  for (const m of msgs) {
    if (m.role !== 'user' && m.role !== 'assistant') continue;
    if (m.sender?.includes('Error')) continue;
    const content = (m.content || '').trim();
    if (!content) continue;
    turns.push({ role: m.role, content: content.slice(0, 2000) });
  }
  return turns.slice(-maxTurns);
}

export default function CopilotPage() {
  const navigate = useNavigate();
  const { language: sessionLanguage } = useSession();
  const { t } = useT();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const sendMessageMutation = useSendMessage();
  const [inputText, setInputText] = useState('');
  const [openReasoning, setOpenReasoning] = useState<Record<string, boolean>>({});
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<CopilotSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [loadingHintIdx, setLoadingHintIdx] = useState(0);
  const [lastMapActionSummary, setLastMapActionSummary] = useState<string | null>(null);
  const mapCtx = useMapCopilotContext();
  const [sessionId] = useState(() => `sess-${Date.now().toString(36)}`);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const prefetchOnce = useRef(false);
  const submittingRef = useRef(false);

  const modeLabel = useCallback(
    (mode: string) => {
      if (mode === 'tool_agent') return t('copilot.mode.tool_agent');
      if (mode === 'heuristic_fallback') return t('copilot.mode.heuristic_fallback');
      if (mode === 'fast_path') return t('copilot.mode.fast_path');
      return mode.replace(/_/g, ' ');
    },
    [t],
  );

  // Sync URL params into Map context on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    // HashRouter: query may be after hash
    const hash = window.location.hash || '';
    const qIdx = hash.indexOf('?');
    const fromHash = qIdx >= 0 ? new URLSearchParams(hash.slice(qIdx + 1)) : null;
    const sid =
      params.get('station_id') ||
      params.get('stationId') ||
      fromHash?.get('station_id') ||
      fromHash?.get('stationId') ||
      '';
    const h3 =
      params.get('h3_cell') ||
      params.get('h3') ||
      fromHash?.get('h3_cell') ||
      fromHash?.get('h3') ||
      '';
    const label = params.get('label') || fromHash?.get('label') || '';
    if (sid || h3) {
      mapCtx.setMapContext({
        station_id: sid || undefined,
        h3_cell: h3 || null,
        label: label || undefined,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only URL bootstrap
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sendMessageMutation.isPending]);

  useEffect(() => {
    if (!sendMessageMutation.isPending) {
      setLoadingHintIdx(0);
      return;
    }
    const id = window.setInterval(() => {
      setLoadingHintIdx((i) => (i + 1) % LOADING_HINT_KEYS.length);
    }, 2800);
    return () => window.clearInterval(id);
  }, [sendMessageMutation.isPending]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const items = await fetchCopilotSuggestions();
      if (!cancelled) setSuggestions(items);
      if (!prefetchOnce.current) {
        prefetchOnce.current = true;
        void prefetchCopilot();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const activeMapContext = useMemo(
    () => ({
      station_id: mapCtx.station_id,
      h3_cell: mapCtx.h3_cell,
      label: mapCtx.label,
    }),
    [mapCtx.station_id, mapCtx.h3_cell, mapCtx.label],
  );

  const handleSend = useCallback(
    async (e?: React.FormEvent, suggestedText?: string) => {
      if (e) e.preventDefault();
      if (submittingRef.current || sendMessageMutation.isPending) return;
      if (!(suggestedText ?? inputText).trim()) return;

      const text = (suggestedText ?? inputText).trim();
      setInputText('');
      setMutationError(null);
      submittingRef.current = true;

      const history = buildHistoryFromMessages(messages, 6);

      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: text,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        sender: t('common.you'),
      };
      setMessages((prev) => [...prev, userMsg]);

      try {
        const data = await sendMessageMutation.mutateAsync({
          message: text,
          station_id: activeMapContext.station_id,
          h3_cell: activeMapContext.h3_cell,
          conversation_history: history,
          session_id: sessionId,
          language: sessionLanguage,
        });
        const audit = data.audit_trail ?? {};
        const reasoning = buildReasoningSteps(data);
        const { mode, label, fromCache, cacheKind, whatifUsed, memoryTurns } =
          deriveCopilotMode(data);
        const botId = `bot-${Date.now()}`;
        if (reasoning.length > 2) {
          setOpenReasoning((prev) => ({ ...prev, [botId]: false }));
        }

        let content = (data.answer || '').trim();
        const isGeneric = isGenericCopilotRefuse(content);
        if (!content) {
          content = t('copilot.error.empty_body');
          setMutationError(t('copilot.error.empty'));
        } else if (isGeneric) {
          setMutationError(t('copilot.error.limited'));
        }

        if (content.startsWith('{') && content.includes('"request_id"')) {
          content = t('copilot.error.malformed_body');
          setMutationError(t('copilot.error.malformed'));
        }

        const grounding = data.structured_data?.grounding;
        if (grounding && grounding.passed === false) {
          reasoning.push({
            id: 'grounding-fail',
            step: `Grounding check failed (${grounding.reason || 'invented numbers'}); answer may be constrained`,
            completed: false,
            type: 'fallback',
          });
        } else if (grounding && grounding.passed) {
          reasoning.push({
            id: 'grounding-ok',
            step: 'Grounding check passed — numeric claims match tool data',
            completed: true,
            type: 'grounding',
          });
        }

        // Copilot → Map: apply highlight instructions
        const mapActions = data.map_actions || data.structured_data?.map_actions;
        let mapActionCount = 0;
        if (mapActions) {
          mapCtx.applyMapActions(mapActions);
          mapActionCount =
            (mapActions.highlight_h3_cells?.length || 0) +
            (mapActions.highlight_stations?.length || 0);
          if (mapActionCount > 0) {
            const labelFocus =
              mapActions.focus_on?.label ||
              mapActions.focus_on?.h3_cell ||
              mapActions.highlight_h3_cells?.[0] ||
              '';
            setLastMapActionSummary(
              t('copilot.map_updated', {
                count: mapActions.highlight_h3_cells?.length || 0,
              }) + (labelFocus ? ` · ${String(labelFocus).slice(0, 40)}` : ''),
            );
            reasoning.push({
              id: 'map-actions',
              step: `Map highlights: ${(mapActions.highlight_h3_cells || []).length} hex(es), ${(mapActions.highlight_stations || []).length} station(s)`,
              completed: true,
              type: 'map',
            });
          }
        }

        const modeDisplay = modeLabel(String(mode));
        const assistantMsg: ChatMessage = {
          id: botId,
          role: 'assistant',
          content,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          sender: fromCache
            ? cacheKind === 'semantic'
              ? t('copilot.sender.cached_similar')
              : t('copilot.sender.cached')
            : t('copilot.sender.prefix', { label: modeDisplay || label }),
          reasoning,
          meta: {
            knowledgeBaseUsed: Boolean(audit.knowledge_base_used),
            knowledgeBackend: audit.knowledge_backend ?? null,
            llmProvider: audit.llm_provider_used ?? null,
            geminiKeyIndex: audit.gemini_key_index ?? null,
            fallbackUsed: Boolean(data.fallback_used || audit.fallback_used),
            llmMode: data.llm_mode,
            responseMode: mode,
            cacheHit: fromCache,
            cacheKind,
            isGenericRefuse: isGeneric,
            isLimitedResponse: isGeneric,
            whatifUsed,
            memoryTurns,
            mapActionsApplied: mapActionCount > 0,
            mapActionCount,
          },
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err: unknown) {
        const { timedOut, networkError, userMessage } = formatCopilotError(err, sessionLanguage);
        setMutationError(userMessage);
        const errMsg: ChatMessage = {
          id: `bot-err-${Date.now()}`,
          role: 'assistant',
          content: timedOut
            ? t('copilot.error.timeout_chat')
            : networkError
              ? t('copilot.error.network_chat')
              : `⚠ ${userMessage}`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          sender: t('copilot.sender.error'),
          meta: {
            responseMode: 'error',
            isLimitedResponse: true,
          },
        };
        setMessages((prev) => [...prev, errMsg]);
      } finally {
        submittingRef.current = false;
      }
    },
    [
      inputText,
      sendMessageMutation,
      messages,
      activeMapContext,
      sessionId,
      mapCtx,
      sessionLanguage,
      t,
      modeLabel,
    ],
  );

  const onSuggestionClick = (question: string) => {
    if (submittingRef.current || sendMessageMutation.isPending) return;
    setInputText(question);
    void handleSend(undefined, question);
  };

  const toggleReasoning = (msgId: string) => {
    setOpenReasoning((prev) => ({ ...prev, [msgId]: !prev[msgId] }));
  };

  const grouped = CATEGORY_ORDER.map((cat) => ({
    category: cat,
    items: suggestions.filter((s) => s.category === cat),
  })).filter((g) => g.items.length > 0);

  const known = new Set(CATEGORY_ORDER);
  suggestions.forEach((s) => {
    if (!known.has(s.category) && !grouped.some((g) => g.category === s.category)) {
      grouped.push({
        category: s.category,
        items: suggestions.filter((x) => x.category === s.category),
      });
    }
  });

  const showEmptyState = messages.length === 0 && !sendMessageMutation.isPending;
  const isBusy = sendMessageMutation.isPending || submittingRef.current;
  const hasMapCtx = Boolean(activeMapContext.station_id || activeMapContext.h3_cell);

  return (
    <div className="w-full h-full flex flex-col bg-black relative">
      {/* Top banner + Map Context Active chip */}
      <div className="absolute top-0 left-0 w-full z-10 p-3 bg-gradient-to-b from-black to-transparent flex flex-col items-center gap-2 pointer-events-none">
        <span className="text-[10px] uppercase tracking-widest font-mono font-bold text-apple-secondary bg-apple-card px-4 py-1.5 rounded-full border border-apple-border/50 pointer-events-auto">
          {t('copilot.banner')}
        </span>
        {hasMapCtx && (
          <div className="pointer-events-auto flex items-center gap-2 ui-glass ui-glass-floating rounded-full px-3 py-1.5 border border-brand-blue/40 shadow-lg">
            <MapPin size={12} className="text-brand-blue shrink-0" />
            <span className="text-[10px] font-bold uppercase tracking-wider text-brand-blue">
              {t('copilot.map_context_active')}
            </span>
            <span className="text-[10px] text-white/80 font-mono max-w-[160px] truncate normal-case tracking-normal">
              {activeMapContext.label ||
                activeMapContext.station_id ||
                String(activeMapContext.h3_cell || '').slice(0, 12)}
            </span>
            <button
              type="button"
              onClick={() => mapCtx.clearMapContext()}
              className="p-0.5 rounded hover:bg-white/10 text-apple-secondary hover:text-white"
              title={t('common.clear_map_context')}
            >
              <X size={12} />
            </button>
          </div>
        )}
        {lastMapActionSummary && (
          <button
            type="button"
            onClick={() => navigate('/')}
            className="pointer-events-auto flex items-center gap-2 ui-glass ui-glass-floating rounded-full px-3 py-1.5 border border-fuchsia-500/40 shadow-lg hover:border-fuchsia-400/60 transition-colors"
          >
            <Sparkles size={12} className="text-fuchsia-400 shrink-0" />
            <span className="text-[10px] font-bold uppercase tracking-wider text-fuchsia-300">
              {lastMapActionSummary}
            </span>
            <span className="text-[9px] text-white/70 font-mono">{t('common.view_map_arrow')}</span>
          </button>
        )}
      </div>

      {mutationError && (
        <div className="flex justify-center pt-14 px-4">
          <div className="flex items-center gap-3 px-5 py-3 bg-brand-red/10 border border-brand-red/20 rounded-2xl text-sm text-brand-red font-mono max-w-lg text-center">
            <AlertCircle size={16} className="shrink-0" />
            <span>{mutationError}</span>
            <button
              type="button"
              onClick={() => setMutationError(null)}
              className="ml-1 text-[10px] uppercase tracking-wider opacity-70 hover:opacity-100 shrink-0"
            >
              {t('common.dismiss')}
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-16 md:px-8 space-y-6 flex flex-col pb-56">
        {showEmptyState && (
          <div className="flex flex-col items-center justify-center flex-1 min-h-[40vh] gap-6 max-w-3xl mx-auto w-full">
            <div className="text-center space-y-2">
              <div className="w-12 h-12 rounded-2xl bg-brand-blue/10 border border-brand-blue/20 flex items-center justify-center text-brand-blue mx-auto mb-3">
                <Bot size={22} />
              </div>
              <h2 className="text-lg font-semibold text-white tracking-tight">
                {t('copilot.title')}
              </h2>
              <p className="text-sm text-apple-secondary max-w-md">
                {t('copilot.empty_body')}
                {hasMapCtx ? t('copilot.empty_map_active') : t('copilot.empty_map_hint')}
              </p>
            </div>

            {showSuggestions && suggestions.length > 0 && (
              <div className="w-full space-y-4">
                <div className="flex items-center justify-between px-1">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-apple-secondary flex items-center gap-1.5">
                    <Sparkles size={12} className="text-amber-400" />
                    {t('copilot.suggested')}
                  </span>
                  <button
                    type="button"
                    onClick={() => setShowSuggestions(false)}
                    className="text-[10px] font-mono text-apple-secondary hover:text-white flex items-center gap-1 transition-colors"
                  >
                    <EyeOff size={12} /> {t('common.hide')}
                  </button>
                </div>

                {grouped.map((group) => (
                  <div key={group.category} className="space-y-2">
                    <div className="flex items-center gap-1.5 px-1 text-[10px] font-mono uppercase tracking-wider text-apple-secondary/80">
                      {categoryIcon(group.category)}
                      {group.category}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {group.items.map((s) => (
                        <button
                          key={s.id}
                          type="button"
                          onClick={() => onSuggestionClick(s.question)}
                          disabled={isBusy}
                          className="text-left text-xs text-white/90 bg-apple-card/70 hover:bg-apple-modal border border-apple-border/60 hover:border-brand-blue/40 rounded-2xl px-3.5 py-2.5 transition-all max-w-full disabled:opacity-50 shadow-sm"
                        >
                          {s.question}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {!showSuggestions && (
              <button
                type="button"
                onClick={() => setShowSuggestions(true)}
                className="text-[10px] font-mono text-apple-secondary hover:text-white flex items-center gap-1.5 transition-colors"
              >
                <Eye size={12} /> {t('copilot.show_suggested')}
              </button>
            )}
          </div>
        )}

        {messages.map((msg) => {
          const isUser = msg.role === 'user';
          const isReasoningOpen = openReasoning[msg.id];
          const limited = msg.meta?.isLimitedResponse || msg.meta?.isGenericRefuse;
          const mode = msg.meta?.responseMode || '';

          return (
            <div key={msg.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] md:max-w-[70%] flex flex-col ${isUser ? 'items-end' : 'items-start'} gap-1.5`}
              >
                <div className="flex items-end gap-2.5">
                  {!isUser && (
                    <div className="w-8 h-8 rounded-full bg-brand-blue/10 border border-brand-blue/20 flex items-center justify-center text-brand-blue shrink-0 mb-1">
                      <Bot size={15} />
                    </div>
                  )}

                  <div
                    className={`px-5 py-3.5 rounded-[20px] shadow-lg leading-relaxed text-sm ${
                      isUser
                        ? 'bg-apple-card border border-apple-border text-white rounded-tr-[4px]'
                        : limited
                          ? 'bg-orange-950/30 border border-orange-700/30 text-orange-50/95 rounded-tl-[4px]'
                          : 'bg-apple-card/40 border border-apple-border/50 text-white rounded-tl-[4px]'
                    }`}
                  >
                    {limited && !isUser && (
                      <div className="text-[10px] font-mono uppercase tracking-wider text-orange-300/90 mb-2 flex items-center gap-1.5">
                        <AlertCircle size={11} />
                        {t('copilot.limited_response')}
                      </div>
                    )}
                    <div className="whitespace-pre-line space-y-2">{msg.content}</div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-1.5 px-2">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-apple-secondary select-none">
                    {msg.timestamp} · {msg.sender}
                  </span>

                  {!isUser && mode && mode !== 'error' && (
                    <span
                      className={`text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-full border flex items-center gap-1 ${modeBadgeStyle(String(mode))}`}
                    >
                      {modeIcon(String(mode))}
                      {modeLabel(String(mode))}
                    </span>
                  )}

                  {!isUser && msg.meta?.cacheHit && (
                    <span className="text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-full bg-violet-900/40 border border-violet-700/40 text-violet-300 flex items-center gap-1">
                      <Database size={10} />
                      {msg.meta.cacheKind === 'semantic'
                        ? t('copilot.cache_similar')
                        : t('copilot.cache')}
                    </span>
                  )}

                  {!isUser && msg.meta?.whatifUsed && (
                    <span className="text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-full bg-fuchsia-900/40 border border-fuchsia-700/40 text-fuchsia-300 flex items-center gap-1">
                      <FlaskConical size={10} />
                      {t('copilot.whatif')}
                    </span>
                  )}

                  {!isUser && (msg.meta?.memoryTurns ?? 0) > 0 && (
                    <span className="text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-full bg-cyan-900/40 border border-cyan-700/40 text-cyan-300 flex items-center gap-1">
                      <MessageSquare size={10} />
                      {t('copilot.memory', { count: msg.meta?.memoryTurns ?? 0 })}
                    </span>
                  )}

                  {!isUser && msg.meta?.mapActionsApplied && (
                    <button
                      type="button"
                      onClick={() => navigate('/')}
                      className="text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-full bg-fuchsia-900/40 border border-fuchsia-700/40 text-fuchsia-300 flex items-center gap-1 hover:bg-fuchsia-900/60"
                    >
                      <Map size={10} />
                      {t('common.view_on_map')}
                      {(msg.meta.mapActionCount ?? 0) > 0
                        ? ` · ${msg.meta.mapActionCount}`
                        : ''}
                    </button>
                  )}

                  {!isUser && msg.meta?.knowledgeBaseUsed && (
                    <span className="text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-900/40 border border-emerald-700/40 text-emerald-300">
                      KB · {msg.meta.knowledgeBackend || 'rag'}
                    </span>
                  )}
                  {!isUser && msg.meta?.fallbackUsed && mode !== 'heuristic_fallback' && (
                    <span className="text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-full bg-orange-900/40 border border-orange-700/40 text-orange-300">
                      {t('copilot.fallback')}
                    </span>
                  )}
                  {!isUser && msg.meta?.llmProvider && msg.meta.llmProvider !== 'cache' && (
                    <span className="text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-full bg-amber-900/30 border border-amber-700/30 text-amber-300">
                      {msg.meta.llmProvider}
                      {msg.meta.geminiKeyIndex ? ` #${msg.meta.geminiKeyIndex}` : ''}
                    </span>
                  )}
                </div>

                {!isUser && msg.reasoning && msg.reasoning.length > 0 && (
                  <div className="ml-10 w-full max-w-lg mt-1">
                    <div className="bg-apple-card/60 border border-apple-border/50 rounded-2xl overflow-hidden">
                      <button
                        type="button"
                        onClick={() => toggleReasoning(msg.id)}
                        className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-semibold text-apple-secondary hover:text-white transition-colors select-none"
                      >
                        <span className="flex items-center gap-2">
                          {isReasoningOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          {t('copilot.reasoning_trace')}
                        </span>
                        <span className="text-[10px] font-mono text-apple-secondary/60">
                          {t('copilot.steps', { count: msg.reasoning.length })}
                        </span>
                      </button>

                      {isReasoningOpen && (
                        <div className="px-4 pb-3 pt-1 border-t border-apple-border/20 flex flex-col gap-2 font-mono text-[10px] text-apple-secondary leading-normal max-h-72 overflow-y-auto">
                          {msg.reasoning.map((step) => (
                            <div key={step.id} className="flex items-start gap-2">
                              {stepIcon(step.type, step.completed)}
                              <div className="flex flex-col gap-0.5 min-w-0">
                                <span
                                  className={
                                    step.completed === false ? 'text-orange-200' : 'text-white/90'
                                  }
                                >
                                  {step.step}
                                </span>
                                {step.meta && (
                                  <span className="text-apple-secondary/70 break-all">{step.meta}</span>
                                )}
                                {step.type && (
                                  <span className="text-apple-secondary/40 uppercase tracking-wider text-[9px]">
                                    {step.type}
                                  </span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {sendMessageMutation.isPending && (
          <div className="flex justify-start">
            <div className="flex items-end gap-2.5 max-w-[80%]">
              <div className="w-8 h-8 rounded-full bg-brand-blue/10 border border-brand-blue/20 flex items-center justify-center text-brand-blue shrink-0">
                <Loader2 size={15} className="animate-spin" />
              </div>
              <div className="px-5 py-3.5 rounded-2xl rounded-tl-[4px] text-xs font-mono select-none space-y-1.5 bg-apple-card/40 border border-apple-border/50 text-apple-secondary">
                <div className="flex items-center gap-2 font-semibold text-white/80">
                  <Wrench size={12} className="text-indigo-400" />
                  {t('copilot.working')}
                </div>
                <div className="text-apple-secondary/90">
                  {t(LOADING_HINT_KEYS[loadingHintIdx])}
                </div>
                <div className="flex gap-1 pt-0.5">
                  {LOADING_HINT_KEYS.map((_, i) => (
                    <span
                      key={i}
                      className={`h-1 w-4 rounded-full transition-colors ${
                        i === loadingHintIdx ? 'bg-brand-blue' : 'bg-apple-border/60'
                      }`}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Fixed bottom console */}
      <div className="absolute bottom-0 left-0 w-full p-4 md:p-6 bg-gradient-to-t from-black via-black/95 to-transparent pb-8 z-20">
        <div className="max-w-3xl mx-auto flex flex-col gap-3">
          {!showEmptyState && showSuggestions && suggestions.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between px-1">
                <span className="text-[9px] font-bold uppercase tracking-widest text-apple-secondary/80 flex items-center gap-1">
                  <Sparkles size={10} className="text-amber-400" />
                  {t('copilot.try_asking')}
                </span>
                <button
                  type="button"
                  onClick={() => setShowSuggestions(false)}
                  className="text-[9px] font-mono text-apple-secondary/70 hover:text-white transition-colors"
                >
                  {t('common.hide')}
                </button>
              </div>
              <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin">
                {suggestions.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => onSuggestionClick(s.question)}
                    disabled={isBusy}
                    className="shrink-0 text-[11px] text-white/85 bg-apple-card border border-apple-border/50 hover:border-brand-blue/40 rounded-full px-3 py-1.5 hover:bg-apple-modal transition-colors disabled:opacity-50 max-w-[280px] truncate"
                    title={s.question}
                  >
                    {s.question}
                  </button>
                ))}
              </div>
            </div>
          )}

          {!showEmptyState && !showSuggestions && (
            <div className="flex justify-center">
              <button
                type="button"
                onClick={() => setShowSuggestions(true)}
                className="text-[9px] font-mono text-apple-secondary hover:text-white flex items-center gap-1 transition-colors"
              >
                <Eye size={10} /> {t('copilot.show_suggestions')}
              </button>
            </div>
          )}

          {/* Quick actions — no Deep Mode */}
          <div className="flex justify-center gap-3 select-none flex-wrap">
            <button
              type="button"
              disabled={isBusy}
              onClick={() =>
                void handleSend(
                  undefined,
                  'What if construction activity reduces by 50% in this area?',
                )
              }
              className="text-[10px] font-bold uppercase tracking-wider text-apple-secondary bg-apple-card border border-apple-border rounded-full px-4 py-1.5 hover:bg-apple-modal hover:text-white transition-colors flex items-center gap-1.5 disabled:opacity-50"
            >
              <FlaskConical size={11} className="text-fuchsia-400" />
              {t('copilot.quick.whatif')}
            </button>
            <button
              type="button"
              disabled={isBusy}
              onClick={() =>
                void handleSend(
                  undefined,
                  'For Bengaluru, prepare an inspection plan using the current enforcement-priority ranking. Include the top location, evidence limits, and recommended actions.',
                )
              }
              className="text-[10px] font-bold uppercase tracking-wider text-apple-secondary bg-apple-card border border-apple-border rounded-full px-4 py-1.5 hover:bg-apple-modal hover:text-white transition-colors flex items-center gap-1.5 disabled:opacity-50"
            >
              <Shield size={11} className="text-brand-orange" />
              {t('copilot.quick.dispatch')}
            </button>
            <button
              type="button"
              disabled={isBusy}
              onClick={() =>
                void handleSend(
                  undefined,
                  'For Bengaluru, provide a spatial intelligence summary for a map overlay: the highest-priority covered areas, their dominant sources, and the limits of station coverage.',
                )
              }
              className="text-[10px] font-bold uppercase tracking-wider text-apple-secondary bg-apple-card border border-apple-border rounded-full px-4 py-1.5 hover:bg-apple-modal hover:text-white transition-colors flex items-center gap-1.5 disabled:opacity-50"
            >
              <Map size={11} className="text-brand-blue" />
              {t('copilot.quick.map_overlay')}
            </button>
          </div>

          <form
            onSubmit={handleSend}
            className="relative flex items-center ui-glass ui-glass-floating rounded-full shadow-2xl px-2.5 py-1.5 focus-within:border-brand-blue/50 transition-colors duration-200"
          >
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              disabled={isBusy}
              className="flex-1 bg-transparent border-none text-sm text-white placeholder:text-apple-secondary/50 focus:ring-0 px-4 outline-none disabled:opacity-60"
              placeholder={
                isBusy
                  ? t('copilot.placeholder_busy')
                  : hasMapCtx
                    ? t('copilot.placeholder_map')
                    : t('copilot.placeholder')
              }
            />

            <div className="flex items-center gap-1 shrink-0 pr-1 select-none">
              <button
                type="submit"
                disabled={isBusy || !inputText.trim()}
                className="bg-brand-blue hover:bg-brand-blue/90 active:scale-95 disabled:opacity-50 text-white w-10 h-10 min-w-[40px] min-h-[40px] rounded-full transition-all flex items-center justify-center shadow-md shadow-brand-blue/20 shrink-0"
                title={t('common.send')}
              >
                {isBusy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
