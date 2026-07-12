import React, { useState, useRef, useEffect } from 'react';
import { useSendMessage } from '../api/client';
import { ChatMessage } from '../types';
import { Bot, User, Send, Plus, Mic, ChevronRight, ChevronDown, CheckCircle, Factory, Shield, Map, Paperclip, AlertCircle } from 'lucide-react';

export default function CopilotPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const sendMessageMutation = useSendMessage();
  const [inputText, setInputText] = useState('');
  const [openReasoning, setOpenReasoning] = useState<Record<string, boolean>>({});
  const [deepReasoning, setDeepReasoning] = useState(false);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputText.trim()) return;

    const text = inputText;
    setInputText('');
    setMutationError(null);

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      sender: 'Operative K.',
    };
    setMessages(prev => [...prev, userMsg]);

    try {
      const data = await sendMessageMutation.mutateAsync({ message: text, force_dynamic_planning: deepReasoning });
      const assistantMsg: ChatMessage = {
        id: `bot-${Date.now()}`,
        role: 'assistant',
        content: data.answer || data.text || JSON.stringify(data),
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        sender: 'Copilot AI',
        reasoning: data.tool_steps || data.reasoning_steps,
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Request failed';
      setMutationError(detail);
    }
  };

  const handleSuggestedAction = (action: string) => {
    setInputText(action);
  };

  const toggleReasoning = (msgId: string) => {
    setOpenReasoning(prev => ({ ...prev, [msgId]: !prev[msgId] }));
  };

  return (
    <div className="w-full h-full flex flex-col bg-black relative">
      {/* Top system notification banner */}
      <div className="absolute top-0 left-0 w-full z-10 p-3 bg-gradient-to-b from-black to-transparent flex justify-center pointer-events-none">
        <span className="text-[10px] uppercase tracking-widest font-mono font-bold text-apple-secondary bg-apple-card px-4 py-1.5 rounded-full border border-apple-border/50">
          SYSTEM INITIALIZED: COPILOT ALPHA
        </span>
      </div>

      {mutationError && (
        <div className="flex justify-center">
          <div className="flex items-center gap-3 px-5 py-3 bg-brand-red/10 border border-brand-red/20 rounded-2xl text-sm text-brand-red font-mono max-w-md text-center">
            <AlertCircle size={16} />
            {deepReasoning
              ? `Deep Reasoning failed: ${mutationError}`
              : `Request failed: ${mutationError}`}
          </div>
        </div>
      )}

      {/* Main message feed */}
      <div className="flex-1 overflow-y-auto px-4 py-16 md:px-8 space-y-6 flex flex-col pb-44">
        {messages.map((msg) => {
          const isUser = msg.role === 'user';
          const isReasoningOpen = openReasoning[msg.id];

          return (
            <div key={msg.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] md:max-w-[70%] flex flex-col ${isUser ? 'items-end' : 'items-start'} gap-1.5`}>
                
                {/* Bubble card */}
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
                    {/* Render message formatting */}
                    <div className="whitespace-pre-line space-y-2">
                      {msg.content}
                    </div>
                  </div>
                </div>

                {/* Subtext info */}
                <span className="text-[10px] font-mono uppercase tracking-wider text-apple-secondary px-2 select-none">
                  {msg.timestamp} · {msg.sender}
                </span>

                {/* Optional Expandable Tool Reasoning log */}
                {!isUser && msg.reasoning && (
                  <div className="ml-10 w-full max-w-md mt-1">
                    <div className="bg-apple-card/60 border border-apple-border/50 rounded-2xl overflow-hidden">
                      <button
                        type="button"
                        onClick={() => toggleReasoning(msg.id)}
                        className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-semibold text-apple-secondary hover:text-white transition-colors select-none"
                      >
                        <span className="flex items-center gap-2">
                          {isReasoningOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          Show operational trace
                        </span>
                        <span className="text-[10px] font-mono text-apple-secondary/60">
                          {msg.reasoning.length} STEPS
                        </span>
                      </button>

                      {isReasoningOpen && (
                        <div className="px-4 pb-3 pt-1 border-t border-apple-border/20 flex flex-col gap-2 font-mono text-[10px] text-apple-secondary leading-normal">
                          {msg.reasoning.map((step) => (
                            <div key={step.id} className="flex items-start gap-2">
                              <CheckCircle size={12} className="text-brand-green shrink-0 mt-0.5" />
                              <span className="text-white">{step.step}</span>
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

        {/* Loading trigger state */}
        {sendMessageMutation.isPending && (
          <div className="flex justify-start">
            <div className="flex items-end gap-2.5 max-w-[70%]">
              <div className="w-8 h-8 rounded-full bg-brand-blue/10 border border-brand-blue/20 flex items-center justify-center text-brand-blue animate-spin">
                <Bot size={15} />
              </div>
              <div className={`px-5 py-3.5 rounded-2xl rounded-tl-[4px] text-xs font-mono select-none ${
                deepReasoning
                  ? 'bg-amber-900/20 border border-amber-600/30 text-amber-400'
                  : 'bg-apple-card/40 border border-apple-border/50 text-apple-secondary'
              }`}>
                {deepReasoning
                  ? 'Gathering data... → Analyzing sources... → Composing answer...'
                  : 'Copilot is compiling telemetry logs...'}
              </div>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Fixed bottom typing console container */}
      <div className="absolute bottom-0 left-0 w-full p-4 md:p-6 bg-gradient-to-t from-black via-black/95 to-transparent pb-8 z-20">
        <div className="max-w-3xl mx-auto flex flex-col gap-4">
          
          {/* Deep Reasoning Mode Toggle */}
          <div className="flex justify-center items-center gap-2 select-none mb-1">
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
                <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform duration-200 ${
                  deepReasoning ? 'translate-x-[18px]' : 'translate-x-[3px]'
                }`} />
              </button>
              <span className={`text-[10px] font-bold uppercase tracking-wider ${
                deepReasoning ? 'text-amber-400' : 'text-apple-secondary'
              }`}>
                Deep Reasoning Mode
              </span>
            </label>
            {deepReasoning && (
              <span className="text-[9px] text-amber-500/70 font-mono tracking-tight">
                Uses multi-step AI planning — slower, more thorough
              </span>
            )}
          </div>

          {/* Quick interactive pills suggestions */}
          <div className="flex justify-center gap-3 select-none">
            <button
              onClick={() => handleSuggestedAction('Draft Dispatch to Sector 44')}
              className="text-[10px] font-bold uppercase tracking-wider text-apple-secondary bg-apple-card border border-apple-border rounded-full px-4 py-1.5 hover:bg-apple-modal hover:text-white transition-colors flex items-center gap-1.5"
            >
              <Shield size={11} className="text-brand-orange" />
              Draft Dispatch
            </button>
            <button
              onClick={() => handleSuggestedAction('Expose active plume overlay on main map')}
              className="text-[10px] font-bold uppercase tracking-wider text-apple-secondary bg-apple-card border border-apple-border rounded-full px-4 py-1.5 hover:bg-apple-modal hover:text-white transition-colors flex items-center gap-1.5"
            >
              <Map size={11} className="text-brand-blue" />
              Map Overlay
            </button>
          </div>

          {/* Actual Pill Input Field Form Console */}
          <form onSubmit={handleSend} className="relative flex items-center bg-apple-card rounded-full shadow-2xl px-2.5 py-1.5 border border-apple-border focus-within:border-brand-blue/60 transition-all duration-300">
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
                className="bg-brand-blue hover:bg-blue-600 text-white w-9 h-9 rounded-full transition-colors flex items-center justify-center shadow-md shadow-brand-blue/10 shrink-0"
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
