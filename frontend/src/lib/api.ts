import type { AskResponse, Conversation } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = "Request failed";
    try {
      const payload = await response.json();
      detail = payload.detail ?? detail;
    } catch {
      detail = response.statusText || detail;
    }
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }

  return response.json() as Promise<T>;
}

export async function registerUser(userId: string, password: string) {
  return request<{ user_id: string }>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, password }),
  });
}

export async function loginUser(userId: string, password: string) {
  return request<{ user_id: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, password }),
  });
}

export async function fetchConversations(userId: string) {
  const data = await request<{ conversations: Conversation[] }>(
    `/api/conversations?user_id=${encodeURIComponent(userId)}`,
  );
  return data.conversations;
}

export async function createConversation(userId: string, title = "New chat") {
  return request<Conversation>("/api/conversations", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, title }),
  });
}

export async function fetchConversation(userId: string, conversationId: string) {
  return request<Conversation>(
    `/api/conversations/${conversationId}?user_id=${encodeURIComponent(userId)}`,
  );
}

export async function saveMessage(
  userId: string,
  conversationId: string,
  sender: "user" | "assistant",
  text: string,
) {
  return request<Conversation>(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId, sender, text }),
  });
}

export async function askQuestion(question: string) {
  return request<AskResponse>(
    `/ask?question=${encodeURIComponent(question)}`,
  );
}

export function adminDashboardUrl() {
  return `${API_URL}/admin/dashboard`;
}
