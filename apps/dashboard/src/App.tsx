import { Navigate, Route, Routes } from "react-router-dom";
import { captureShareTokenFromUrl, isAuthed } from "./api";
import Layout from "./components/Layout";
import CalibrationPage from "./pages/CalibrationPage";
import EntityPage from "./pages/EntityPage";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import MarketPage from "./pages/MarketPage";
import SettingsPage from "./pages/SettingsPage";
import ShareHomePage from "./pages/ShareHomePage";
import ShareQueryPage from "./pages/ShareQueryPage";
import ShareSignalPage from "./pages/ShareSignalPage";
import SignalPage from "./pages/SignalPage";
import SystemPage from "./pages/SystemPage";
import PortfolioPage from "./pages/PortfolioPage";
import InvestorsPage from "./pages/InvestorsPage";
import ThemesPage from "./pages/ThemesPage";

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!isAuthed()) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  captureShareTokenFromUrl();
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/s/:id/:token" element={<ShareSignalPage />} />
      <Route path="/h/:token" element={<ShareHomePage />} />
      <Route path="/open" element={<ShareQueryPage />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route path="/" element={<Navigate to="/demand" replace />} />
        <Route path="/demand" element={<HomePage defaultTab="demand" />} />
        <Route path="/bulk" element={<HomePage defaultTab="bulk" />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/investors" element={<InvestorsPage />} />
        <Route path="/themes" element={<ThemesPage />} />
        <Route path="/signals/:id" element={<SignalPage />} />
        <Route path="/entities/:name" element={<EntityPage />} />
        <Route path="/markets/:market" element={<MarketPage />} />
        <Route path="/calibration" element={<CalibrationPage />} />
        <Route path="/system" element={<SystemPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
