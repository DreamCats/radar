import { FormEvent, useState } from "react";
import { LockKeyhole, LogIn, ShieldCheck } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";

type LoginPageProps = {
  error?: string | null;
  onLogin: (token: string) => Promise<void>;
};

export function LoginPage({ error, onLogin }: LoginPageProps) {
  const [token, setToken] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const shouldReduceMotion = useReducedMotion();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError(null);
    setSubmitting(true);
    try {
      await onLogin(token.trim());
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="login-page">
      <motion.div
        className="login-panel"
        initial={shouldReduceMotion ? false : { opacity: 0, y: 12 }}
        animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
        transition={{ duration: 0.28, ease: "easeOut" }}
      >
        <div className="login-mark">
          <ShieldCheck size={18} />
        </div>
        <div className="login-heading">
          <p className="eyebrow">Private Workspace</p>
          <h1>radar</h1>
          <p>输入访问密钥</p>
        </div>
        <form className="login-form" onSubmit={submit}>
          <label className="login-field">
            <span>密钥</span>
            <div className="login-password">
              <LockKeyhole size={15} />
              <input
                autoComplete="current-password"
                autoFocus
                type="password"
                value={token}
                onChange={(event) => setToken(event.target.value)}
              />
            </div>
          </label>
          {(localError || error) && <p className="login-error">{localError || error}</p>}
          <button className="primary-button login-submit" type="submit" disabled={submitting}>
            <LogIn size={15} />
            {submitting ? "校验中" : "进入"}
          </button>
        </form>
      </motion.div>
    </section>
  );
}
