"use client";

import { useEffect, useState, useRef, useMemo } from "react";
import { QueryClient, QueryClientProvider, useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { io, Socket } from "socket.io-client";
import { motion, AnimatePresence } from "framer-motion";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import {
  Bell, CheckCircle, XCircle, Send, Radio,
  LayoutDashboard, Mail, MessageSquare, Facebook, BrainCircuit, Activity,
  Database, Server, RefreshCw
} from "lucide-react";

// ── Utils ──────────────────────────────────────────────────────────────────
function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }
const API = "http://localhost:8000";
const queryClient = new QueryClient();

// ── Types ──────────────────────────────────────────────────────────────────
interface InboxItem {
  filename: string;
  type: string;
  subject?: string;
  from?: string;
  sender?: string;
  person?: string;
  preview?: string;
  content?: string;
  timestamp?: string;
}
interface StatusMap { [key: string]: { status: string; last_active: string } }

// ── Components ─────────────────────────────────────────────────────────────

// Premium Card
function Card({ children, className, glow }: { children: React.ReactNode; className?: string; glow?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      className={cn(
        "relative rounded-xl border border-white/5 bg-black/40 backdrop-blur-xl overflow-hidden group",
        glow && `hover:shadow-[0_0_30px_-10px_${glow}] hover:border-[${glow}]/30 transition-all duration-500`,
        className
      )}
    >
      <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
      <div className="relative z-10 p-5">{children}</div>
    </motion.div>
  );
}

// Sidebar Nav Item
function NavItem({ active, icon: Icon, label, onClick, count }: any) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full flex items-center justify-between px-4 py-3 rounded-lg text-sm transition-all duration-300 relative overflow-hidden group",
        active ? "bg-white/10 text-white font-medium border-l-2 border-primary" : "text-white/40 hover:text-white hover:bg-white/5"
      )}
    >
      <div className="flex items-center gap-3 z-10">
        <Icon className={cn("w-5 h-5", active ? "text-primary" : "group-hover:text-primary transition-colors")} />
        <span>{label}</span>
      </div>
      {count > 0 && (
        <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full", active ? "bg-primary text-black" : "bg-white/10")}>
          {count}
        </span>
      )}
      {active && <div className="absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent z-0" />}
    </button>
  );
}

// Live Feed Item
function FeedItem({ item }: { item: Partial<InboxItem> }) {
  const filename = item.filename || "";
  const type = item.type || "";

  const isGmail = type === "email" || filename.includes("gmail");
  const isWA = type === "whatsapp" || filename.includes("WhatsApp");
  const isFB = type.includes("facebook");

  return (
    <motion.div
      layout initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}
      className="p-4 rounded-lg bg-white/5 border border-white/5 hover:border-white/10 transition-colors mb-3 flex gap-4"
    >
      <div className={cn("p-2 rounded-lg h-fit flex items-center justify-center", isGmail ? "bg-red-500/10 text-red-400" : isWA ? "bg-emerald-500/10" : "bg-blue-500/10 text-blue-400")}>
        {isGmail ? <Mail size={18} /> : isWA ? <img src="https://upload.wikimedia.org/wikipedia/commons/6/6b/WhatsApp.svg" alt="WA" className="w-[18px] h-[18px]" /> : <Facebook size={18} />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex justify-between items-start mb-1">
          <h4 className="font-medium text-white/90 truncate pr-2">{item.subject || item.sender || item.from || "Unknown"}</h4>
          <span className="text-[10px] text-white/30 font-mono whitespace-nowrap">{new Date().toLocaleTimeString()}</span>
        </div>
        <p className="text-sm text-white/50 line-clamp-2">{item.preview || item.content}</p>
      </div>
    </motion.div>
  );
}

// Approval Item
function ApprovalItem({ item, onApprove, onReject }: any) {
  return (
    <motion.div
      layout initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
      className="group relative p-5 rounded-xl bg-gradient-to-br from-white/5 to-black border border-white/10 hover:border-primary/50 transition-all"
    >
      <div className="flex justify-between items-start mb-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-primary px-2 py-0.5 rounded bg-primary/10 border border-primary/20 uppercase tracking-wider">
            {item.type || "TASK"}
          </span>
          <span className="text-xs text-white/30 font-mono">{item.filename}</span>
        </div>
      </div>

      <h3 className="text-lg font-medium text-white mb-2">{item.subject || item.sender || "Pending Action"}</h3>
      <div className="text-sm text-white/60 mb-6 font-mono p-3 bg-black/30 rounded border border-white/5">
        {item.content || item.preview}
      </div>

      <div className="flex gap-3">
        <button onClick={() => onReject(item.filename)}
          className="flex-1 py-2.5 rounded-lg border border-white/10 text-white/40 hover:bg-red-500/10 hover:text-red-400 hover:border-red-500/30 transition-all text-sm font-medium flex items-center justify-center gap-2">
          <XCircle size={16} /> Reject
        </button>
        <button onClick={() => onApprove(item.filename)}
          className="flex-1 py-2.5 rounded-lg bg-primary/20 border border-primary/30 text-primary hover:bg-primary hover:text-black transition-all text-sm font-medium flex items-center justify-center gap-2 shadow-[0_0_15px_-5px_var(--primary)]">
          <CheckCircle size={16} /> Approve
        </button>
      </div>
    </motion.div>
  );
}

