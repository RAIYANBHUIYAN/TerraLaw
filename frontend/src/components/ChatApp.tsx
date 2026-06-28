"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ChatBubble, TypingIndicator } from "@/components/ChatBubble";
import { WelcomePanel } from "@/components/WelcomePanel";
import {
  adminDashboardUrl,
  askQuestion,
  createConversation,
  fetchConversation,
  fetchConversations,
  saveMessage,
} from "@/lib/api";
import { clearSession, getSession } from "@/lib/session";
import type { Conversation, Message } from "@/lib/types";

export function ChatApp() {
  const router = useRouter();
  const [userId, setUserId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState("");

  const activeConversation = useMemo(
    () => conversations.find((item) => item.id === activeId) ?? null,
    [conversations, activeId],
  );

  const loadConversations = useCallback(async (uid: string, preferredId?: string) => {
    const items = await fetchConversations(uid);
    setConversations(items);
    const nextId = preferredId ?? items[0]?.id ?? null;
    setActiveId(nextId);
    if (nextId) {
      const conversation = await fetchConversation(uid, nextId);
      setMessages(conversation.messages);
    } else {
      setMessages([]);
    }
  }, []);

  useEffect(() => {
    const session = getSession();
    if (!session) {
      router.replace("/login");
      return;
    }
    setUserId(session.user_id);
    loadConversations(session.user_id).catch(() =>
      setError("Could not load conversations."),
    );
  }, [router, loadConversations]);

  async function handleNewChat() {
    if (!userId) return;
    setError("");
    const conversation = await createConversation(userId);
    await loadConversations(userId, conversation.id);
  }

  async function handleSelectConversation(id: string) {
    if (!userId) return;
    setActiveId(id);
    const conversation = await fetchConversation(userId, id);
    setMessages(conversation.messages);
  }

  async function handleSend(event?: FormEvent, preset?: string) {
    event?.preventDefault();
    const text = (preset ?? input).trim();
    if (!text || !userId || thinking) return;

    let conversationId = activeId;
    if (!conversationId) {
      const created = await createConversation(userId);
      conversationId = created.id;
      setActiveId(conversationId);
    }

    setInput("");
    setError("");
    setThinking(true);

    const userMessage: Message = {
      sender: "user",
      text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);

    try {
      await saveMessage(userId, conversationId, "user", text);
      const response = await askQuestion(text);
      const assistantMessage: Message = {
        sender: "assistant",
        text: response.answer,
        created_at: new Date().toISOString(),
      };
      await saveMessage(userId, conversationId, "assistant", response.answer);
      setMessages((prev) => [...prev, assistantMessage]);
      await loadConversations(userId, conversationId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setThinking(false);
    }
  }

  function handleLogout() {
    clearSession();
    router.push("/login");
  }

  if (!userId) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white text-sm text-[#6b7c75]">
        Loading...
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-[#eef1ef]">
      <aside className="flex w-72 shrink-0 flex-col bg-[#101816] text-[#8fa39a]">
        <div className="border-b border-white/5 px-6 py-6">
          <h1 className="text-lg font-semibold text-[#ecf3ef]">TerraLaw</h1>
          <p className="mt-1 text-xs">Bangladesh land law</p>
        </div>

        <div className="p-4">
          <button
            type="button"
            onClick={handleNewChat}
            className="w-full rounded-xl bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-teal-700"
          >
            + New chat
          </button>
        </div>

        <div className="px-5 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em]">
          Recent
        </div>

        <div className="flex-1 space-y-1 overflow-y-auto px-3 pb-4">
          {conversations.map((conversation) => (
            <button
              key={conversation.id}
              type="button"
              onClick={() => handleSelectConversation(conversation.id)}
              className={`w-full rounded-xl px-3 py-2.5 text-left text-sm transition ${
                conversation.id === activeId
                  ? "bg-[#243330] text-[#ecf3ef]"
                  : "text-[#8fa39a] hover:bg-[#1c2825] hover:text-[#ecf3ef]"
              }`}
            >
              <span className="line-clamp-2">{conversation.title}</span>
            </button>
          ))}
        </div>

        <div className="border-t border-white/5 p-4">
          <p className="mb-3 truncate text-xs">{userId}</p>
          <div className="flex gap-2">
            <a
              href={adminDashboardUrl()}
              target="_blank"
              rel="noreferrer"
              className="flex-1 rounded-lg bg-[#182220] px-3 py-2 text-center text-xs text-[#ecf3ef] transition hover:bg-[#243330]"
            >
              Admin
            </a>
            <button
              type="button"
              onClick={handleLogout}
              className="flex-1 rounded-lg bg-[#182220] px-3 py-2 text-xs text-[#ecf3ef] transition hover:bg-[#243330]"
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col bg-white">
        <header className="flex items-center justify-between border-b border-[#dde5e1] px-6 py-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-[#6b7c75]">
              AI legal assistant
            </p>
            <h2 className="text-sm font-medium text-[#0f1714]">
              {activeConversation?.title ?? "New chat"}
            </h2>
          </div>
          <span className="rounded-full bg-[#ecfdf5] px-3 py-1 text-xs font-medium text-teal-700">
            ● Online
          </span>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8">
          {messages.length === 0 && !thinking ? (
            <WelcomePanel userName={userId} onPrompt={(text) => handleSend(undefined, text)} />
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-4">
              {messages.map((message, index) => (
                <ChatBubble key={`${message.created_at}-${index}`} message={message} />
              ))}
              {thinking && <TypingIndicator />}
            </div>
          )}
        </div>

        <div className="border-t border-[#dde5e1] px-4 py-4 md:px-8">
          {error && (
            <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
              {error}
            </p>
          )}
          <form
            onSubmit={(event) => handleSend(event)}
            className="mx-auto flex max-w-3xl items-center gap-3 rounded-2xl border border-[#dde5e1] bg-[#f8faf9] px-4 py-2"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask a land law question..."
              className="flex-1 bg-transparent px-2 py-3 text-sm text-[#0f1714] outline-none placeholder:text-[#94a8a0]"
              disabled={thinking}
            />
            <button
              type="submit"
              disabled={thinking || !input.trim()}
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-600 text-lg font-semibold text-white transition hover:bg-teal-700 disabled:opacity-50"
              aria-label="Send message"
            >
              ↑
            </button>
          </form>
          <p className="mx-auto mt-3 max-w-3xl text-center text-[11px] text-[#6b7c75]">
            Informational only — not legal advice. Verify with official records and counsel.
          </p>
        </div>
      </main>
    </div>
  );
}
