import React, { useState, useRef, useEffect, useCallback } from "react";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000";

type Language = "en" | "hi" | "ta";

interface Message {
  id: string;
  role: "user" | "agent";
  text: string;
  language?: Language;
  timestamp: Date;
}

interface LatencyStats {
  stt_ms: number;
  lang_ms: number;
  agent_ms: number;
  tts_ms: number;
  total_ms: number;
  within_budget: boolean;
}

const LANG_LABELS: Record<Language, string> = {
  en: "English",
  hi: "हिन्दी",
  ta: "தமிழ்",
};

const DEMO_PATIENT_ID = "pat-001";

export default function VoiceAgentApp() {
  const [isConnected, setIsConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [latency, setLatency] = useState<LatencyStats | null>(null);
  const [statusText, setStatusText] = useState("Click connect to start");
  const [patientId, setPatientId] = useState(DEMO_PATIENT_ID);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(`${WS_URL}/ws/voice/${patientId}`);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      setIsConnected(true);
      setStatusText("Connected — press and hold to speak");
      addMessage("agent", "Hello! I'm your healthcare assistant. How can I help you today?", "en");
    };

    ws.onmessage = async (event) => {
      if (event.data instanceof ArrayBuffer) {
        // Audio response — play it
        await playAudio(event.data);
        setIsProcessing(false);
        setStatusText("Connected — press and hold to speak");
        return;
      }

      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "transcript") {
          addMessage("user", msg.text);
          setStatusText(`Thinking… (STT: ${msg.stt_ms}ms)`);
        } else if (msg.type === "response") {
          addMessage("agent", msg.text, msg.language);
        } else if (msg.type === "latency") {
          setLatency(msg);
        } else if (msg.type === "interrupted") {
          setIsProcessing(false);
          setStatusText("Interrupted — speak again");
        } else if (msg.type === "error") {
          setStatusText(`Error: ${msg.message}`);
          setIsProcessing(false);
        }
      } catch (_) {}
    };

    ws.onclose = () => {
      setIsConnected(false);
      setIsRecording(false);
      setIsProcessing(false);
      setStatusText("Disconnected");
    };

    ws.onerror = () => {
      setStatusText("Connection error — is the backend running?");
    };

    wsRef.current = ws;
  }, [patientId]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setIsConnected(false);
    setStatusText("Disconnected");
  }, []);

  const startRecording = useCallback(async () => {
    if (!isConnected || isProcessing) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
          // Stream chunk to backend
          e.data.arrayBuffer().then((buf) => {
            wsRef.current?.send(buf);
          });
        }
      };

      mediaRecorder.start(100); // 100ms chunks
      mediaRecorderRef.current = mediaRecorder;
      setIsRecording(true);
      setStatusText("Listening…");
    } catch (err) {
      setStatusText("Microphone access denied");
    }
  }, [isConnected, isProcessing]);

  const stopRecording = useCallback(() => {
    if (!isRecording) return;
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current?.stream.getTracks().forEach((t) => t.stop());
    setIsRecording(false);
    setIsProcessing(true);
    setStatusText("Processing…");
    // Signal end of speech
    wsRef.current?.send(JSON.stringify({ type: "end_of_speech" }));
  }, [isRecording]);

  const sendInterrupt = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: "interrupt" }));
  }, []);

  async function playAudio(arrayBuffer: ArrayBuffer) {
    try {
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext();
      }
      const ctx = audioContextRef.current;
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0));
      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);
      source.start();
    } catch (e) {
      console.error("Audio playback error:", e);
    }
  }

  function addMessage(role: "user" | "agent", text: string, language?: Language) {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role, text, language, timestamp: new Date() },
    ]);
  }

  const latencyColor = (ms: number) =>
    ms < 450 ? "#22c55e" : ms < 600 ? "#f59e0b" : "#ef4444";

  return (
    <div style={styles.root}>
      {/* Header */}
      <header style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.logo}>🏥</span>
          <div>
            <div style={styles.title}>Voice AI Agent</div>
            <div style={styles.subtitle}>Clinical Appointment Booking</div>
          </div>
        </div>
        <div style={styles.langBadges}>
          {(Object.keys(LANG_LABELS) as Language[]).map((l) => (
            <span key={l} style={styles.langBadge}>{LANG_LABELS[l]}</span>
          ))}
        </div>
      </header>

      <div style={styles.body}>
        {/* Sidebar */}
        <aside style={styles.sidebar}>
          <div style={styles.sideSection}>
            <label style={styles.label}>Patient ID</label>
            <input
              style={styles.input}
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              disabled={isConnected}
              placeholder="pat-001"
            />
          </div>

          <button
            style={{
              ...styles.btn,
              background: isConnected ? "#ef4444" : "#6366f1",
            }}
            onClick={isConnected ? disconnect : connect}
          >
            {isConnected ? "⛔ Disconnect" : "🔌 Connect"}
          </button>

          {isConnected && (
            <button style={{ ...styles.btn, background: "#f59e0b" }} onClick={sendInterrupt}>
              ✋ Interrupt
            </button>
          )}

          {/* Status */}
          <div style={styles.statusBox}>
            <div style={{ ...styles.statusDot, background: isConnected ? "#22c55e" : "#6b7280" }} />
            <span style={styles.statusText}>{statusText}</span>
          </div>

          {/* Latency Panel */}
          {latency && (
            <div style={styles.latencyBox}>
              <div style={styles.latencyTitle}>⚡ Latency Breakdown</div>
              {[
                ["STT", latency.stt_ms],
                ["Language", latency.lang_ms],
                ["Agent", latency.agent_ms],
                ["TTS", latency.tts_ms],
              ].map(([label, ms]) => (
                <div key={label as string} style={styles.latencyRow}>
                  <span style={styles.latencyLabel}>{label as string}</span>
                  <span style={{ color: latencyColor(ms as number), fontWeight: 600 }}>
                    {ms as number}ms
                  </span>
                </div>
              ))}
              <div style={{ ...styles.latencyRow, borderTop: "1px solid #374151", paddingTop: 6, marginTop: 4 }}>
                <span style={{ fontWeight: 700 }}>Total</span>
                <span style={{ color: latencyColor(latency.total_ms), fontWeight: 700, fontSize: 15 }}>
                  {latency.total_ms}ms
                  {latency.within_budget ? " ✅" : " ⚠️"}
                </span>
              </div>
              <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 4 }}>
                Target: &lt;450ms
              </div>
            </div>
          )}

          {/* Language guide */}
          <div style={styles.langGuide}>
            <div style={styles.latencyTitle}>💬 Try saying:</div>
            <div style={styles.example}>"Book cardiologist tomorrow"</div>
            <div style={styles.example}>"मुझे कल डॉक्टर से मिलना है"</div>
            <div style={styles.example}>"நாளை சந்திப்பு வேண்டும்"</div>
          </div>
        </aside>

        {/* Chat Area */}
        <main style={styles.chat}>
          <div style={styles.messages}>
            {messages.length === 0 && (
              <div style={styles.emptyState}>
                <div style={{ fontSize: 48 }}>🎙️</div>
                <div>Connect and press the mic button to start a voice conversation</div>
              </div>
            )}
            {messages.map((m) => (
              <div
                key={m.id}
                style={{
                  ...styles.bubble,
                  alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                  background: m.role === "user" ? "#6366f1" : "#1f2937",
                  borderRadius: m.role === "user"
                    ? "18px 18px 4px 18px"
                    : "18px 18px 18px 4px",
                }}
              >
                <div style={styles.bubbleRole}>
                  {m.role === "user" ? "👤 You" : "🤖 Agent"}
                  {m.language && (
                    <span style={styles.bubbleLang}>{LANG_LABELS[m.language]}</span>
                  )}
                </div>
                <div style={styles.bubbleText}>{m.text}</div>
                <div style={styles.bubbleTime}>
                  {m.timestamp.toLocaleTimeString()}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Mic Button */}
          <div style={styles.micArea}>
            <button
              style={{
                ...styles.micBtn,
                background: isRecording
                  ? "#ef4444"
                  : isProcessing
                  ? "#f59e0b"
                  : isConnected
                  ? "#6366f1"
                  : "#374151",
                transform: isRecording ? "scale(1.15)" : "scale(1)",
                boxShadow: isRecording
                  ? "0 0 0 12px rgba(239,68,68,0.2), 0 0 0 24px rgba(239,68,68,0.1)"
                  : "0 4px 20px rgba(99,102,241,0.4)",
              }}
              onMouseDown={startRecording}
              onMouseUp={stopRecording}
              onTouchStart={(e) => { e.preventDefault(); startRecording(); }}
              onTouchEnd={(e) => { e.preventDefault(); stopRecording(); }}
              disabled={!isConnected || isProcessing}
            >
              {isRecording ? "🔴" : isProcessing ? "⏳" : "🎙️"}
            </button>
            <div style={styles.micHint}>
              {isRecording
                ? "Release to send"
                : isProcessing
                ? "Processing…"
                : isConnected
                ? "Press & hold to speak"
                : "Connect first"}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  root: {
    fontFamily: "'IBM Plex Sans', 'Segoe UI', sans-serif",
    background: "#0f172a",
    color: "#f1f5f9",
    minHeight: "100vh",
    display: "flex",
    flexDirection: "column",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "14px 24px",
    background: "#1e293b",
    borderBottom: "1px solid #334155",
  },
  headerLeft: { display: "flex", alignItems: "center", gap: 12 },
  logo: { fontSize: 28 },
  title: { fontWeight: 700, fontSize: 18, letterSpacing: "-0.3px" },
  subtitle: { fontSize: 12, color: "#94a3b8" },
  langBadges: { display: "flex", gap: 8 },
  langBadge: {
    padding: "3px 10px",
    background: "#334155",
    borderRadius: 20,
    fontSize: 12,
    color: "#cbd5e1",
  },
  body: {
    display: "flex",
    flex: 1,
    overflow: "hidden",
    height: "calc(100vh - 65px)",
  },
  sidebar: {
    width: 240,
    background: "#1e293b",
    borderRight: "1px solid #334155",
    padding: 16,
    display: "flex",
    flexDirection: "column",
    gap: 12,
    overflowY: "auto",
  },
  sideSection: { display: "flex", flexDirection: "column", gap: 4 },
  label: { fontSize: 11, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.5px" },
  input: {
    background: "#0f172a",
    border: "1px solid #334155",
    borderRadius: 8,
    color: "#f1f5f9",
    padding: "6px 10px",
    fontSize: 13,
    outline: "none",
  },
  btn: {
    border: "none",
    borderRadius: 10,
    color: "#fff",
    padding: "10px 0",
    fontWeight: 600,
    fontSize: 14,
    cursor: "pointer",
    transition: "opacity 0.15s",
  },
  statusBox: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    background: "#0f172a",
    borderRadius: 8,
    padding: "8px 10px",
  },
  statusDot: { width: 8, height: 8, borderRadius: "50%", flexShrink: 0 },
  statusText: { fontSize: 12, color: "#94a3b8" },
  latencyBox: {
    background: "#0f172a",
    borderRadius: 10,
    padding: 12,
    border: "1px solid #334155",
  },
  latencyTitle: { fontSize: 12, fontWeight: 700, color: "#94a3b8", marginBottom: 8 },
  latencyRow: {
    display: "flex",
    justifyContent: "space-between",
    fontSize: 13,
    padding: "2px 0",
  },
  latencyLabel: { color: "#cbd5e1" },
  langGuide: {
    background: "#0f172a",
    borderRadius: 10,
    padding: 12,
    border: "1px solid #334155",
  },
  example: { fontSize: 12, color: "#94a3b8", marginTop: 4, fontStyle: "italic" },
  chat: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  messages: {
    flex: 1,
    overflowY: "auto",
    padding: "20px 24px",
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  emptyState: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    flex: 1,
    color: "#475569",
    gap: 12,
    textAlign: "center",
    fontSize: 14,
    marginTop: "20vh",
  },
  bubble: {
    maxWidth: "70%",
    padding: "10px 14px",
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  bubbleRole: {
    fontSize: 11,
    color: "#94a3b8",
    display: "flex",
    alignItems: "center",
    gap: 6,
  },
  bubbleLang: {
    background: "#374151",
    borderRadius: 10,
    padding: "1px 6px",
    fontSize: 10,
    color: "#cbd5e1",
  },
  bubbleText: { fontSize: 14, lineHeight: 1.5 },
  bubbleTime: { fontSize: 10, color: "#6b7280", textAlign: "right" },
  micArea: {
    padding: "20px 0 28px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 10,
    borderTop: "1px solid #334155",
    background: "#1e293b",
  },
  micBtn: {
    width: 72,
    height: 72,
    borderRadius: "50%",
    border: "none",
    fontSize: 28,
    cursor: "pointer",
    transition: "all 0.15s cubic-bezier(0.34,1.56,0.64,1)",
    userSelect: "none",
  },
  micHint: { fontSize: 12, color: "#64748b" },
};
