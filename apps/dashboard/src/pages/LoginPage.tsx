import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch, setAuth } from "../api";

export default function LoginPage() {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("changeme");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setAuth(username, password);
    try {
      await apiFetch("/health");
      navigate("/");
    } catch {
      setError("Login failed");
      sessionStorage.removeItem("auth");
    }
  }

  return (
    <div className="card login">
      <h2>Login</h2>
      <form onSubmit={onSubmit}>
        <label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {error && <p className="error">{error}</p>}
        <button type="submit">Sign in</button>
      </form>
    </div>
  );
}
