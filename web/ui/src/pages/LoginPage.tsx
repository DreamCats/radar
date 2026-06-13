import { FormEvent, useState } from "react";
import { LockKeyhole, LogIn, ShieldCheck } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";

type LoginPageProps = {
  error?: string | null;
  onLogin: (username: string, password: string) => Promise<void>;
};

export function LoginPage({ error, onLogin }: LoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const shouldReduceMotion = useReducedMotion();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError(null);
    setSubmitting(true);
    try {
      await onLogin(username.trim(), password);
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
          <p>个人投研工作台</p>
        </div>
        <form className="login-form" onSubmit={submit}>
          <label className="login-field">
            <span>账号</span>
            <input
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </label>
          <label className="login-field">
            <span>密码</span>
            <div className="login-password">
              <LockKeyhole size={15} />
              <input
                autoComplete="current-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
          </label>
          {(localError || error) && <p className="login-error">{localError || error}</p>}
          <button className="primary-button login-submit" type="submit" disabled={submitting}>
            <LogIn size={15} />
            {submitting ? "登录中" : "登录"}
          </button>
        </form>
      </motion.div>
    </section>
  );
}
