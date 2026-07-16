import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useSendMessage, fetchCopilotSuggestions, prefetchCopilot, CopilotSuggestion } from '../services/copilotService';
import { ChatMessage, ReasoningStep } from '../types';
import {
  Bot,
  Send,
  Mic,
  ChevronRight,
  ChevronDown,
  CheckCircle,
  XCircle,
  Shield,
  Map,
  Paperclip,
  AlertCircle,
  BookOpen,
  KeyRound,
  Route,
  Sparkles,
  Scale,
  Wind,
  Eye,
  EyeOff,
} from 'lucide-react';

/** Build a rich reasoning list from audit_trail.reasoning_trace (+ tools fallback). */
function buildReasoningSteps(data: any, deepMode: boolean): ReasoningStep[] {
  const audit = data?.audit_trail ?? {};
  const trace: any[] = Array.isArray(audit.reasoning_trace) ? audit.reasoning_trace : [];
  const steps: ReasoningStep[] = [];

  if (deepMode) {
    steps.push({
      id: 'mode-deep',
      step: 'Deep Reasoning Mode enabled (LangGraph multi-step planner)',
      completed: true,
      type: 'mode',
    });
  }

  if (trace.length > 0) {
    trace.forEach((entry, index) => {
      const type = String(entry.type || 'step');
      let step = String(entry.detail || type);
      if (type === 'tool' && entry.tool) {
        const name = String(entry.tool).replace(/^tool_/, '').replace(/_/g, ' ');
        step = entry.success ? `Tool OK: ${name}` : `Tool failed: ${name}`;
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
  if (type === 'cache') return <Sparkles size={12} className="text-violet-400 shrink-0 mt-0.5" />;
  if (type === 'llm' || type === 'plan') return <KeyRound size={12} className="text-amber-400 shrink-0 mt-0.5" />;
  if (type === 'route' || type === 'agent') return <Route size={12} className="text-sky-400 shrink-0 mt-0.5" />;
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
  if (c.includes('weather')) return <Wind size={12} className="text-sky-400" />;
  return <Sparkles size={12} className="text-brand-blue" />;
}

const CATEGORY_ORDER = ['Policy', 'Enforcement', 'General AQI', 'Weather + Pollution'];

export default function CopilotPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const sendMessageMutation = useSendMessage();
  const [inputText, setInputText] = useState('');
  const [openReasoning, setOpenReasoning] = useState<Record<string, boolean>>({});
  const [deepReasoning, setDeepReasoning] = useState(false);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<CopilotSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const prefetchOnce = useRef(false);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load suggested questions + kick off backend prefetch once on mount
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

  const handleSend = useCallback(
    async (e?: React.FormEvent, suggestedText?: string) => {
      if (e) e.preventDefault();
      if (!(suggestedText ?? inputText).trim()) return;

      const text = suggestedText ?? inputText;
      setInputText('');
      setMutationError(null);

      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: text,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        sender: 'Operative K.',
      };
      setMessages((prev) => [...prev, userMsg]);

      try {
        const data = await sendMessageMutation.mutateAsync({
          message: text,
          force_dynamic_planning: deepReasoning,
        });
        const audit = data.audit_trail ?? {};
        const reasoning = buildReasoningSteps(data, deepReasoning);
        const isDeep =
          deepReasoning ||
          (data.llm_mode === 'hosted' && data.selected_agent === 'dynamic_planning_agent');
        const botId = `bot-${Date.now()}`;
        if (deepReasoning || reasoning.length > 0) {
          setOpenReasoning((prev) => ({ ...prev, [botId]: deepReasoning }));
        }
        const fromCache = (audit.warnings || []).includes('served_from_response_cache')
          || (data.warnings || []).includes('served_from_response_cache');
        const assistantMsg: ChatMessage = {
          id: botId,
          role: 'assistant',
          content: data.answer || data.text || JSON.stringify(data),
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          sender: fromCache
            ? 'Copilot AI · Cached'
            : isDeep
              ? 'Copilot AI · Deep plan'
              : data.fallback_used
                ? 'Copilot AI · Grounded fallback'
                : 'Copilot AI',
          reasoning,
          meta: {
            knowledgeBaseUsed: Boolean(audit.knowledge_base_used),
            knowledgeBackend: audit.knowledge_backend ?? null,
            llmProvider: audit.llm_provider_used ?? null,
            geminiKeyIndex: audit.gemini_key_index ?? null,
            fallbackUsed: Boolean(data.fallback_used || audit.fallback_used),
            llmMode: data.llm_mode,
          },
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err: any) {
        const detail = err?.response?.data?.detail || err?.message || 'Request failed';
        setMutationError(detail);
      }
    },
    [inputText, deepReasoning, sendMessageMutation],
  );

  const onSuggestionClick = (question: string) => {
    // Populate input briefly for visual feedback, then auto-send
    setInputText(question);
    void handleSend(undefined, question);
  };

  const toggleReasoning = (msgId: string) => {
    setOpenReasoning((prev) => ({ ...prev, [msgId]: !prev[msgId] }));
  };

  // Group suggestions by category for display
  const grouped = CATEGORY_ORDER.map((cat) => ({
    category: cat,
    items: suggestions.filter((s) => s.category === cat),
  })).filter((g) => g.items.length > 0);

  // Also show any categories not in the default order
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

  return (
    <div className="w-full h-full flex flex-col bg-black relative">
      {/* Top system notification banner */}
      <div className="absolute top-0 left-0 w-full z-10 p-3 bg-gradient-to-b from-black to-transparent flex justify-center pointer-events-none">
        <span className="text-[10px] uppercase tracking-widest font-mono font-bold text-apple-secondary bg-apple-card px-4 py-1.5 rounded-full border border-apple-border/50">
          SYSTEM INITIALIZED: COPILOT ALPHA
        </span>
      </div>

      {mutationError && (
        <div className="flex justify-center pt-14 px-4">
          <div className="flex items-center gap-3 px-5 py-3 bg-brand-red/10 border border-brand-red/20 rounded-2xl text-sm text-brand-red font-mono max-w-md text-center">
            <AlertCircle size={16} />
            {deepReasoning
              ? `Deep Reasoning failed: ${mutationError}`
              : `Request failed: ${mutationError}`}
          </div>
        </div>
      )}

      {/* Main message feed */}
      <div className="flex-1 overflow-y-auto px-4 py-16 md:px-8 space-y-6 flex flex-col pb-56">
        {/* Empty-state hero with suggested questions */}
        {showEmptyState && (
          <div className="flex flex-col items-center justify-center flex-1 min-h-[40vh] gap-6 max-w-3xl mx-auto w-full">
            <div className="text-center space-y-2">
              <div className="w-12 h-12 rounded-2xl bg-brand-blue/10 border border-brand-blue/20 flex items-center justify-center text-brand-blue mx-auto mb-3">
                <Bot size={22} />
              </div>
              <h2 className="text-lg font-semibold text-white tracking-tight">
                AQI Sentinel Copilot
              </h2>
              <p className="text-sm text-apple-secondary max-w-md">
                Ask about policy, enforcement priorities, neighbourhood air quality, or weather-linked pollution.
                Answers are grounded in live data and the local knowledge base.
              </p>
            </div>

            {showSuggestions && suggestions.length > 0 && (
              <div className="w-full space-y-4">
                <div className="flex items-center justify-between px-1">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-apple-secondary flex items-center gap-1.5">
                    <Sparkles size={12} className="text-amber-400" />
                    Suggested questions
                  </span>
                  <button
                    type="button"
                    onClick={() => setShowSuggestions(false)}
                    className="text-[10px] font-mono text-apple-secondary hover:text-white flex items-center gap-1 transition-colors"
                  >
                    <EyeOff size={12} /> Hide
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
                          disabled={sendMessageMutation.isPending}
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
                <Eye size={12} /> Show suggested questions
              </button>
            )}
          </div>
        )}

        {messages.map((msg) => {
          const isUser = msg.role === 'user';
          const isReasoningOpen = openReasoning[msg.id];

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
                        : 'bg-apple-card/40 border border-apple-border/50 text-white rounded-tl-[4px]'
                    }`}
                  >
                    <div className="whitespace-pre-line space-y-2">{msg.content}</div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-1.5 px-2">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-apple-secondary select-none">
                    {msg.timestamp} · {msg.sender}
                  </span>
                  {!isUser && msg.meta?.knowledgeBaseUsed && (
                    <span className="text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-900/40 border border-emerald-700/40 text-emerald-300">
                      KB · {msg.meta.knowledgeBackend || 'rag'}
                    </span>
                  )}
                  {!isUser && msg.meta?.fallbackUsed && (
                    <span className="text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-full bg-orange-900/40 border border-orange-700/40 text-orange-300">
                      Fallback
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
                          {msg.meta?.llmMode === 'hosted' && msg.sender?.includes('Deep')
                            ? 'Show deep reasoning trace'
                            : 'Show operational trace'}
                        </span>
                        <span className="text-[10px] font-mono text-apple-secondary/60">
                          {msg.reasoning.length} STEPS
                        </span>
                      </button>

                      {isReasoningOpen && (
                        <div className="px-4 pb-3 pt-1 border-t border-apple-border/20 flex flex-col gap-2 font-mono text-[10px] text-apple-secondary leading-normal max-h-64 overflow-y-auto">
                          {msg.reasoning.map((step) => (
                            <div key={step.id} className="flex items-start gap-2">
                              {stepIcon(step.type, step.completed)}
                              <div className="flex flex-col gap-0.5">
                                <span className={step.completed === false ? 'text-orange-200' : 'text-white'}>
                                  {step.step}
                                </span>
                                {step.meta && (
                                  <span className="text-apple-secondary/70">{step.meta}</span>
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
            <div className="flex items-end gap-2.5 max-w-[70%]">
              <div className="w-8 h-8 rounded-full bg-brand-blue/10 border border-brand-blue/20 flex items-center justify-center text-brand-blue animate-spin">
                <Bot size={15} />
              </div>
              <div
                className={`px-5 py-3.5 rounded-2xl rounded-tl-[4px] text-xs font-mono select-none ${
                  deepReasoning
                    ? 'bg-amber-900/20 border border-amber-600/30 text-amber-400'
                    : 'bg-apple-card/40 border border-apple-border/50 text-apple-secondary'
                }`}
              >
                {deepReasoning
                  ? 'Gathering data... → Analyzing sources... → Composing answer...'
                  : 'Copilot is compiling telemetry logs...'}
              </div>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Fixed bottom console */}
      <div className="absolute bottom-0 left-0 w-full p-4 md:p-6 bg-gradient-to-t from-black via-black/95 to-transparent pb-8 z-20">
        <div className="max-w-3xl mx-auto flex flex-col gap-3">
          {/* Compact suggestions strip when chat already has messages */}
          {!showEmptyState && showSuggestions && suggestions.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between px-1">
                <span className="text-[9px] font-bold uppercase tracking-widest text-apple-secondary/80 flex items-center gap-1">
                  <Sparkles size={10} className="text-amber-400" />
                  Try asking
                </span>
                <button
                  type="button"
                  onClick={() => setShowSuggestions(false)}
                  className="text-[9px] font-mono text-apple-secondary/70 hover:text-white transition-colors"
                >
                  Hide
                </button>
              </div>
              <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin">
                {suggestions.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => onSuggestionClick(s.question)}
                    disabled={sendMessageMutation.isPending}
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
                <Eye size={10} /> Show suggestions
              </button>
            </div>
          )}

          {/* Deep Reasoning Mode Toggle */}
          <div className="flex justify-center items-center gap-2 select-none">
            <label className="flex items-center gap-2 cursor-pointer">
              <button
                type="button"
                role="switch"
                aria-checked={deepReasoning}
                onClick={() => setDeepReasoning(!deepReasoning)}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors duration-200 ${
                  deepReasoning ? 'bg-amber-600' : 'bg-apple-border/50'
                }`}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform duration-200 ${
                    deepReasoning ? 'translate-x-[18px]' : 'translate-x-[3px]'
                  }`}
                />
              </button>
              <span
                className={`text-[10px] font-bold uppercase tracking-wider ${
                  deepReasoning ? 'text-amber-400' : 'text-apple-secondary'
                }`}
              >
                Deep Reasoning Mode
              </span>
            </label>
            {deepReasoning && (
              <span className="text-[9px] text-amber-500/70 font-mono tracking-tight">
                Uses multi-step AI planning — slower, more thorough
              </span>
            )}
          </div>

          {/* Quick action pills */}
          <div className="flex justify-center gap-3 select-none">
            <button
              type="button"
              onClick={() =>
                void handleSend(
                  undefined,
                  'For Bengaluru, prepare an inspection plan using the current enforcement-priority ranking. Include the top location, evidence limits, and recommended actions.',
                )
              }
              className="text-[10px] font-bold uppercase tracking-wider text-apple-secondary bg-apple-card border border-apple-border rounded-full px-4 py-1.5 hover:bg-apple-modal hover:text-white transition-colors flex items-center gap-1.5"
            >
              <Shield size={11} className="text-brand-orange" />
              Draft Dispatch
            </button>
            <button
              type="button"
              onClick={() =>
                void handleSend(
                  undefined,
                  'For Bengaluru, provide a spatial intelligence summary for a map overlay: the highest-priority covered areas, their dominant sources, and the limits of station coverage.',
                )
              }
              className="text-[10px] font-bold uppercase tracking-wider text-apple-secondary bg-apple-card border border-apple-border rounded-full px-4 py-1.5 hover:bg-apple-modal hover:text-white transition-colors flex items-center gap-1.5"
            >
              <Map size={11} className="text-brand-blue" />
              Map Overlay
            </button>
          </div>

          <form
            onSubmit={handleSend}
            className="relative flex items-center ui-glass ui-glass-floating rounded-full shadow-2xl px-2.5 py-1.5 focus-within:border-brand-blue/50 transition-colors duration-200"
          >
            <button
              type="button"
              onClick={() => alert('Attachments console: Only CSV or GEOJSON arrays allowed in preview.')}
              className="p-2 text-apple-secondary hover:text-white transition-colors rounded-full hover:bg-apple-modal shrink-0"
              title="Add attachment"
            >
              <Paperclip size={16} />
            </button>

            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              className="flex-1 bg-transparent border-none text-sm text-white placeholder:text-apple-secondary/50 focus:ring-0 px-3 outline-none"
              placeholder="Ask why an area is polluted, request reports, or issue commands..."
            />

            <div className="flex items-center gap-1 shrink-0 pr-1 select-none">
              <button
                type="button"
                onClick={() => alert('Voice protocol activated. Listening...')}
                className="p-2 text-apple-secondary hover:text-white transition-colors rounded-full hover:bg-apple-modal hidden sm:flex"
                title="Voice dictation"
              >
                <Mic size={16} />
              </button>

              <button
                type="submit"
                className="bg-brand-blue hover:bg-brand-blue/90 active:scale-95 text-white w-10 h-10 min-w-[40px] min-h-[40px] rounded-full transition-all flex items-center justify-center shadow-md shadow-brand-blue/20 shrink-0"
                title="Transmit"
              >
                <Send size={14} />
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
