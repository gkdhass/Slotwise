import { Shell } from "../components/Shell";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import { useState } from "react";

export default function S01Auth() {
  const [mode, setMode] = useState<"signin" | "register">("signin");
  return (
    <Shell title={mode === "signin" ? "Sign in" : "Create your account"} subtitle="Slotwise — account access">
      <form className="flex flex-col gap-4" onSubmit={(e) => e.preventDefault()}>
        <Input label="Email" type="email" placeholder="you@example.test" />
        <Input label="Password" type="password" placeholder="••••••••" />
        {mode === "register" && <Input label="Display name" placeholder="Your name" />}
        <Button type="submit">{mode === "signin" ? "Sign in" : "Create account"}</Button>
        <button
          type="button"
          className="text-small text-accent underline"
          onClick={() => setMode(mode === "signin" ? "register" : "signin")}
        >
          {mode === "signin" ? "Need an account? Register" : "Already have an account? Sign in"}
        </button>
      </form>
    </Shell>
  );
}