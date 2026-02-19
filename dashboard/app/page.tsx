"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { io, Socket } from "socket.io-client";
import { motion, AnimatePresence } from "framer-motion";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { FaWhatsapp, FaFacebook, FaCheckCircle, FaRobot, FaBolt } from "react-icons/fa";
import { SiGmail } from "react-icons/si";
import { LuBrainCircuit, LuLayoutDashboard } from "react-icons/lu";

// ── Utils ──────────────────────────────────────────────────────────────────
function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }
const API = "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────
interface Stats { needs_action: number; pending: number; approved: number; done: number; rejected: number; }
interface InboxItem {
  filename?: string;
  id?: string;
  content?: string;
  type?: string;
  from?: string;
  sender?: string;
  subject?: string;
  snippet?: string;  // from Gmail history
  preview?: string;  // from WA/FB history
  timestamp?: string;
  date?: string;
  _body?: string;
  summary?: string;
  details?: string;
}
interface StatusMap { [key: string]: { status: string; last_active: string; pid: number } }
interface ToastItem { id: string; type: "success" | "error" | "info"; message: string; }
type Tab = "overview" | "gmail" | "whatsapp" | "facebook" | "approvals" | "chat";

// ── Hook: Toast ────────────────────────────────────────────────────────────
function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const add = useCallback((type: ToastItem["type"], message: string) => {
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2);
    setToasts(p => [...p, { id, type, message }]);
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4000);
  }, []);
  return { toasts, add };
}

