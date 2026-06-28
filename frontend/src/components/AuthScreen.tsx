"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { loginUser, registerUser } from "@/lib/api";
import { setSession } from "@/lib/session";

type Mode = "login" | "register";

export function AuthScreen({ mode }: { mode: Mode }) {
  const router = useRouter();
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (mode === "register") {
        if (password !== confirm) {
          throw new Error("Passwords do not match.");
        }
        await registerUser(userId.trim(), password);
        await loginUser(userId.trim(), password);
      } else {
        await loginUser(userId.trim(), password);
      }
      setSession({ user_id: userId.trim() });
      router.push("/chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#eef1ef] px-4">
      <div className="w-full max-w-md overflow-hidden rounded-2xl border border-[#dde5e1] bg-white shadow-[0_20px_60px_rgba(13,148,136,0.08)]">
        <div className="h-1 bg-teal-600" />
        <div className="px-8 py-10">
          <div className="mb-8 text-center">
            <div className="mb-3 text-3xl">⚖</div>
            <h1 className="text-2xl font-semibold tracking-tight text-[#0f1714]">
              TerraLaw
            </h1>
            <p className="mt-2 text-sm text-[#6b7c75]">
              {mode === "login"
                ? "Sign in to continue"
                : "Create an account to save your chats"}
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4">
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[#6b7c75]">
                User ID
              </span>
              <input
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                className="w-full rounded-xl border border-[#dde5e1] bg-[#f8faf9] px-4 py-3 text-sm text-[#0f1714] outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
                autoComplete="username"
                required
              />
            </label>

            <label className="block">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[#6b7c75]">
                Password
              </span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-xl border border-[#dde5e1] bg-[#f8faf9] px-4 py-3 text-sm text-[#0f1714] outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                required
              />
            </label>

            {mode === "register" && (
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[#6b7c75]">
                  Confirm password
                </span>
                <input
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="w-full rounded-xl border border-[#dde5e1] bg-[#f8faf9] px-4 py-3 text-sm text-[#0f1714] outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
                  autoComplete="new-password"
                  required
                />
              </label>
            )}

            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-teal-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-teal-700 disabled:opacity-60"
            >
              {loading
                ? "Please wait..."
                : mode === "login"
                  ? "Sign in"
                  : "Create account"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-[#6b7c75]">
            {mode === "login" ? (
              <>
                New here?{" "}
                <Link href="/register" className="font-medium text-teal-700 hover:underline">
                  Create account
                </Link>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <Link href="/login" className="font-medium text-teal-700 hover:underline">
                  Sign in
                </Link>
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