// ─── Core Dashboard Logic ───────────────────────────────────────────────────
function DashboardCore() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("live");
  const [socket, setSocket] = useState<Socket | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [notifications, setNotifications] = useState<{ id: string, msg: string, type: string }[]>([]);
  const [connecting, setConnecting] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Queries
  const { data: status } = useQuery({ queryKey: ['status'], queryFn: () => fetch(`${API}/status`).then(r => r.json()), refetchInterval: 3000 });
  const { data: pending } = useQuery({ queryKey: ['pending'], queryFn: () => fetch(`${API}/pending`).then(r => r.json()) });
  const { data: gmail } = useQuery({ queryKey: ['history', 'gmail'], queryFn: () => fetch(`${API}/history/gmail`).then(r => r.json()) });
  const { data: wa } = useQuery({ queryKey: ['history', 'whatsapp'], queryFn: () => fetch(`${API}/history/whatsapp`).then(r => r.json()) });
  const { data: fb } = useQuery({ queryKey: ['history', 'facebook'], queryFn: () => fetch(`${API}/history/facebook`).then(r => r.json()) });

  // Chat State
  const [chatLog, setChatLog] = useState([{ role: "ai", text: "Silver Tier AI Online. Systems Nominal." }]);

  // Socket Connection
  useEffect(() => {
    const s = io(API, { transports: ['websocket'] });
    setSocket(s);

    s.on("connect", () => addToast("System Connected", "success"));
    s.on("disconnect", () => addToast("System Offline", "error"));
    s.on("status_update", () => queryClient.invalidateQueries({ queryKey: ['status'] }));

    // ── KEY: Refresh live feed when watcher syncs new messages ──
    s.on("history_update", (payload: { service: string; data: any[] }) => {
      // Instantly refresh the specific service's history in React Query cache
      queryClient.setQueryData(['history', payload.service], payload.data);
      queryClient.invalidateQueries({ queryKey: ['history', payload.service] });
    });

    s.on("inbox_update", () => {
      queryClient.invalidateQueries({ queryKey: ['pending'] });
      queryClient.invalidateQueries({ queryKey: ['history', 'whatsapp'] });
      queryClient.invalidateQueries({ queryKey: ['history', 'facebook'] });
      queryClient.invalidateQueries({ queryKey: ['history', 'gmail'] });
    });
    s.on("chat_reply", (msg: { role: string; text: string }) => {
      setChatLog(prev => prev.filter(m => m.text !== "Thinking...").concat([msg]));
    });
    s.on("toast", (t: { type: string, message: string }) => addToast(t.message, t.type));

    return () => { s.disconnect(); };
  }, [queryClient]);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chatLog]);

  const addToast = (msg: string, type: string = "info") => {
    const id = Math.random().toString(36);
    setNotifications(prev => [...prev, { id, msg, type }]);
    setTimeout(() => setNotifications(prev => prev.filter(n => n.id !== id)), 4000);
  };

  const sendChat = async () => {
    if (!chatInput.trim()) return;
    const msg = chatInput;
    setChatInput("");
    setChatLog(prev => [...prev, { role: "user", text: msg }, { role: "ai", text: "Thinking..." }]);

    try {
      await fetch(`${API}/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg })
      });
    } catch {
      setChatLog(prev => prev.filter(m => m.text !== "Thinking...").concat([{ role: "error", text: "Command Failed" }]));
    }
  };

  const handleConnect = async (service: string) => {
    setConnecting(service);
    addToast(`Launching ${service} connection...`, "info");
    try {
      await fetch(`${API}/connect/${service}`, { method: "POST" });
      // Poll a bit faster immediately after
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ['status'] }), 2000);
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ['status'] }), 5000);
    } catch (e) {
      addToast(`Failed to connect ${service}`, "error");
    } finally {
      setTimeout(() => setConnecting(null), 8000); // Reset spinner after 8s
    }
  };

  const handleApprove = async (filename: string) => {
    await fetch(`${API}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename }) });
    queryClient.setQueryData(['pending'], (old: any[]) => old.filter((i: any) => i.filename !== filename));
    addToast("Task Approved", "success");
  };

  const handleReject = async (filename: string) => {
    await fetch(`${API}/reject`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename }) });
    queryClient.setQueryData(['pending'], (old: any[]) => old.filter((i: any) => i.filename !== filename));
    addToast("Task Rejected", "info");
  };

  const feed = useMemo(() => {
    const all = [
      ...(gmail || []).map((i: any) => ({ ...i, type: "email" })),
      ...(wa || []).map((i: any) => ({ ...i, type: "whatsapp" })),
      ...(fb || []).map((i: any) => ({ ...i, type: "facebook" }))
    ];
    return all.slice(0, 50);
  }, [gmail, wa, fb]);

  // Filter feed for specific tabs
  const displayFeed = useMemo(() => {
    if (tab === "gmail") return feed.filter(i => i.type === "email" || i.filename?.includes("gmail"));
    if (tab === "whatsapp") return feed.filter(i => i.type === "whatsapp" || i.filename?.includes("WhatsApp"));
    if (tab === "facebook") return feed.filter(i => i.type.includes("facebook"));
    return feed;
  }, [tab, feed]);

  return (
    <div className="flex h-screen bg-[#050508] text-slate-100 font-sans selection:bg-primary/30 overflow-hidden">
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] bg-blue-900/5 blur-[120px] rounded-full mix-blend-screen" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[50%] h-[50%] bg-amber-900/5 blur-[120px] rounded-full mix-blend-screen" />
      </div>

      <div className="fixed top-6 right-6 z-50 flex flex-col gap-2 pointer-events-none">
        <AnimatePresence>
          {notifications.map(n => (
            <motion.div
              key={n.id} initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}
              className={cn(
                "px-4 py-3 rounded-lg border backdrop-blur-md shadow-2xl pointer-events-auto min-w-[280px] flex items-center gap-3",
                n.type === "success" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" :
                  n.type === "error" ? "bg-red-500/10 border-red-500/20 text-red-400" :
                    "bg-zinc-800/80 border-white/10 text-white"
              )}
            >
              <div className={cn("w-2 h-2 rounded-full shadow-[0_0_10px_currentColor]", n.type === "success" ? "bg-emerald-400" : n.type === "error" ? "bg-red-400" : "bg-primary")} />
              <span className="text-sm font-medium">{n.msg}</span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <div className="w-64 border-r border-white/5 bg-black/40 backdrop-blur-xl flex flex-col z-10">
        <div className="p-6 border-b border-white/5">
          <div className="flex items-center gap-2 text-xl font-bold tracking-tight text-white mb-1">
            <BrainCircuit className="text-primary" />
            <span>AI Assistant</span>
          </div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-white/30 pl-8">Autonomous Entity</div>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          <NavItem active={tab === "live"} icon={Activity} label="Live Feed" onClick={() => setTab("live")} />
          <NavItem active={tab === "approvals"} icon={CheckCircle} label="Approvals" onClick={() => setTab("approvals")} count={pending?.length || 0} />
          <NavItem active={tab === "chat"} icon={MessageSquare} label="Command Console" onClick={() => setTab("chat")} />
          <div className="my-4 border-t border-white/5" />
          <div className="px-4 text-xs font-semibold text-white/20 uppercase tracking-widest mb-2">Systems</div>
          <NavItem active={tab === "gmail"} icon={Mail} label="Gmail" onClick={() => setTab("gmail")} count={gmail?.length} />

          <button
            onClick={() => setTab("whatsapp")}
            className={cn(
              "w-full flex items-center justify-between px-4 py-3 rounded-lg text-sm transition-all duration-300 relative overflow-hidden group",
              tab === "whatsapp" ? "bg-white/10 text-white font-medium border-l-2 border-primary" : "text-white/40 hover:text-white hover:bg-white/5"
            )}
          >
            <div className="flex items-center gap-3 z-10">
              <img src="https://upload.wikimedia.org/wikipedia/commons/6/6b/WhatsApp.svg" alt="WhatsApp" className="w-5 h-5" />
              <span>WhatsApp</span>
            </div>
            {(wa?.length || 0) > 0 && (
              <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full", tab === "whatsapp" ? "bg-primary text-black" : "bg-white/10")}>
                {wa?.length}
              </span>
            )}
            {tab === "whatsapp" && <div className="absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent z-0" />}
          </button>
          <NavItem active={tab === "facebook"} icon={Facebook} label="Facebook" onClick={() => setTab("facebook")} count={fb?.length} />
        </nav>

        <div className="p-4 bg-black/20 border-t border-white/5">
          <div className="flex items-center gap-3">
            <div className={cn("w-2 h-2 rounded-full shadow-[0_0_10px_currentColor]", socket?.connected ? "bg-emerald-500 text-emerald-500" : "bg-red-500 text-red-500")} />
            <div className="text-xs text-white/50">{socket?.connected ? "Brain Connected" : "Brain Offline"}</div>
          </div>
        </div>
      </div>

      <main className="flex-1 relative z-10 flex flex-col min-w-0">
        <header className="h-16 border-b border-white/5 flex items-center justify-between px-8 bg-black/20 backdrop-blur-sm">
          <div className="flex items-center gap-2 text-white/80">
            <LayoutDashboard size={18} className="text-primary" />
            <span className="font-medium capitalize">{tab.replace("-", " ")}</span>
          </div>
          <div className="flex gap-4">
            <div className="flex gap-2">
              {Object.entries(status || {}).map(([Key, Val]: any) => (
                <div key={Key} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/5 border border-white/5">
                  <div className={cn("w-1.5 h-1.5 rounded-full", Val.status === "online" ? "bg-emerald-500" : "bg-red-500")} />
                  <span className="text-[10px] uppercase font-bold text-white/50">{Key}</span>
                </div>
              ))}
            </div>
          </div>
        </header>

        <div className="flex-1 p-8 overflow-y-auto">
          <AnimatePresence mode="wait">
            {/* ── LIVE FEED & SERVICE TABS ── */}
            {(tab === "live" || tab === "gmail" || tab === "whatsapp" || tab === "facebook") && (
              <motion.div key="feed" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="max-w-4xl mx-auto space-y-6">

                {/* Stats Cards - Only on Live Tab */}
                {tab === "live" && (
                  <div className="grid grid-cols-3 gap-4 mb-8">
                    <Card glow="#10b981" className="bg-emerald-500/5 border-emerald-500/10 relative group/card">
                      <div className="flex justify-between items-start">
                        <div className="text-emerald-400 mb-2"><MessageSquare /></div>
                        {status?.whatsapp?.status !== 'online' && (
                          <button
                            disabled={connecting === 'whatsapp'}
                            onClick={() => handleConnect('whatsapp')}
                            className={cn(
                              "transition-all bg-emerald-500/20 hover:bg-emerald-500/40 text-emerald-400 text-xs px-2 py-1 rounded",
                              connecting === 'whatsapp' ? "opacity-100 cursor-wait" : "opacity-0 group-hover/card:opacity-100"
                            )}>
                            {connecting === 'whatsapp' ? "Connecting..." : "Connect"}
                          </button>
                        )}
                      </div>
                      <div className="text-2xl font-bold text-white">{wa?.length || 0}</div>
                      <div className="text-xs text-white/30 uppercase tracking-widest flex items-center gap-2">
                        WhatsApp
                        {status?.whatsapp?.status === 'online' && <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_5px_currentColor]" />}
                      </div>
                    </Card>

                    <Card glow="#ef4444" className="bg-red-500/5 border-red-500/10 relative group/card">
                      <div className="flex justify-between items-start">
                        <div className="text-red-400 mb-2"><Mail /></div>
                        {status?.gmail?.status !== 'online' && (
                          <button
                            disabled={connecting === 'gmail'}
                            onClick={() => handleConnect('gmail')}
                            className={cn(
                              "transition-all bg-red-500/20 hover:bg-red-500/40 text-red-400 text-xs px-2 py-1 rounded",
                              connecting === 'gmail' ? "opacity-100 cursor-wait" : "opacity-0 group-hover/card:opacity-100"
                            )}>
                            {connecting === 'gmail' ? "Auth..." : "Connect"}
                          </button>
                        )}
                      </div>
                      <div className="text-2xl font-bold text-white">{gmail?.length || 0}</div>
                      <div className="text-xs text-white/30 uppercase tracking-widest flex items-center gap-2">
                        Gmail
                        {status?.gmail?.status === 'online' && <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_5px_currentColor]" />}
                      </div>
                    </Card>

                    <Card glow="#3b82f6" className="bg-blue-500/5 border-blue-500/10 relative group/card">
                      <div className="flex justify-between items-start">
                        <div className="text-blue-400 mb-2"><Facebook /></div>
                        {status?.facebook?.status !== 'online' && (
                          <button
                            disabled={connecting === 'facebook'}
                            onClick={() => handleConnect('facebook')}
                            className={cn(
                              "transition-all bg-blue-500/20 hover:bg-blue-500/40 text-blue-400 text-xs px-2 py-1 rounded",
                              connecting === 'facebook' ? "opacity-100 cursor-wait" : "opacity-0 group-hover/card:opacity-100"
                            )}>
                            {connecting === 'facebook' ? "Connecting..." : "Connect"}
                          </button>
                        )}
                      </div>
                      <div className="text-2xl font-bold text-white">{fb?.length || 0}</div>
                      <div className="text-xs text-white/30 uppercase tracking-widest flex items-center gap-2">
                        Facebook
                        {status?.facebook?.status === 'online' && <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_5px_currentColor]" />}
                      </div>
                    </Card>
                  </div>
                )}

                <div>
                  <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
                    <Radio className="text-primary animate-pulse" size={18} /> {tab === "live" ? "Live Stream" : `${tab} Feed`}
                  </h3>
                  <div className="space-y-2">
                    <AnimatePresence initial={false}>
                      {displayFeed.map((item, i) => <FeedItem key={i} item={item} />)}
                    </AnimatePresence>
                    {displayFeed.length === 0 && <div className="text-center py-20 text-white/20">No recent activity detected.</div>}
                  </div>
                </div>
              </motion.div>
            )}

            {/* ── APPROVALS TAB ── */}
            {tab === "approvals" && (
              <motion.div key="approvals" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="max-w-3xl mx-auto">
                <h3 className="text-lg font-medium text-white mb-6 flex items-center gap-2">
                  <CheckCircle className="text-primary" size={18} /> Pending Approvals
                  <span className="bg-white/10 px-2 py-0.5 rounded-full text-xs text-white/50">{pending?.length || 0}</span>
                </h3>
                <div className="grid gap-4">
                  <AnimatePresence>
                    {(pending || []).map((item: any) => (
                      <ApprovalItem key={item.filename} item={item} onApprove={handleApprove} onReject={handleReject} />
                    ))}
                  </AnimatePresence>
                  {pending?.length === 0 && (
                    <div className="text-center py-20 border border-dashed border-white/10 rounded-xl">
                      <CheckCircle className="mx-auto text-white/10 mb-2" size={48} />
                      <p className="text-white/30">All tasks handled. You're clear.</p>
                    </div>
                  )}
                </div>
              </motion.div>
            )}

            {/* ── CHAT TAB ── */}
            {tab === "chat" && (
              <motion.div key="chat" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col h-[calc(100vh-180px)] max-w-4xl mx-auto">
                <div className="flex-1 overflow-y-auto mb-4 space-y-4 pr-2">
                  {chatLog.map((msg, i) => (
                    <motion.div
                      key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                      className={cn(
                        "flex gap-3 max-w-[80%]",
                        msg.role === "user" ? "ml-auto flex-row-reverse" : ""
                      )}
                    >
                      <div className={cn(
                        "w-8 h-8 rounded-full flex items-center justify-center shrink-0 border",
                        msg.role === "user" ? "bg-white/10 border-white/10" :
                          msg.role === "error" ? "bg-red-500/10 border-red-500/20 text-red-400" :
                            "bg-primary/10 border-primary/20 text-primary"
                      )}>
                        {msg.role === "user" ? "You" : <BrainCircuit size={16} />}
                      </div>
                      <div className={cn(
                        "p-3 rounded-2xl text-sm leading-relaxed",
                        msg.role === "user" ? "bg-white text-black" :
                          msg.role === "error" ? "bg-red-500/10 text-red-200 border border-red-500/20" :
                            "bg-white/5 text-white/90 border border-white/10"
                      )}>
                        {msg.text}
                      </div>
                    </motion.div>
                  ))}
                  <div ref={chatEndRef} />
                </div>
                <div className="relative">
                  <input
                    type="text"
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && sendChat()}
                    placeholder="Command the system..."
                    className="w-full bg-black/40 border border-white/10 rounded-xl px-5 py-4 pr-14 text-white placeholder-white/20 focus:outline-none focus:border-primary/50 transition-colors"
                    autoFocus
                  />
                  <button onClick={sendChat} className="absolute right-2 top-2 p-2 bg-primary text-black rounded-lg hover:bg-primary/90 transition-colors">
                    <Send size={18} />
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}

// ── Wrapper ────────────────────────────────────────────────────────────────
export default function Dashboard() {
  return (
    <QueryClientProvider client={queryClient}>
      <DashboardCore />
    </QueryClientProvider>
  );
}
