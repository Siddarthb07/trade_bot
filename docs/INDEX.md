# Trade Bot — Documentation Index

Local path: `C:\Users\siddu\Projects\trade_bot`  
GitHub: [Siddarthb07/trade_bot](https://github.com/Siddarthb07/trade_bot)

---

## Start here


| Document                                               | Description                                                    |
| ------------------------------------------------------ | -------------------------------------------------------------- |
| [TRADE_BOT_DEEP_DIVE.md](./TRADE_BOT_DEEP_DIVE.md)     | Full architecture, data flow, services, ML, alerts, deployment |
| [LLM_COUNCIL_RATING.md](./LLM_COUNCIL_RATING.md)       | V1 council review — **6.9/10 (B+)**                            |
| [LLM_COUNCIL_RATING_V2.md](./LLM_COUNCIL_RATING_V2.md) | V2 council (portfolio + investor UX) — **7.2/10 (A−)**         |


---

## Product & automation


| Document                                               | Description                                                     |
| ------------------------------------------------------ | --------------------------------------------------------------- |
| [TRADE_AUTOMATION_PLAN.md](./TRADE_AUTOMATION_PLAN.md) | Dashboard → broker execution roadmap (paper → live → semi-auto) |


---

## Operations & deployment


| Document                           | Description                                                        |
| ---------------------------------- | ------------------------------------------------------------------ |
| [HTTPS_SETUP.md](./HTTPS_SETUP.md) | Tailscale, Cloudflare Tunnel, sslip.io for tappable WhatsApp links |


---

## Related project (Anima)


| Document                                   | Description                                               |
| ------------------------------------------ | --------------------------------------------------------- |
| [ANIMA_DEEP_DIVE.md](./ANIMA_DEEP_DIVE.md) | Anima LLM readout stack — separate repo, research tooling |


Anima repo: [Siddarthb07/Anima](https://github.com/Siddarthb07/Anima)

---

## Quick reference


| Item      | Value                                             |
| --------- | ------------------------------------------------- |
| Dashboard | `http://192.168.1.42` or `:3000`                  |
| Login     | `admin` / `changeme` (change in production)       |
| New pages | **Portfolio**, **Investors** (nav bar)            |
| Migration | `docker compose run --rm migrate` (002 portfolio) |
| Stack     | `docker compose up -d`                            |


---

*Last updated: 2026-07-01*
