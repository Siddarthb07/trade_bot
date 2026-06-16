import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

/** WhatsApp-friendly path link: /s/{signalId}/{token} */
export default function ShareSignalPage() {
  const { id, token } = useParams();
  const navigate = useNavigate();

  useEffect(() => {
    if (token) sessionStorage.setItem("share_token", token);
    if (id) navigate(`/signals/${id}`, { replace: true });
  }, [id, token, navigate]);

  return <p>Opening signal…</p>;
}
