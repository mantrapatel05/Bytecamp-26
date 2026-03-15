import { motion, AnimatePresence } from 'framer-motion';
import { useState, useRef, useEffect, useCallback } from 'react';
import { useApp } from '@/context/AppContext';
import { useAuth } from '@/context/AuthContext';
import apiClient, { ChatSession, ChatMessage } from '@/api/client';

// ── Simple markdown renderer ─────────────────────────────────────────────────
function MarkdownText({ text }: { text: string }) {
  const lines = text.split('\n');
  const output: React.ReactNode[] = [];
  let codeBuffer: string[] = [];
  let inCode = false;
  let key = 0;

  const flush = () => {
    if (codeBuffer.length) {
      output.push(
        <pre key={key++} className="my-2 p-3 rounded-lg overflow-x-auto text-[11px] leading-relaxed" style={{
          background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.07)', fontFamily: 'monospace'
        }}>
          <code style={{ color: '#7dd3fc' }}>{codeBuffer.join('\n')}</code>
        </pre>
      );
      codeBuffer = [];
    }
  };

  const renderInline = (s: string): React.ReactNode => {
    const parts = s.split(/(`[^`]+`)/g);
    return parts.map((p, i) => {
      if (p.startsWith('`') && p.endsWith('`') && p.length > 2) {
        return <code key={i} className="px-1 py-0.5 rounded text-[11px]" style={{
          background: 'rgba(0,229,184,0.08)', color: 'var(--teal-hex)', fontFamily: 'monospace'
        }}>{p.slice(1, -1)}</code>;
      }
      const boldParts = p.split(/(\*\*[^*]+\*\*)/g);
      return boldParts.map((bp, j) => {
        if (bp.startsWith('**') && bp.endsWith('**')) {
          return <strong key={`${i}-${j}`} style={{ color: 'var(--text-1-hex)' }}>{bp.slice(2, -2)}</strong>;
        }
        return <span key={`${i}-${j}`}>{bp}</span>;
      });
    });
  };

  for (const line of lines) {
    const fence = line.match(/^```(\w*)/);
    if (fence && !inCode) { inCode = true; continue; }
    if (line.startsWith('```') && inCode) { inCode = false; flush(); continue; }
    if (inCode) { codeBuffer.push(line); continue; }

    const h3 = line.match(/^### (.+)/);
    const h2 = line.match(/^## (.+)/);
    const h1 = line.match(/^# (.+)/);
    if (h1) { output.push(<p key={key++} className="font-syne font-bold text-[13px] mt-3 mb-1" style={{ color: 'var(--teal-hex)' }}>{renderInline(h1[1])}</p>); continue; }
    if (h2) { output.push(<p key={key++} className="font-syne font-semibold text-[12px] mt-3 mb-1" style={{ color: 'var(--teal-hex)' }}>{renderInline(h2[1])}</p>); continue; }
    if (h3) { output.push(<p key={key++} className="font-syne font-medium text-[11px] mt-2 mb-0.5" style={{ color: 'var(--text-2-hex)' }}>{renderInline(h3[1])}</p>); continue; }

    const bullet = line.match(/^[\-\*\•]\s+(.+)/);
    const numbered = line.match(/^\d+\.\s+(.+)/);
    if (bullet) {
      output.push(<div key={key++} className="flex gap-2 my-0.5"><span style={{ color: 'var(--teal-hex)', flexShrink: 0 }}>•</span><span className="text-[12px] leading-relaxed" style={{ color: 'var(--text-2-hex)' }}>{renderInline(bullet[1])}</span></div>);
      continue;
    }
    if (numbered) {
      const num = line.match(/^(\d+)/)?.[1];
      output.push(<div key={key++} className="flex gap-2 my-0.5"><span className="font-mono text-[11px]" style={{ color: 'var(--teal-hex)', flexShrink: 0, minWidth: 16 }}>{num}.</span><span className="text-[12px] leading-relaxed" style={{ color: 'var(--text-2-hex)' }}>{renderInline(numbered[1])}</span></div>);
      continue;
    }
    if (line.match(/^---+$/)) { output.push(<hr key={key++} className="my-2 border-0 h-px" style={{ background: 'var(--border-1-hex)' }} />); continue; }
    if (!line.trim()) { output.push(<div key={key++} className="h-1" />); continue; }
    output.push(<p key={key++} className="text-[12px] leading-relaxed" style={{ color: 'var(--text-2-hex)' }}>{renderInline(line)}</p>);
  }
  flush();
  return <div className="space-y-0.5">{output}</div>;
}

// ── Types ─────────────────────────────────────────────────────────────────────
interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  isError?: boolean;
}

function getSuggestions(selectedNode: string | null): string[] {
  if (selectedNode) {
    const name = selectedNode.split('::').pop() ?? selectedNode;
    return [`What does \`${name}\` do?`, `What breaks if \`${name}\` is renamed?`, `Trace the data flow from \`${name}\``];
  }
  return [
    'What are the main data flows in this codebase?',
    'Which fields have the highest break risk?',
    'How does data travel from the database to the frontend?',
  ];
}

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
}