// ── Main Dashboard ─────────────────────────────────────────────────────────
export default function Dashboard() {
  const [tab, setTab] = useState<Tab>("overview");
  const [connected, setConnected] = useState(false);
  const [stats, setStats] = useState<Stats>({ needs_action: 0, pending: 0, approved: 0, done: 0, rejected: 0 });

  // Real-time Data
  const [statusMap, setStatusMap] = useState<StatusMap>({});

  // History / Inbox
  const [gmailHistory, setGmailHistory] = useState<InboxItem[]>([]);
  const [waHistory, setWaHistory] = useState<InboxItem[]>([]);
  const [fbHistory, setFbHistory] = useState<InboxItem[]>([]);
  const [pending, setPending] = useState<InboxItem[]>([]);

  // Chat
  const [chatLog, setChatLog] = useState<{ role: string; text: string }[]>([
    { role: "ai", text: "🤖 System Online. Ready for commands." },
  ]);
  const [chatInput, setChatInput] = useState("");
  const { toasts, add } = useToast();
  const chatEnd = useRef<HTMLDivElement>(null);

  // ── Fetchers ───────────────────────────────────────────────────────────
  const fetchStats = useCallback(async () => { try { const r = await fetch(`${API}/stats`); if (r.ok) setStats(await r.json()); } catch { } }, []);
  const fetchStatus = useCallback(async () => { try { const r = await fetch(`${API}/status`); if (r.ok) setStatusMap(await r.json()); } catch { } }, []);
  const fetchPending = useCallback(async () => {
    try {
      const r = await fetch(`${API}/pending`);
      if (r.ok) {
        const data: InboxItem[] = await r.json();
        // Filter out items that are not relevant to the 3 core services if needed
        // For now, user request was "kaam ki cheese ha jo in 3 cheeso ke related just wohi honi chahiye"
        // We can filter by checking content/type or just rely on the archive cleanup I did.
        // But to be safe, let's filter the UI too.
        // Actually, the simplest way is to just show them. The cleanup script handled the bulk. 
        // But I will add a client-side filter just in case.
        const relevant = data.filter(i =>
          (i.filename && (i.filename.includes("gmail") || i.filename.includes("WhatsApp") || i.filename.includes("Facebook"))) ||
          (i.type && ["email", "whatsapp", "facebook", "friend_request"].includes(i.type))
        );
        setPending(relevant.length > 0 ? relevant : data); // If filter removes everything but data exists, maybe show data? No, show relevant only.
        setPending(relevant);
      }
    } catch { }
  }, []);

  const fetchHistory = useCallback(async (service: string) => {
    try {
      const r = await fetch(`${API}/history/${service}`);
      if (r.ok) {
        const data = await r.json();
        if (service === "gmail") setGmailHistory(data);
        if (service === "whatsapp") setWaHistory(data);
        if (service === "facebook") setFbHistory(data);
      }
    } catch { }
  }, []);

  const refreshAll = useCallback(() => {
    fetchStats(); fetchStatus(); fetchPending();
    fetchHistory("gmail"); fetchHistory("whatsapp"); fetchHistory("facebook");
  }, [fetchStats, fetchStatus, fetchPending, fetchHistory]);

  // ── Handlers ───────────────────────────────────────────────────────────
  const handleConnect = async (service: string) => {
    add("info", `🚀 Launching ${service} connection...`);
    try {
      // Trigger backend to launch auth flow
      await fetch(`${API}/connect/${service}`, { method: 'POST' });
    } catch {
      add("error", "Failed to launch connection");
    }
  };

  // ── Socket ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const socket: Socket = io(API, { transports: ["websocket", "polling"] });
    socket.on("connect", () => { setConnected(true); add("success", "🟢 Brain Connected"); refreshAll(); });
    socket.on("disconnect", () => setConnected(false));

    // Updates
    socket.on("status_update", () => fetchStatus());
    socket.on("history_update", (d: { service: string; data: InboxItem[] }) => {
      if (d.service === "gmail") setGmailHistory(d.data);
      if (d.service === "whatsapp") setWaHistory(d.data);
      if (d.service === "facebook") setFbHistory(d.data);
    });

    socket.on("inbox_update", () => { fetchStats(); add("info", "📥 New Needs Action item"); });
    socket.on("approval_update", (d: InboxItem & { action: string }) => {
      if (d.action === "created") {
        setPending(p => [d, ...p]);
        add("info", `⏳ Approval Required: ${d.filename}`);
      }
      fetchStats();
    });

    socket.on("toast", (d: { type: ToastItem["type"]; message: string }) => add(d.type, d.message));
    refreshAll(); // Initial fetch

    // Polling fallback every 10s just in case
    const interval = setInterval(refreshAll, 10000);
    return () => { socket.disconnect(); clearInterval(interval); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [chatLog]);

  // ── Actions ────────────────────────────────────────────────────────────
  const approve = async (filename: string) => {
    setPending(p => p.filter(t => t.filename !== filename));
    try { await fetch(`${API}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename }) }); } catch { }
  };
  const reject = async (filename: string) => {
    setPending(p => p.filter(t => t.filename !== filename));
    try { await fetch(`${API}/reject`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename }) }); } catch { }
  };
  const sendChat = async () => {
    if (!chatInput.trim()) return;
    const msg = chatInput.trim();
    setChatInput("");
    setChatLog(p => [...p, { role: "user", text: msg }]);
    try {
      await fetch(`${API}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: msg }) });
      setChatLog(p => [...p, { role: "ai", text: "⚡ Processing..." }]);
    } catch {
      setChatLog(p => [...p, { role: "error", text: "❌ Connection Error" }]);
    }
  };

  // ── Nav Items ──────────────────────────────────────────────────────────
  const navItems = [
    { id: "overview", icon: <LuLayoutDashboard />, label: "Overview" },
    { id: "gmail", icon: <SiGmail />, label: "Gmail", count: gmailHistory.length, status: statusMap.gmail?.status },
    { id: "whatsapp", icon: <FaWhatsapp />, label: "WhatsApp", count: waHistory.length, status: statusMap.whatsapp?.status },
    { id: "facebook", icon: <FaFacebook />, label: "Facebook", count: fbHistory.length, status: statusMap.facebook?.status },
    { id: "approvals", icon: <FaCheckCircle />, label: "Approvals", count: pending.length, highlight: pending.length > 0 },
    { id: "chat", icon: <FaRobot />, label: "AI Chat" },
  ];

  return (
    <div className="flex h-screen bg-[#050508] text-slate-100 font-sans selection:bg-cyan-500/30">

      {/* Background Ambience */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute -top-[20%] -left-[10%] w-[50%] h-[50%] bg-blue-900/10 blur-[120px] rounded-full mix-blend-screen" />
        <div className="absolute top-[20%] right-[0%] w-[40%] h-[40%] bg-cyan-900/10 blur-[100px] rounded-full mix-blend-screen" />
        <div className="absolute -bottom-[20%] left-[20%] w-[60%] h-[40%] bg-indigo-900/10 blur-[120px] rounded-full mix-blend-screen" />
      </div>

      {/* Toast Overlay */}
      <div className="fixed top-6 right-6 z-50 flex flex-col gap-3 pointer-events-none">
        <AnimatePresence>
          {toasts.map(t => (
            <motion.div key={t.id} initial={{ opacity: 0, x: 50, scale: 0.9 }} animate={{ opacity: 1, x: 0, scale: 1 }} exit={{ opacity: 0, x: 20, scale: 0.9 }}
              className={cn(
                "px-4 py-3 rounded-xl text-sm font-medium shadow-2xl backdrop-blur-xl border pointer-events-auto min-w-[300px]",
                t.type === "success" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300 shadow-emerald-900/20" :
                  t.type === "error" ? "bg-rose-500/10 border-rose-500/20 text-rose-300 shadow-rose-900/20" :
                    "bg-cyan-500/10 border-cyan-500/20 text-cyan-300 shadow-cyan-900/20"
              )}>
              <div className="flex items-center gap-3">
                <div className={cn("w-2 h-2 rounded-full shadow-[0_0_10px_currentColor]", t.type === "success" ? "bg-emerald-400" : t.type === "error" ? "bg-rose-400" : "bg-cyan-400")} />
                {t.message}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Sidebar */}
      <div className="w-64 shrink-0 z-10 flex flex-col border-r border-white/5 bg-black/20 backdrop-blur-xl">
        <div className="p-6 border-b border-white/5">
          <div className="text-xl font-bold bg-gradient-to-r from-white to-white/50 bg-clip-text text-transparent tracking-tight flex items-center gap-3">
            <LuBrainCircuit className="text-cyan-400" /> Silver Tier
          </div>
          <div className="text-[11px] text-white/30 tracking-widest uppercase mt-1 font-medium pl-8">Autonomous Entity</div>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {navItems.map(item => (
            <button key={item.id} onClick={() => setTab(item.id as Tab)}
              className={cn(
                "w-full flex items-center justify-between px-4 py-3 rounded-xl text-sm transition-all duration-300 group reltative overflow-hidden",
                tab === item.id
                  ? "bg-white/5 text-white font-medium shadow-[0_0_20px_-5px_rgba(255,255,255,0.1)] border border-white/10"
                  : "text-white/40 hover:text-white/80 hover:bg-white/5 border border-transparent"
              )}>
              <div className="flex items-center gap-3 relative z-10">
                <span className={cn("text-lg transition-transform duration-300", tab === item.id ? "scale-110" : "group-hover:scale-110")}>{item.icon}</span>
                <span>{item.label}</span>
              </div>

              <div className="flex items-center gap-2">
                {/* Status Dot */}
                {item.status && (
                  <div className={cn("w-1.5 h-1.5 rounded-full shadow-[0_0_8px_currentColor]", item.status === "online" ? "bg-emerald-500 text-emerald-500" : "bg-amber-500 text-amber-500")} />
                )}
                {/* Count Badge */}
                {item.count !== undefined && item.count > 0 && (
                  <span className={cn(
                    "text-[10px] font-bold px-2 py-0.5 rounded-full border",
                    item.highlight
                      ? "bg-cyan-500 text-black border-cyan-400 shadow-[0_0_15px_-3px_rgba(6,182,212,0.6)] animate-pulse"
                      : "bg-white/10 text-white/70 border-white/5"
                  )}>
                    {item.count}
                  </span>
                )}
              </div>
            </button>
          ))}
        </nav>

        <div className="p-6 border-t border-white/5">
          <div className="flex items-center gap-3">
            <div className={cn("w-2 h-2 rounded-full shadow-[0_0_15px_currentColor] transition-all duration-500", connected ? "bg-emerald-500 text-emerald-500" : "bg-rose-500 text-rose-500")} />
            <div className="text-xs font-medium text-white/50">{connected ? "Brain Connected" : "Brain Offline"}</div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative z-10">
        {/* Header */}
        <header className="h-20 border-b border-white/5 flex items-center justify-between px-8 bg-black/10 backdrop-blur-sm">
          <div>
            <h1 className="text-lg font-medium text-white/90 capitalize tracking-wide">{tab.replace("_", " ")}</h1>
            <p className="text-xs text-white/30 mt-0.5">Real-time Command Center</p>
          </div>
          <div className="flex items-center gap-4">
            <button onClick={refreshAll} className="p-2 rounded-lg hover:bg-white/5 text-white/30 hover:text-white transition-colors">
              ↺
            </button>
          </div>
        </header>

        {/* Scroll Area */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden p-8">
          <AnimatePresence mode="wait">
            <motion.div key={tab} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }}>

              {/* ── STATUS DASHBOARD ── */}
              {tab === "overview" && (
                <div className="space-y-8 max-w-7xl mx-auto">
                  {/* Stats Grid - Hidden per user request to 'khatam karo' the 300+ confusing stats. 
                      Replacing with a cleaner Status Summary of the 3 active services. 
                  */}
                  <div className="grid grid-cols-3 gap-6 mb-8">
                    {/* We can just show the Service Status Cards as the main view. */}
                  </div>

                  {/* Services Status */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <ServiceStatus title="Gmail" icon={<SiGmail />} status={statusMap.gmail} count={gmailHistory.length} color="rose" onClick={() => setTab("gmail")} onConnect={() => handleConnect("gmail")} />
                    <ServiceStatus title="WhatsApp" icon={<FaWhatsapp />} status={statusMap.whatsapp} count={waHistory.length} color="emerald" onClick={() => setTab("whatsapp")} onConnect={() => handleConnect("whatsapp")} />
                    <ServiceStatus title="Facebook" icon={<FaFacebook />} status={statusMap.facebook} count={fbHistory.length} color="blue" onClick={() => setTab("facebook")} onConnect={() => handleConnect("facebook")} />
                  </div>

                  {/* Pending Tasks */}
                  {pending.length > 0 && (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <h2 className="text-sm font-semibold text-white/70 uppercase tracking-wider">⚡ Pending Approvals</h2>
                      </div>
                      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                        {pending.map(item => (
                          <ApprovalCard key={item.filename} item={item} onApprove={approve} onReject={reject} />
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ── GMAIL TAB ── */}
              {tab === "gmail" && (
                <div className="space-y-6 max-w-5xl mx-auto">
                  <div className="flex items-center justify-between">
                    <h2 className="text-xl font-light text-white">Inbox History</h2>
                    <Badge status={statusMap.gmail?.status} />
                  </div>
                  {gmailHistory.length === 0 ? <Empty msg="No email history synced yet." /> :
                    gmailHistory.map(email => <GmailCard key={email.id || email.filename} item={email} />)
                  }
                </div>
              )}

              {/* ── WHATSAPP TAB ── */}
              {tab === "whatsapp" && (
                <div className="space-y-6 max-w-5xl mx-auto">
                  <div className="flex items-center justify-between">
                    <h2 className="text-xl font-light text-white">Recent Chats</h2>
                    <Badge status={statusMap.whatsapp?.status} />
                  </div>
                  {waHistory.length === 0 ? <Empty msg="No WhatsApp history synced yet." /> :
                    waHistory.map((chat, i) => <WhatsappCard key={i} item={chat} />)
                  }
                </div>
              )}

              {/* ── FACEBOOK TAB ── */}
              {tab === "facebook" && (
                <div className="space-y-6 max-w-5xl mx-auto">
                  <div className="flex items-center justify-between">
                    <h2 className="text-xl font-light text-white">Timeline & Events</h2>
                    <Badge status={statusMap.facebook?.status} />
                  </div>
                  {fbHistory.length === 0 ? <Empty msg="No Facebook history synced yet." /> :
                    fbHistory.map((evt, i) => <FacebookCard key={i} item={evt} />)
                  }
                </div>
              )}

              {/* ── APPROVALS TAB ── */}
              {tab === "approvals" && (
                <div className="space-y-6 max-w-5xl mx-auto">
                  <div className="flex items-center justify-between">
                    <h2 className="text-xl font-light text-white">Pending Actions</h2>
                    <div className="text-xs text-white/40">{pending.length} waiting</div>
                  </div>
                  {pending.length === 0 ? <Empty msg="All clear. No pending actions." /> :
                    pending.map(item => <ApprovalCard key={item.filename} item={item} onApprove={approve} onReject={reject} />)
                  }
                </div>
              )}

              {/* ── CHAT TAB ── */}
              {tab === "chat" && (
                <div className="max-w-4xl mx-auto h-[70vh] flex flex-col bg-white/5 border border-white/10 rounded-2xl overflow-hidden backdrop-blur-sm shadow-2xl">
                  {/* Chat messages */}
                  <div className="flex-1 overflow-y-auto p-6 space-y-4">
                    {chatLog.map((m, i) => (
                      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                        <div className={cn(
                          "max-w-[80%] px-5 py-3 rounded-2xl text-sm leading-relaxed shadow-lg",
                          m.role === "user"
                            ? "bg-cyan-600/20 border border-cyan-500/30 text-cyan-100 rounded-br-none"
                            : "bg-white/10 border border-white/5 text-white/80 rounded-bl-none"
                        )}>
                          {m.text}
                        </div>
                      </motion.div>
                    ))}
                    <div ref={chatEnd} />
                  </div>
                  {/* Input */}
                  <div className="p-4 bg-white/5 border-t border-white/5 flex gap-3">
                    <input
                      className="flex-1 bg-black/20 border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-500/50 transition-all placeholder-white/20"
                      placeholder="Instruct System AI..."
                      value={chatInput}
                      onChange={e => setChatInput(e.target.value)}
                      onKeyDown={e => e.key === "Enter" && sendChat()}
                      autoFocus
                    />
                    <button onClick={sendChat} className="px-6 py-3 bg-cyan-600 hover:bg-cyan-500 text-white rounded-xl font-medium transition-all shadow-[0_0_20px_-5px_rgba(6,182,212,0.5)]">
                      Send
                    </button>
                  </div>
                </div>
              )}

            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

// ── Components ─────────────────────────────────────────────────────────────

function StatCard({ label, value, color, glow }: any) {
  return (
    <div className={cn("p-5 rounded-2xl bg-white/5 border border-white/5 backdrop-blur-md transition-all hover:bg-white/10 hover:border-white/10 group", glow && `hover:${glow} hover:shadow-2xl`)}>
      <div className="text-[10px] uppercase tracking-widest text-white/30 font-semibold mb-1">{label}</div>
      <div className={cn("text-3xl font-bold transition-all group-hover:scale-105 origin-left", color)}>{value}</div>
    </div>
  );
}

function ServiceStatus({ title, icon, status, count, color, onClick, onConnect }: any) {
  const isOnline = status?.status === "online";
  const lastActive = status?.last_active ? new Date(status.last_active).toLocaleTimeString() : "Never";

  const colorStyles = {
    rose: "group-hover:text-rose-400 group-hover:border-rose-500/30 group-hover:shadow-[0_0_30px_-10px_rgba(244,63,94,0.3)]",
    emerald: "group-hover:text-emerald-400 group-hover:border-emerald-500/30 group-hover:shadow-[0_0_30px_-10px_rgba(16,185,129,0.3)]",
    blue: "group-hover:text-blue-400 group-hover:border-blue-500/30 group-hover:shadow-[0_0_30px_-10px_rgba(59,130,246,0.3)]"
  }[color as string] || "";

  return (
    <button onClick={onClick} className={cn("group text-left p-6 rounded-2xl bg-white/5 border border-white/5 backdrop-blur-md transition-all duration-300 relative overflow-hidden", colorStyles)}>
      <div className="flex items-start justify-between mb-4 relative z-10">
        <div className="text-3xl p-3 bg-white/5 rounded-2xl border border-white/5">{icon}</div>
        <div className="text-right">
          <div className="text-3xl font-bold text-white transition-colors">{count}</div>
          <div className="text-[10px] text-white/30 uppercase tracking-wider">Items</div>
        </div>
      </div>
      <div className="relative z-10">
        <div className="text-lg font-medium text-white/80 transition-colors flex items-center justify-between">
          {title}
          {!isOnline && (
            <div onClick={(e) => { e.stopPropagation(); onConnect(); }}
              className="text-[10px] px-2 py-1 bg-white/10 rounded hover:bg-white/20 border border-white/10 transition-colors uppercase tracking-wider font-bold">
              Connect
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 mt-1.5">
          <div className={cn("w-1.5 h-1.5 rounded-full shadow-[0_0_8px_currentColor]", isOnline ? "bg-emerald-500 text-emerald-500 animate-pulse" : "bg-red-500 text-red-500")} />
          <div className="text-xs text-white/30">
            {isOnline ? `Live • Last seen ${lastActive}` : "Offline"}
          </div>
        </div>
      </div>
      {/* Glow bg */}
      <div className={cn("absolute -bottom-10 -right-10 w-32 h-32 blur-[60px] opacity-0 group-hover:opacity-20 transition-opacity",
        color === "rose" ? "bg-rose-500" : color === "emerald" ? "bg-emerald-500" : "bg-blue-500")} />
    </button>
  );
}

function ApprovalCard({ item, onApprove, onReject }: any) {
  const title = item.subject || item.person || item.filename;
  const content = item.preview || item.snippet || item.content || "";

  return (
    <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-md hover:border-cyan-500/30 transition-all group">
      <div className="flex items-start justify-between mb-3">
        <div className="text-sm font-medium text-cyan-200 truncate pr-4">{title}</div>
        <div className="text-[10px] bg-white/5 px-2 py-1 rounded text-white/30 font-mono">{item.type || "TASK"}</div>
      </div>
      <div className="text-xs text-white/50 leading-relaxed line-clamp-3 mb-5 font-mono bg-black/20 p-3 rounded-lg border border-white/5">
        {content.slice(0, 300)}
      </div>
      <div className="flex gap-3">
        <button onClick={() => onReject(item.filename)} className="flex-1 py-2 rounded-lg border border-white/10 hover:bg-rose-500/20 hover:border-rose-500/50 hover:text-rose-200 transition-all text-xs text-white/40">Reject</button>
        <button onClick={() => onApprove(item.filename)} className="flex-1 py-2 rounded-lg bg-cyan-600/20 border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/30 hover:shadow-[0_0_15px_-5px_rgba(6,182,212,0.5)] transition-all text-xs font-medium">Approve</button>
      </div>
    </div>
  );
}

function Badge({ status }: { status: string }) {
  if (status === "online") return <div className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-bold shadow-[0_0_10px_-3px_rgba(16,185,129,0.3)]">ONLINE</div>;
  return <div className="px-2 py-0.5 rounded-full bg-red-500/10 border border-red-500/20 text-red-400 text-[10px] font-bold">OFFLINE</div>;
}

function Empty({ msg }: { msg: string }) {
  return <div className="py-20 text-center border border-dashed border-white/10 rounded-2xl bg-white/2"><div className="text-white/20 text-sm">{msg}</div></div>;
}

function GmailCard({ item }: { item: InboxItem }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-5 rounded-xl bg-white/5 border border-white/5 hover:border-rose-500/30 hover:bg-white/10 transition-all group">
      <div className="flex justify-between items-start mb-1">
        <div className="text-sm font-medium text-white/90">{item.from}</div>
        <div className="text-[10px] text-white/30">{item.date ? new Date(item.date).toLocaleDateString() : ""}</div>
      </div>
      <div className="text-xs text-rose-200/80 mb-2 font-medium">{item.subject}</div>
      <div className="text-xs text-white/40 line-clamp-2">{item.snippet}</div>
    </motion.div>
  );
}

function WhatsappCard({ item }: { item: InboxItem }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-5 rounded-xl bg-white/5 border border-white/5 hover:border-emerald-500/30 hover:bg-white/10 transition-all">
      <div className="flex justify-between items-start mb-2">
        <div className="text-sm font-medium text-emerald-300">{item.sender}</div>
        <div className="text-[10px] text-white/30">{item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : ""}</div>
      </div>
      <div className="text-xs text-white/60 bg-black/20 p-3 rounded-lg border border-white/5 inline-block max-w-full">
        {item.preview}
      </div>
    </motion.div>
  );
}

function FacebookCard({ item }: { item: InboxItem }) {
  const isReq = item.type === "friend_request";
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-5 rounded-xl bg-white/5 border border-white/5 hover:border-blue-500/30 hover:bg-white/10 transition-all flex items-start gap-4">
      <div className={cn("mt-1 p-2 rounded-lg border", isReq ? "bg-blue-500/20 border-blue-500/30 text-blue-300" : "bg-purple-500/20 border-purple-500/30 text-purple-300")}>
        {isReq ? <FaFacebook /> : <FaBolt />}
      </div>
      <div>
        <div className="text-sm font-medium text-white/90">{item.subject || (item as any).summary || "Facebook Event"}</div>
        <div className="text-xs text-white/40 mt-1">{item.content || (item as any).details}</div>
        <div className="text-[10px] text-white/20 mt-2">{item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : ""}</div>
      </div>
    </motion.div>
  );
}
