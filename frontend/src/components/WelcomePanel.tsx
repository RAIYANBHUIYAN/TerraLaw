"use client";

import { greeting } from "@/lib/utils";

const PROMPTS = [
  {
    title: "Can a co-sharer claim pre-emption after a family land sale?",
    text: "My father sold part of our family land to an outsider without informing the other co-sharers. Can I claim pre-emption, and what documents would I need?",
  },
  {
    title: "How do I object to a government land acquisition notice?",
    text: "The government published a notice saying our land may be acquired for a public purpose. How can we object, within how many days, and before which authority?",
  },
];

export function WelcomePanel({
  userName,
  onPrompt,
}: {
  userName: string;
  onPrompt: (text: string) => void;
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-12">
      <div className="w-full max-w-2xl text-center">
        <div className="mb-4 text-4xl text-teal-600">⚖</div>
        <p className="text-sm text-[#6b7c75]">{greeting(userName)}</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-[#0f1714] md:text-4xl">
          Ask about Bangladeshi land law
        </h2>
        <p className="mx-auto mt-3 max-w-lg text-sm leading-relaxed text-[#6b7c75]">
          Statute-grounded answers on transfer, tenancy, acquisition, and tax.
        </p>
      </div>

      <div className="mt-10 w-full max-w-2xl space-y-3">
        {PROMPTS.map((prompt) => (
          <button
            key={prompt.title}
            type="button"
            onClick={() => onPrompt(prompt.text)}
            className="w-full rounded-2xl border border-[#99f6e4] bg-[#ecfdf5] px-5 py-4 text-left text-sm text-[#0f766e] transition hover:border-[#5eead4] hover:bg-[#d1fae5]"
          >
            {prompt.title}
          </button>
        ))}
      </div>
    </div>
  );
}
