---
name: promethium-dashboard
description: Install and run the Promethium ($PROM) community mining dashboard — a local web explorer showing live network stats, the user's balance, earnings, hashrate, blocks won, the top block winners, and an all-time miner leaderboard. Works for pool, solo, rented-rig, or home CPU/GPU miners. Then act as a mining co-pilot — watch the data, surface alerts, explain the metrics, and guide setup. Use when a user wants to monitor or understand their Promethium mining.
---

# Promethium Dashboard — install, run & co-pilot

A local, single-file dashboard for the Promethium ($PROM) network. It reads the
public Promethium explorer API and renders network stats, the user's mining
position, a recent-blocks feed, the top block winners, and a miner leaderboard.
**Python standard library only — nothing to `pip install`.**

This skill installs it, wires it to the user's address, launches it, and then
stays on as a mining co-pilot. It complements the official mining skills
(`pool-skill.md`, `node-skill.md`) — those *set up* mining; this one *monitors* it.

## 1. Get the dashboard

```bash
# from the repo:
git clone https://github.com/devpyle/promethium-dashboard && cd promethium-dashboard
# or grab the single file:
curl -O https://raw.githubusercontent.com/devpyle/promethium-dashboard/main/explorer.py
```

## 2. Configure (edit the CONFIG block at the top of `explorer.py`)

- **`PROM_ADDRESS`** — the user's `prom1…` payout address (required for the "Your Miner" panels).
  - No address yet? Get one: `curl -O https://promethium.work/downloads/prom-keygen.py && python3 prom-keygen.py` (**back up the key**).
- **`PROM_ADDRESSES`** — optional list of extra addresses to aggregate.
- **`MRR_KEY` / `MRR_SECRET`** — optional MiningRigRentals API key → shows rented-rig hashrate. View-only is fine; it does **not** need withdraw.
- **`MINER_LOG`** — optional path to a local cpuminer/ccminer log → home CPU/GPU hashrate.
- **`HOST`** — leave `127.0.0.1` for local-only, or set `0.0.0.0` to reach it from other devices on the LAN.

Ask the user for their address before editing. Never ask for or store private keys.

## 3. Run

```bash
python3 explorer.py         # then open http://localhost:8899
```

Confirm it's up (the terminal prints the URL). Offer to open the browser.

## 4. Co-pilot — stay engaged after launch

Poll `http://localhost:8899/api/data` and help the user proactively:

- **Alerts:** a rented rig near expiry (`status` shows `Nh left`); average block time drifting (retarget incoming); the user being out-hashed on the winners board; win-efficiency dropping below ~0.8× (losing block races → node/latency issue).
- **Explain on request:** *win efficiency* (block-share ÷ hashrate-share — <1 means losing races), *block time vs difficulty*, *PPLNS vs solo*, *"am I better pooled or solo?"*.
- **Guide setup:** shared pool `stratum.promethium.work:3337` (PPLNS, 0% fee, steady) vs solo `:3335` (keep your own blocks, high variance). Point to the official docs rather than reinventing steps.

**Guardrail:** advise and explain freely, but **never spend money** (e.g. renting rigs via an MRR key) or move funds without explicit, per-action user confirmation.

## Related official resources (link the user to these — don't duplicate)

- Shared pool: https://promethium.work/docs/mining-pool · skill: https://promethium.work/downloads/pool-skill.md
- Run a node: https://promethium.work/docs/run-a-node · skill: https://promethium.work/downloads/node-skill.md
- Miner tool: https://promethium.work/downloads/prom-miner.py · Keygen: https://promethium.work/downloads/prom-keygen.py
- Agentic mining overview: https://promethium.work/docs/agentic-mining

---
*Community tool — not affiliated with the Promethium project. MIT licensed.*
