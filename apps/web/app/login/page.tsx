"use client";

import {
  Suspense,
  type FormEvent,
  useState,
} from "react";
import { useRouter } from "next/navigation";

type AuthResponse = {
  authenticated?: boolean;
  error?: string;
};

function LoginPageContent() {
  const router = useRouter();

  const [email, setEmail] =
    useState("");

  const [password, setPassword] =
    useState("");

  const [error, setError] =
    useState("");

  const [submitting, setSubmitting] =
    useState(false);

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    setError("");

    const normalizedEmail =
      email.trim().toLowerCase();

    if (!normalizedEmail) {
      setError("Email is required.");
      return;
    }

    if (!password) {
      setError("Password is required.");
      return;
    }

    try {
      setSubmitting(true);

      const response = await fetch(
        "/api/auth/login",
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json",
          },
          body: JSON.stringify({
            email: normalizedEmail,
            password,
          }),
        },
      );

      const data: AuthResponse =
        await response.json();

      if (!response.ok) {
        throw new Error(
          data.error
          ?? "Unable to sign in.",
        );
      }

      if (data.authenticated) {
        router.replace("/");
        return;
      }

      throw new Error(
        "Authentication completed in an "
        + "unexpected state.",
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Authentication failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main
      className="
        min-h-screen
        bg-zinc-950
        px-6
        py-16
        text-zinc-100
      "
    >
      <div
        className="
          mx-auto
          flex
          min-h-[calc(100vh-8rem)]
          max-w-md
          items-center
        "
      >
        <section
          className="
            w-full
            rounded-3xl
            border
            border-zinc-800
            bg-zinc-900/70
            p-8
            shadow-2xl
            shadow-black/30
            backdrop-blur
          "
        >
          <div className="mb-8">
            <p
              className="
                mb-3
                text-sm
                font-medium
                uppercase
                tracking-[0.22em]
                text-zinc-500
              "
            >
              Purchase Intelligence
            </p>

            <h1
              className="
                text-3xl
                font-semibold
                tracking-tight
              "
            >
              Welcome back
            </h1>

            <p
              className="
                mt-3
                text-sm
                leading-6
                text-zinc-400
              "
            >
              Sign in to manage your tracked
              products.
            </p>
          </div>

          <form
            onSubmit={handleSubmit}
            className="space-y-5"
          >
            <label
              className="
                block
                space-y-2
                text-sm
                font-medium
                text-zinc-300
              "
            >
              <span>Email</span>

              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) =>
                  setEmail(
                    event.target.value,
                  )
                }
                placeholder="you@example.com"
                className="
                  w-full
                  rounded-xl
                  border
                  border-zinc-800
                  bg-zinc-950
                  px-4
                  py-3
                  text-zinc-100
                  outline-none
                  transition
                  placeholder:text-zinc-600
                  focus:border-zinc-600
                "
              />
            </label>

            <label
              className="
                block
                space-y-2
                text-sm
                font-medium
                text-zinc-300
              "
            >
              <span>Password</span>

              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) =>
                  setPassword(
                    event.target.value,
                  )
                }
                className="
                  w-full
                  rounded-xl
                  border
                  border-zinc-800
                  bg-zinc-950
                  px-4
                  py-3
                  text-zinc-100
                  outline-none
                  transition
                  focus:border-zinc-600
                "
              />
            </label>

            {error && (
              <div
                role="alert"
                className="
                  rounded-xl
                  border
                  border-red-950
                  bg-red-950/30
                  px-4
                  py-3
                  text-sm
                  leading-5
                  text-red-300
                "
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="
                w-full
                rounded-xl
                bg-zinc-100
                px-4
                py-3
                text-sm
                font-semibold
                text-zinc-950
                transition
                hover:bg-white
                disabled:cursor-not-allowed
                disabled:opacity-50
              "
            >
              {submitting
                ? "Signing in..."
                : "Sign in"}
            </button>
          </form>

          <p
            className="
              mt-7
              text-center
              text-xs
              leading-5
              text-zinc-600
            "
          >
            Authentication is handled by
            Supabase. Your password is not
            stored by Purchase Intelligence.
          </p>
        </section>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-zinc-950" />
      }
    >
      <LoginPageContent />
    </Suspense>
  );
}
