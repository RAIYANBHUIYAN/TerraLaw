import type { Message } from "@/lib/types";
import { formatTime } from "@/lib/utils";

export function ChatBubble({ message }: { message: Message }) {
  const isUser = message.sender === "user";

  return (
    <div className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed md:max-w-[70%] ${
          isUser
            ? "bg-teal-600 text-white"
            : "border border-[#dde5e1] bg-[#f4f7f6] text-[#1a2421]"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.text}</p>
      </div>
      <span className="mt-1 px-1 text-[11px] text-[#6b7c75]">
        {formatTime(message.created_at)}
      </span>
    </div>
  );
}

export function TypingIndicator() {
  return (
    <div className="flex items-start">
      <div className="rounded-2xl border border-[#dde5e1] bg-[#f4f7f6] px-4 py-3 text-sm text-[#6b7c75]">
        Thinking...
      </div>
    </div>
  );
}
