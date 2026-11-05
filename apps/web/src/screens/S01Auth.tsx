import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import { ApiError, login, register } from "../lib/api";

export default function S01Auth() {
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      if (mode === "register") {
        await register(email, password);
        setMode("signin");
        setNotice("Account created. Check your email to verify it, then sign in.");
      } else {
        await login(email, password);
        navigate("/app");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.userMessage : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Shell title={mode === "signin" ? "Sign in" : "Create your account"} subtitle="Slotwise — account access">
      <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        {error && <Alert variant="error">{error}</Alert>}
        {notice && <Alert variant="success">{notice}</Alert>}
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Input
          label="Password"
          type="password"
          autoComplete={mode === "signin" ? "current-password" : "new-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" loading={loading}>
          {mode === "signin" ? "Sign in" : "Create account"}
        </Button>
        <button
          type="button"
          className="text-small text-accent underline"
          onClick={() => {
            setMode(mode === "signin" ? "register" : "signin");
            setError(null);
            setNotice(null);
          }}
        >
          {mode === "signin" ? "Need an account? Register" : "Already have an account? Sign in"}
        </button>
      </form>
    </Shell>
  );
}
