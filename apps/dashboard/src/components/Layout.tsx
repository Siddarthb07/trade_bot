import { Link, NavLink, Outlet } from "react-router-dom";

const MAIN = [
  { to: "/demand", label: "Demand picks" },
  { to: "/bulk", label: "Bulk deals" },
  { to: "/portfolio", label: "Portfolio" },
  { to: "/investors", label: "Investors" },
  { to: "/themes", label: "Themes" },
];

const MORE = [
  { to: "/markets/in", label: "India" },
  { to: "/markets/us", label: "US" },
  { to: "/calibration", label: "Calibration" },
  { to: "/system", label: "System" },
  { to: "/settings", label: "Settings" },
];

export default function Layout() {
  return (
    <div className="app">
      <header className="header">
        <div className="header-brand">
          <strong>Trade Bot</strong>
          <span className="subtitle">Not investment advice</span>
        </div>
        <nav className="header-nav">
          {MAIN.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? "active" : "")}>
              {item.label}
            </NavLink>
          ))}
          <div className="nav-more">
            <span>More ▾</span>
            <div className="nav-dropdown">
              {MORE.map((item) => (
                <Link key={item.to} to={item.to}>{item.label}</Link>
              ))}
            </div>
          </div>
        </nav>
      </header>
      <main className="main"><Outlet /></main>
      <footer className="footer">Historical win rates are not calibrated probabilities until the Platt scorer ships.</footer>
    </div>
  );
}
