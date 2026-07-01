# AGENTS.md — Promethium Dashboard

Instructions for a coding agent (Codex, Claude Code, etc.) working in this repo.
This mirrors `SKILL.md`; either file is enough to install, run, and co-pilot the
Promethium ($PROM) community mining dashboard.

## What this repo is

`explorer.py` — a single-file, standard-library-only web dashboard that reads the
public Promethium explorer API and shows: network stats (height, hashrate,
difficulty, block time, halving), the user's mining position (balance, earn rate,
hashrate, blocks won, win efficiency), a recent-blocks feed, the top block
winners, and an all-time miner leaderboard. No `pip install`, no account.

## Setup task (do this when asked to "set up / run the Promethium dashboard")

1. **Check Python 3** is available (`python3 --version`).
2. **Get the user's `prom1…` address.** If they don't have one, point them to
   `https://promethium.work/downloads/prom-keygen.py` (they run it; it prints an
   address and saves a key they must back up). Never ask for or handle private keys.
3. **Edit the CONFIG block** at the top of `explorer.py`:
   - `PROM_ADDRESS` (required) and optionally `PROM_ADDRESSES` (aggregate several).
   - Optional `MRR_KEY`/`MRR_SECRET` (rented-rig hashrate, view-only) and
     `MINER_LOG` (path to a local miner log for home CPU/GPU hashrate).
   - `HOST=0.0.0.0` only if the user wants LAN access.
4. **Run** `python3 explorer.py` and confirm `http://localhost:8899` serves.
5. Offer to open the browser.

## Co-pilot task (stay engaged after launch)

Poll `http://localhost:8899/api/data` (JSON). Proactively surface:
- rented rig near expiry, block-time drift (retarget incoming), the user being
  out-hashed on the winners board, or win efficiency < ~0.8× (losing races).
Explain metrics on request (win efficiency, block time, PPLNS vs solo). Guide
pool (`stratum.promethium.work:3337`) vs solo (`:3335`) setup via the official docs.

**Hard rule:** never spend money or move funds (e.g. renting rigs with an MRR key)
without explicit, per-action confirmation from the user.

## Endpoints exposed by the running dashboard

- `GET /` — the HTML dashboard
- `GET /api/data` — full JSON state (network + user + tables)
- `GET /api/lookup?q=<prom1address|blockheight>` — explorer search

## Official resources (link, don't duplicate)

Pool: /docs/mining-pool + /downloads/pool-skill.md · Node: /docs/run-a-node +
/downloads/node-skill.md · Miner: /downloads/prom-miner.py · Keygen:
/downloads/prom-keygen.py · Agentic mining: /docs/agentic-mining
(all under https://promethium.work).