// ── History panel ─────────────────────────────────────────────────────────────
function HistoryPanel({
  sessions,
  onLoad,
  onDelete,
  onNew,
  onClose,
}: {
  sessions: ChatSession[];
  onLoad: (s: ChatSession) => void;
  onDelete: (id: string) => void;
  onNew: () => void;
  onClose: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ duration: 0.18 }}
      className="absolute inset-0 z-20 flex flex-col"
      style={{ background: 'var(--void-hex)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b shrink-0" style={{ borderColor: 'var(--border-1-hex)' }}>
        <span className="font-syne font-semibold text-[12px]" style={{ color: 'var(--text-1-hex)' }}>Chat History</span>
        <div className="flex items-center gap-2">
          <button
            onClick={onNew}
            className="font-mono text-[10px] px-2.5 py-1 rounded-full border transition-all"
            style={{ borderColor: 'var(--teal-hex)', color: 'var(--teal-hex)', background: 'rgba(0,229,184,0.06)' }}
          >
            + New chat
          </button>
          <button
            onClick={onClose}
            className="font-mono text-[11px] w-6 h-6 flex items-center justify-center rounded"
            style={{ color: 'var(--text-3-hex)', background: 'var(--surface-hex)' }}
          >
            ✕
          </button>
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1">
        {sessions.length === 0 && (
          <p className="font-mono text-[11px] text-center mt-8" style={{ color: 'var(--text-4-hex)' }}>
            No saved chats yet
          </p>
        )}
        {sessions.map(s => (
          <div
            key={s.id}
            className="group flex items-start gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition-all"
            style={{ background: 'var(--surface-hex)', border: '1px solid var(--border-1-hex)' }}
            onMouseEnter={e => (e.currentTarget.style.borderColor = 'rgba(0,229,184,0.3)')}
            onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border-1-hex)')}
            onClick={() => onLoad(s)}
          >
            <div className="flex-1 min-w-0">
              <p className="font-mono text-[11px] truncate" style={{ color: 'var(--text-2-hex)' }}>{s.title}</p>
              <p className="font-mono text-[9px] mt-0.5" style={{ color: 'var(--text-4-hex)' }}>{formatDate(s.updated_at)}</p>
            </div>
            <button
              onClick={e => { e.stopPropagation(); onDelete(s.id); }}
              className="opacity-0 group-hover:opacity-100 font-mono text-[10px] px-1.5 py-0.5 rounded transition-all shrink-0"
              style={{ color: '#ff5733', background: 'rgba(255,87,51,0.1)' }}
            >
              del
            </button>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
const GREETING: Message = {
  role: 'assistant',
  content: 'I have indexed the repository knowledge graph. Ask me anything about the codebase — data flows, dependencies, break risks, or how a specific symbol is used across languages.',
  timestamp: new Date().toLocaleTimeString(),
};

const ChatTab = () => {
  const { selectedNode } = useApp();
  const { username } = useAuth();
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([GREETING]);
  const [loading, setLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionsLoaded, setSessionsLoaded] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, loading]);

  const loadSessions = useCallback(async () => {
    try {
      const res = await apiClient.getChatSessions();
      setSessions(res.sessions);
      setSessionsLoaded(true);
    } catch { /* silently ignore */ }
  }, []);

  const handleShowHistory = async () => {
    if (!sessionsLoaded) await loadSessions();
    setShowHistory(true);
  };

  const handleNewChat = () => {
    setMessages([GREETING]);
    setActiveSessionId(null);
    setShowHistory(false);
    inputRef.current?.focus();
  };

  const handleLoadSession = async (session: ChatSession) => {
    try {
      const res = await apiClient.getChatSessionMessages(session.id);
      const loaded: Message[] = res.messages.map(m => ({
        role: m.role,
        content: m.content,
        timestamp: formatDate(m.timestamp),
      }));
      setMessages([GREETING, ...loaded]);
      setActiveSessionId(session.id);
      setShowHistory(false);
    } catch { /* silently ignore */ }
  };

  const handleDeleteSession = async (id: string) => {
    try {
      await apiClient.deleteChatSession(id);
      setSessions(prev => prev.filter(s => s.id !== id));
      if (activeSessionId === id) {
        setMessages([GREETING]);
        setActiveSessionId(null);
      }
    } catch { /* silently ignore */ }
  };

  const handleSend = useCallback(async () => {
    if (!input.trim() || loading) return;

    const query = input.trim();
    const userMsg: Message = { role: 'user', content: query, timestamp: new Date().toLocaleTimeString() };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput('');
    setLoading(true);

    // Create session on first real message
    let sessionId = activeSessionId;
    if (!sessionId) {
      try {
        const session = await apiClient.createChatSession();
        sessionId = session.id;
        setActiveSessionId(sessionId);
      } catch { /* continue without session */ }
    }

    // Build history (skip the greeting)
    const history = next.slice(1).map(m => ({ role: m.role, content: m.content }));

    try {
      const response = await apiClient.chat(query, selectedNode ?? undefined, history, sessionId ?? undefined);
      const aiMsg: Message = {
        role: 'assistant',
        content: response.answer,
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages(prev => [...prev, aiMsg]);
      // Refresh sessions list to show updated title
      if (sessionId) loadSessions();
    } catch (err: any) {
      const errText = err.code === 'ECONNABORTED'
        ? 'Request timed out. The LLM may be slow — try again.'
        : err.response?.data?.detail || err.message || 'Failed to get response';
      setMessages(prev => [...prev, {
        role: 'assistant', content: `Error: ${errText}`,
        timestamp: new Date().toLocaleTimeString(), isError: true,
      }]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, messages, selectedNode, activeSessionId, loadSessions]);

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const suggestions = getSuggestions(selectedNode);
  const showSuggestions = !loading && messages.length <= 2;

  return (
    <div className="flex flex-col h-full relative" style={{ background: 'var(--void-hex)' }}>

      {/* History overlay */}
      <AnimatePresence>
        {showHistory && (
          <HistoryPanel
            sessions={sessions}
            onLoad={handleLoadSession}
            onDelete={handleDeleteSession}
            onNew={handleNewChat}
            onClose={() => setShowHistory(false)}
          />
        )}
      </AnimatePresence>

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 shrink-0 border-b" style={{ borderColor: 'var(--border-1-hex)' }}>
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--teal-hex)' }} />
          <span className="font-mono text-[11px]" style={{ color: 'var(--text-3-hex)' }}>Graph RAG</span>
          {activeSessionId && (
            <span className="font-mono text-[9px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(0,229,184,0.06)', color: 'var(--teal-hex)' }}>
              saved
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {selectedNode && (
            <span className="font-mono text-[10px] px-2 py-0.5 rounded-full truncate max-w-[120px]" style={{
              background: 'rgba(0,229,184,0.07)', color: 'var(--teal-hex)', border: '1px solid rgba(0,229,184,0.2)'
            }}>
              {selectedNode.split('::').pop()}
            </span>
          )}
          <button
            onClick={handleShowHistory}
            className="font-mono text-[10px] px-2 py-0.5 rounded border transition-all"
            style={{ borderColor: 'var(--border-1-hex)', color: 'var(--text-3-hex)', background: 'var(--surface-hex)' }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,229,184,0.4)'; (e.currentTarget as HTMLElement).style.color = 'var(--teal-hex)'; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-1-hex)'; (e.currentTarget as HTMLElement).style.color = 'var(--text-3-hex)'; }}
          >
            History
          </button>
          <button
            onClick={handleNewChat}
            className="font-mono text-[10px] px-2 py-0.5 rounded border transition-all"
            style={{ borderColor: 'var(--border-1-hex)', color: 'var(--text-3-hex)', background: 'var(--surface-hex)' }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,229,184,0.4)'; (e.currentTarget as HTMLElement).style.color = 'var(--teal-hex)'; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-1-hex)'; (e.currentTarget as HTMLElement).style.color = 'var(--text-3-hex)'; }}
          >
            + New
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar" ref={scrollRef}>
        <AnimatePresence initial={false}>
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
            >
              {msg.role === 'assistant' && (
                <div className="flex items-center gap-1.5 mb-1.5">
                  <div className="w-4 h-4 rounded-sm flex items-center justify-center" style={{ background: 'var(--teal-hex)' }}>
                    <span className="text-[8px] font-bold" style={{ color: 'var(--void-hex)' }}>AI</span>
                  </div>
                  <span className="font-syne font-semibold text-[11px]" style={{ color: 'var(--teal-hex)' }}>DepGraph.ai</span>
                </div>
              )}
              <div
                className={`px-3.5 py-2.5 rounded-xl max-w-[96%] ${msg.role === 'user' ? 'rounded-br-sm' : 'rounded-tl-sm'}`}
                style={{
                  background: msg.role === 'user' ? 'var(--raised-hex)' : 'var(--surface-hex)',
                  border: `1px solid ${msg.isError ? 'rgba(255,87,51,0.3)' : 'var(--border-2-hex)'}`,
                }}
              >
                {msg.role === 'user'
                  ? <span className="font-mono text-[13px] leading-relaxed" style={{ color: 'var(--text-1-hex)' }}>{msg.content}</span>
                  : <MarkdownText text={msg.content} />}
              </div>
              <span className="font-mono text-[9px] mt-1" style={{ color: 'var(--text-4-hex)' }}>{msg.timestamp}</span>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Thinking indicator */}
        {loading && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-start">
            <div className="flex items-center gap-1.5 mb-1.5">
              <div className="w-4 h-4 rounded-sm flex items-center justify-center" style={{ background: 'var(--teal-hex)' }}>
                <span className="text-[8px] font-bold" style={{ color: 'var(--void-hex)' }}>AI</span>
              </div>
              <span className="font-syne font-semibold text-[11px]" style={{ color: 'var(--teal-hex)' }}>Searching graph...</span>
            </div>
            <div className="px-4 py-3 rounded-xl rounded-tl-sm" style={{ background: 'var(--surface-hex)', border: '1px solid var(--border-2-hex)' }}>
              <div className="flex gap-1.5 items-center">
                {[0, 1, 2].map(d => (
                  <motion.div key={d} animate={{ y: [0, -4, 0] }} transition={{ duration: 0.7, repeat: Infinity, delay: d * 0.15 }}
                    className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--teal-hex)' }} />
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </div>

      {/* Suggestions */}
      <AnimatePresence>
        {showSuggestions && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            className="px-4 pb-2 flex flex-wrap gap-1.5">
            {suggestions.map(s => (
              <button key={s}
                className="font-mono text-[10px] px-2.5 py-1 rounded-full cursor-pointer transition-all"
                style={{ background: 'var(--surface-hex)', border: '1px solid var(--border-1-hex)', color: 'var(--text-3-hex)' }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,229,184,0.4)'; (e.currentTarget as HTMLElement).style.color = 'var(--teal-hex)'; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-1-hex)'; (e.currentTarget as HTMLElement).style.color = 'var(--text-3-hex)'; }}
                onClick={() => setInput(s)}
              >
                {s}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input */}
      <div className="border-t p-3 shrink-0" style={{ borderColor: 'var(--border-1-hex)', background: 'var(--base-hex)' }}>
        <div className="flex items-end gap-2 px-3.5 py-2 rounded-lg border transition-all duration-150"
          style={{ background: 'var(--surface-hex)', borderColor: 'var(--border-2-hex)' }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder={selectedNode
              ? `Ask about ${selectedNode.split('::').pop()}... (Enter to send)`
              : 'Ask about this codebase... (Enter to send)'}
            rows={1}
            className="flex-1 bg-transparent outline-none font-mono text-[13px] resize-none leading-relaxed"
            style={{ color: 'var(--text-1-hex)', maxHeight: 120, overflow: 'auto' }}
            onInput={e => {
              const el = e.currentTarget;
              el.style.height = 'auto';
              el.style.height = Math.min(el.scrollHeight, 120) + 'px';
            }}
          />
          <motion.button
            whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="w-8 h-8 shrink-0 flex items-center justify-center rounded-md text-[14px] cursor-pointer mb-0.5"
            style={{
              background: input.trim() && !loading ? 'var(--teal-hex)' : 'var(--border-1-hex)',
              color: 'var(--void-hex)',
              opacity: input.trim() && !loading ? 1 : 0.45,
              transition: 'background 0.15s',
            }}
          >
            ↗
          </motion.button>
        </div>
        <p className="font-mono text-[9px] mt-1.5 pl-1" style={{ color: 'var(--text-4-hex)' }}>
          Shift+Enter for newline · {username && <span>{username} · </span>}context: {selectedNode ? selectedNode.split('::').pop() : 'full graph'}
        </p>
      </div>
    </div>
  );
};

export default ChatTab;
