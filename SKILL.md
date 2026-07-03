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

## 2. Configure (write `dashboard.conf` — do NOT edit the code)

**Preferred:** create a `dashboard.conf` next to `explorer.py` (copy
`dashboard.conf.example`) with the user's settings — `KEY=value`, one per line. It
overrides the in-code defaults and keeps settings out of the code so future updates
(`git pull`) never clobber them. Only edit the CONFIG block in `explorer.py` if the
user explicitly prefers that.

Settings (same names work in `dashboard.conf`, as env vars, or in the CONFIG block):

- **`PROM_ADDRESS`** — the user's `prom1…` payout address (required for the "Your Miner" panels).
  - No address yet? Get one: `curl -O https://promethium.work/downloads/prom-keygen.py && python3 prom-keygen.py` (**back up the key**).
- **`PROM_ADDRESSES`** — optional list of extra addresses to aggregate.
- **`MRR_KEY` / `MRR_SECRET`** — optional MiningRigRentals API key → shows rented-rig hashrate. View-only is fine; it does **not** need withdraw.
- **`MINER_LOG`** — optional path to a local cpuminer/ccminer log → home CPU/GPU hashrate.
- **`NODE_RPC`** (+ `NODE_COOKIE` or `NODE_RPC_USER`/`NODE_RPC_PASS`) — optional; point at the user's **own** local `promd` RPC to light up the **Your Node** panel (sync status, peer count, mempool, version, per-country peer rollup). Privacy: the panel shows counts only — **it never displays or stores a peer IP**. `NODE_GEO=False` skips the country lookup entirely.
- **`HOST`** — leave `127.0.0.1` for local-only, or set `0.0.0.0` to reach it from other devices on the LAN.

Ask the user for their address first. Never ask for or store private keys.

**Updating later:** `git pull` (or re-`curl` the single file), then restart. The
user's `dashboard.conf` is untouched, so no settings are lost.

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
