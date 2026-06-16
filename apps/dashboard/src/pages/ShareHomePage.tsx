import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

/** WhatsApp-friendly home link: /h/{token} */
export default function ShareHomePage() {
  const { token } = useParams();
  const navigate = useNavigate();

  useEffect(() => {
    if (token) sessionStorage.setItem("share_token", token);
    navigate("/demand", { replace: true });
  }, [token, navigate]);

  return <p>Opening dashboard…</p>;
}
