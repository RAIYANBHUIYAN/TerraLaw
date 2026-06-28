export interface Message {
  sender: "user" | "assistant";
  text: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

export interface AskResponse {
  answer: string;
  mode: string;
  analysis?: {
    label?: string;
    confidence?: number;
  };
  sources_used?: Array<{
    act_name?: string;
    section?: string;
    score?: number;
  }>;
}

export interface SessionUser {
  user_id: string;
}
