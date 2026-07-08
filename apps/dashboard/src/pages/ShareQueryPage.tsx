import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

/** Fallback when WhatsApp strips path: http://host/?s={id}&k={token} */
export default function ShareQueryPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const k = params.get("k");
    const s = params.get("s");
    if (k) sessionStorage.setItem("share_token", k);
    if (s) {
      navigate(`/signals/${s}`, { replace: true });
      return;
    }
    navigate("/share", { replace: true });
  }, [params, navigate]);

  return <p>Opening…</p>;
}
