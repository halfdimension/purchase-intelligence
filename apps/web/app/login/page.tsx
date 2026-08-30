"use client";

import {
  Suspense,
  type FormEvent,
  useState,
} from "react";
import {
  useRouter,
  useSearchParams,
} from "next/navigation";

type AuthMode =
  | "login"
  | "signup";

type AuthResponse = {
  authenticated?: boolean;
  emailConfirmationRequired?: boolean;
  error?: string;
};

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [ignoreQueryError, setIgnoreQueryError] =
    useState(false);

  const [mode, setMode] =
    useState<AuthMode>("login");

  const [email, setEmail] =
    useState("");

  const [password, setPassword] =
    useState("");

  const [error, setError] =
    useState("");

  const [message, setMessage] =
    useState("");

  const [submitting, setSubmitting] =
    useState(false);

  function switchMode(
    nextMode: AuthMode,
  ) {
    setMode(nextMode);
    setError("");
    setMessage("");
    setIgnoreQueryError(true);
  }

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    setError("");
    setMessage("");
    setIgnoreQueryError(true);

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

      const endpoint =
        mode === "login"
          ? "/api/auth/login"
          : "/api/auth/signup";

      const response = await fetch(
        endpoint,
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
          ?? (
            mode === "login"
              ? "Unable to sign in."
              : "Unable to create account."
          ),
        );
      }

      if (data.authenticated) {
        router.replace("/");
        return;
      }

      if (
        mode === "signup"
        && data.emailConfirmationRequired
      ) {
        setPassword("");

        setMessage(
          "Account created. Check your email "
          + "and confirm your address before "
          + "signing in.",
        );

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

  const isLogin =
    mode === "login";

  const confirmationError =
    !ignoreQueryError
    && searchParams.get("error")
      === "confirmation_failed"
      ? (
        "Email confirmation failed or "
        + "the link has expired."
      )
      : "";

  const displayedError =
    error || confirmationError;

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
              {isLogin
                ? "Welcome back"
                : "Create your account"}
            </h1>

            <p
              className="
                mt-3
                text-sm
                leading-6
                text-zinc-400
              "
            >
              {isLogin
                ? (
                  "Sign in to manage your "
                  + "tracked products."
                )
                : (
                  "Create an account to build "
                  + "your personal watchlist."
                )}
            </p>
          </div>

          <div
            className="
              mb-7
              grid
              grid-cols-2
              rounded-xl
              bg-zinc-950
              p-1
            "
          >
            <button
              type="button"
              onClick={() =>
                switchMode("login")
              }
              className={`
                rounded-lg
                px-4
                py-2.5
                text-sm
                font-medium
                transition
                ${
                  isLogin
                    ? (
                      "bg-zinc-800 "
                      + "text-white"
                    )
                    : (
                      "text-zinc-500 "
                      + "hover:text-zinc-300"
                    )
                }
              `}
            >
              Sign in
            </button>

            <button
              type="button"
              onClick={() =>
                switchMode("signup")
              }
              className={`
                rounded-lg
                px-4
                py-2.5
                text-sm
                font-medium
                transition
                ${
                  !isLogin
                    ? (
                      "bg-zinc-800 "
                      + "text-white"
                    )
                    : (
                      "text-zinc-500 "
                      + "hover:text-zinc-300"
                    )
                }
              `}
            >
              Create account
            </button>
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
                autoComplete={
                  isLogin
                    ? "current-password"
                    : "new-password"
                }
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

            {displayedError && (
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
                {displayedError}
              </div>
            )}

            {message && (
              <div
                className="
                  rounded-xl
                  border
                  border-emerald-950
                  bg-emerald-950/30
                  px-4
                  py-3
                  text-sm
                  leading-5
                  text-emerald-300
                "
              >
                {message}
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
                ? (
                  isLogin
                    ? "Signing in..."
                    : "Creating account..."
                )
                : (
                  isLogin
                    ? "Sign in"
                    : "Create account"
                )}
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
