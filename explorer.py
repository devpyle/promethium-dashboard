#!/usr/bin/env python3
r"""
PROMETHIUM — Community Mining Dashboard  (Windows / macOS / Linux)
=================================================================
An easy, local explorer for the Promethium ($PROM) network. Shows live network
stats (height, hashrate, difficulty, block time, halving), YOUR miner (balance,
earn rate, hashrate, blocks won, win efficiency), your hardware, a recent-blocks
feed, the top block winners, and an all-time miner leaderboard — for anyone
mining in the shared pool, solo, on rented rigs, or on a home CPU/GPU.

Reads the public Promethium explorer API. No account, no packages — Python
standard library only. Optional: MRR or NiceHash API keys (rented hashrate) or a
local miner log path (home CPU/GPU hashrate).

----------------------------------  QUICK START  ----------------------------------
1. Install Python 3:  https://www.python.org/downloads/  (Windows: tick "Add to PATH")
2. Edit the CONFIG block below — set your prom1 address.  (MRR key / log are optional.)
3. Run:            python explorer.py
4. Open:           http://localhost:8899
Leave the terminal open while you use it; Ctrl+C to stop.

Don't have an address?  ->  https://promethium.work/downloads/prom-keygen.py
Want to start mining?   ->  https://promethium.work/docs/mining-pool
-----------------------------------------------------------------------------------
MIT licensed. Not affiliated with the Promethium project — a community tool.
"""
import hmac, hashlib, time, json, threading, urllib.request, urllib.parse, collections, re, uuid, base64, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ============================ CONFIG — EDIT THESE ============================
PROM_ADDRESS   = "prom1qxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"   # <-- your prom1... payout address
PROM_ADDRESSES = []          # optional: list ALL your addresses to aggregate, e.g. ["prom1q...a","prom1q...b"]
MRR_KEY        = ""          # optional: MiningRigRentals API key  -> shows rented-rig hashrate
MRR_SECRET     = ""          # optional: MiningRigRentals API secret
NICEHASH_ORG   = ""          # optional: NiceHash Organization ID -> shows NiceHash-rented hashrate
NICEHASH_KEY   = ""          # optional: NiceHash API key code
NICEHASH_SECRET= ""          # optional: NiceHash API secret
MINER_LOG      = ""          # optional: full path to a local cpuminer/ccminer log -> home CPU/GPU hashrate
PORT           = 8899        # dashboard served at http://localhost:PORT
HOST           = "127.0.0.1" # set "0.0.0.0" to reach it from other devices on your LAN
WINDOW         = 50          # recent blocks scanned for the block-winners board / your share
POOL_WALLETS   = ["prom1qspqnn7eyu5symh7ykqg29r97rf40nqhh8cerdj"]   # shared-pool coinbase — flagged with a globe in winners/recent blocks
# --- Optional: run your own node? point the dashboard at its local RPC to light up the "Your Node" panel ---
NODE_RPC       = ""          # optional: local promd RPC, e.g. "http://127.0.0.1:18132"  (empty = hide the Your Node panel)
NODE_COOKIE    = ""          # path to your node's .cookie file, e.g. "~/.prom/.cookie"  (easiest auth)
NODE_RPC_USER  = ""          # OR set rpcuser / rpcpassword instead of a cookie
NODE_RPC_PASS  = ""
NODE_GEO       = True        # roll your peers up into a COUNTRY count (via ip-api.com). No IPs are ever shown or stored. Set False to skip the geo call entirely.
# ===========================================================================
# Prefer NOT editing the block above. Instead drop a `dashboard.conf` next to this file
# (copy dashboard.conf.example) with just the settings you want — it OVERRIDES the defaults
# above, and lives outside the code so `git pull` / re-downloading never wipes your config.
# Environment variables of the same name win over dashboard.conf. See README "Updating".

_CFG_KEYS = ["PROM_ADDRESS", "PROM_ADDRESSES", "MRR_KEY", "MRR_SECRET", "NICEHASH_ORG",
             "NICEHASH_KEY", "NICEHASH_SECRET", "MINER_LOG", "PORT", "HOST", "WINDOW",
             "NODE_RPC", "NODE_COOKIE", "NODE_RPC_USER", "NODE_RPC_PASS", "NODE_GEO"]
def _cast(cur, val):
    if isinstance(cur, bool): return str(val).strip().lower() in ("1", "true", "yes", "on")
    if isinstance(cur, int):  return int(str(val).strip())
    if isinstance(cur, list): return [x.strip() for x in str(val).replace(",", " ").split() if x.strip()]
    return str(val).strip()
def _load_overrides():
    import os
    g = globals(); src = {}
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, "dashboard.conf"), os.path.join(os.getcwd(), "dashboard.conf")):
        try:
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line: continue
                k, v = line.split("=", 1); k = k.strip()
                if k in _CFG_KEYS: src[k] = v.strip().strip('"').strip("'")
        except FileNotFoundError: pass
        except Exception as e: print("!! dashboard.conf parse error:", e)
    for k in _CFG_KEYS:                                   # env vars win over the file
        if os.environ.get(k): src[k] = os.environ[k]
    for k, v in src.items():
        try: g[k] = _cast(g[k], v)
        except Exception as e: print(f"!! bad value for {k}={v!r} ({e})")
    if src: print(f"config: loaded {len(src)} setting(s) from dashboard.conf / env")
_load_overrides()

EXP = "https://promethium.work/api/explorer"
POOL_API = "https://promethium.work/api/pool"
MRR = "https://www.miningrigrentals.com/api/v2"
NH  = "https://api2.nicehash.com"
UA  = {"User-Agent": "prom-dashboard"}
MULT = {"hash":1,"kh":1e3,"mh":1e6,"gh":1e9,"th":1e12,"ph":1e15}
SUPPLY_CAP = 21_000_000      # Bitcoin-fork default; edit if the project's cap differs
HALVING_INTERVAL = 210_000
RETARGET_INTERVAL = 2016     # difficulty retargets every 2016 blocks (confirmed on-chain)
TARGET_SPACING    = 600      # 10-minute target block time
POOL_HOST = "stratum.promethium.work"; POOL_PORT = 3337; SOLO_PORT = 3335

HAVE_MRR = bool(MRR_KEY and MRR_SECRET and "xxxx" not in MRR_KEY)
HAVE_NH  = bool(NICEHASH_ORG and NICEHASH_KEY and NICEHASH_SECRET)
HAVE_NODE = bool(NODE_RPC)
MY = set([PROM_ADDRESS] + [a for a in PROM_ADDRESSES if a]) - {""}
MY = {a for a in MY if "xxxx" not in a}

def jget(url, headers=None, timeout=15):
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers=headers or UA)
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except Exception as e:
            last = e; time.sleep(0.4)
    raise last

def mrr(path):
    sig = path.split('?')[0]                       # MRR signs the PATH ONLY
    n = str(int(time.time()*1000))
    s = hmac.new(MRR_SECRET.encode(), (MRR_KEY+n+sig).encode(), hashlib.sha1).hexdigest()
    h = {"x-api-key": MRR_KEY, "x-api-nonce": n, "x-api-sign": s, "User-Agent": "d"}
    return jget(MRR+path, headers=h, timeout=15)

def nicehash(path, query=""):
    """NiceHash API v2 GET. Signs with HMAC-SHA256 over null-separated fields."""
    t = str(int(time.time()*1000)); n = str(uuid.uuid4())
    msg = "\x00".join([NICEHASH_KEY, t, n, "", NICEHASH_ORG, "", "GET", path, query])
    sig = hmac.new(NICEHASH_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
    h = {"X-Time": t, "X-Nonce": n, "X-Organization-Id": NICEHASH_ORG,
         "X-Request-Id": str(uuid.uuid4()), "X-Auth": NICEHASH_KEY+":"+sig, "Accept": "application/json"}
    return jget(NH+path+("?"+query if query else ""), headers=h, timeout=15)

def miner_log_hps():
    if not MINER_LOG: return 0.0
    try:
        txt = open(MINER_LOG, "r", errors="ignore").read()[-20000:]
        m = re.findall(r'([0-9.]+)\s*(kH|MH|GH|TH)/s', txt, re.I)
        if not m: return 0.0
        v, u = m[-1]; return float(v) * MULT.get(u.lower(), 1)
    except Exception:
        return 0.0

# caches
block_info = collections.OrderedDict()     # height -> {"miner","reward","time"}
bal_hist   = collections.deque(maxlen=400) # (ts, balance)
_rich = [None, 0.0]

def richlist():
    now = time.time()
    if _rich[0] is not None and now-_rich[1] < 300: return _rich[0]
    try: _rich[0] = jget(f"{EXP}/richlist?count=100"); _rich[1] = now
    except Exception:
        if _rich[0] is None: _rich[0] = {"top": [], "holders": 0, "totalMined": 0}
    return _rich[0]

_pool = [None, 0.0]
def pool_wide():
    now = time.time()
    if _pool[0] is not None and now-_pool[1] < 30: return _pool[0]
    try: _pool[0] = jget(POOL_API); _pool[1] = now
    except Exception:
        if _pool[0] is None: _pool[0] = {}
    return _pool[0]

_pm = [None, 0.0]
def pool_me_agg():
    """Aggregate this user's pool pending/paid/hashrate across all their addresses (cached ~30s)."""
    now = time.time()
    if _pm[0] is not None and now-_pm[1] < 30: return _pm[0]
    pm = {"found": False, "pending": 0.0, "paid": 0.0, "earned": 0.0, "hps": 0.0}
    for a in MY:
        try:
            m = jget(f"{POOL_API}/miner/{a}")
            if m.get("found"):
                pm["found"] = True
                pm["pending"] += float(m.get("pending", 0)); pm["paid"] += float(m.get("paid", 0))
                pm["earned"]  += float(m.get("earned", 0));  pm["hps"]  += float(m.get("hashrate", 0))
        except Exception: pass
    _pm[0] = pm; _pm[1] = now; return pm

# ---- Your Node (optional): reads YOUR OWN local promd via RPC. Privacy: only aggregate
#      counts and a per-COUNTRY peer rollup ever leave this function — never any peer IP. ----
def _rpc_auth():
    if NODE_RPC_USER:
        return NODE_RPC_USER + ":" + NODE_RPC_PASS
    if NODE_COOKIE:
        return open(os.path.expanduser(NODE_COOKIE)).read().strip()
    return None

def rpc(method, params=None):
    auth = _rpc_auth()
    if auth is None: raise RuntimeError("no NODE_COOKIE or NODE_RPC_USER set")
    body = json.dumps({"jsonrpc": "1.0", "id": "dash", "method": method, "params": params or []}).encode()
    req = urllib.request.Request(NODE_RPC, data=body, headers={
        "Content-Type": "text/plain",
        "Authorization": "Basic " + base64.b64encode(auth.encode()).decode()})
    r = json.load(urllib.request.urlopen(req, timeout=8))
    if r.get("error"): raise RuntimeError(r["error"])
    return r["result"]

_geo = {}                      # ip -> countryCode  (cached across ticks; no IPs are ever emitted)
def geo_countries(ips):
    """Return {countryCode: count} for a list of peer IPs. IPs are used only to look up a
    country and are never returned/stored beyond this in-memory cache. Best-effort; skips on failure."""
    want = [ip for ip in ips if ip and ip not in _geo and ":" not in ip.split("%")[0][:4]
            and not ip.startswith(("10.", "192.168.", "127.", "172.", "fd", "fe80"))]
    for i in range(0, len(want), 100):
        chunk = want[i:i+100]
        try:
            req = urllib.request.Request("http://ip-api.com/batch?fields=countryCode,query",
                data=json.dumps([{"query": ip} for ip in chunk]).encode(),
                headers={"Content-Type": "application/json"})
            for row in json.load(urllib.request.urlopen(req, timeout=8)):
                if row.get("query"): _geo[row["query"]] = row.get("countryCode") or "?"
        except Exception:
            break
    cc = collections.Counter()
    for ip in ips:
        c = _geo.get(ip)
        if c: cc[c] += 1
    return dict(cc)

_node = [None, 0.0]
def node_stats(net_tip):
    """Snapshot of the operator's OWN node: sync state + peer counts + country rollup. Cached ~20s."""
    now = time.time()
    if _node[0] is not None and now-_node[1] < 20: return _node[0]
    try:
        bc = rpc("getblockchaininfo"); ni = rpc("getnetworkinfo")
        blocks = int(bc.get("blocks", 0)); headers = int(bc.get("headers", blocks))
        vp = float(bc.get("verificationprogress", 0))
        behind = max((net_tip or headers) - blocks, headers - blocks, 0)
        synced = behind <= 1 and vp >= 0.9999
        cin = ni.get("connections_in"); cout = ni.get("connections_out")
        countries = {}
        if cin is None or cout is None or NODE_GEO:
            peers = rpc("getpeerinfo")
            if cin is None:  cin  = sum(1 for p in peers if p.get("inbound"))
            if cout is None: cout = sum(1 for p in peers if not p.get("inbound"))
            if NODE_GEO:
                ips = [str(p.get("addr", "")).rsplit(":", 1)[0].strip("[]") for p in peers]
                countries = geo_countries(ips)
        mp = 0
        try: mp = int(rpc("getmempoolinfo").get("size", 0))
        except Exception: pass
        top = sorted(countries.items(), key=lambda x: -x[1])
        node = {"ok": True, "blocks": blocks, "headers": headers, "behind": behind,
                "synced": synced, "vp": round(vp*100, 2), "chain": bc.get("chain", ""),
                "peers": int(ni.get("connections", (cin or 0)+(cout or 0))),
                "cin": cin or 0, "cout": cout or 0, "mempool": mp,
                "subver": (ni.get("subversion") or "").strip("/"),
                "countries": [{"cc": c, "n": n} for c, n in top]}
    except Exception as e:
        node = {"ok": False, "err": str(e)[:80]}
    _node[0] = node; _node[1] = now; return node

def block_at(h):
    if h in block_info: return block_info[h]
    try:
        b = jget(f"{EXP}/block/{h}")
        block_info[h] = {"miner": b.get("miner"), "reward": b.get("reward", 50), "time": b.get("time", 0)}
    except Exception:
        block_info[h] = {"miner": None, "reward": 50, "time": 0}
    while len(block_info) > 400: block_info.popitem(last=False)
    return block_info[h]

_pstart = {}                                        # period-start-height -> timestamp (one fetch per 2-week period)
def retarget_info(tip, diff, avgbt, recent_bt=None):
    """Blocks until the next difficulty retarget, plus an estimate of where difficulty
    will land — the ACTUAL time mined so far this period plus the remaining blocks
    projected at the current (recent) pace, so a hashrate change moves the estimate.
    Bitcoin rule: new_diff = old_diff * target_timespan / actual_timespan, clamped [0.25x,4x]."""
    period_start = (tip // RETARGET_INTERVAL) * RETARGET_INTERVAL
    next_h = period_start + RETARGET_INTERVAL
    blocks_left = next_h - tip
    done = tip - period_start
    pace = recent_bt if (recent_bt and recent_bt > 0) else (avgbt or TARGET_SPACING)   # projected s/block for remaining blocks
    info = {"interval": RETARGET_INTERVAL, "next_height": next_h, "blocks_left": blocks_left,
            "progress": round(100 * done / RETARGET_INTERVAL, 1),
            "eta_sec": round(blocks_left * pace), "est": None}
    try:
        if period_start not in _pstart:
            _pstart[period_start] = block_at(period_start).get("time") or 0
            for k in list(_pstart)[:-4]: _pstart.pop(k, None)   # keep only recent periods
        t0 = _pstart[period_start]; t1 = block_at(tip).get("time") or 0
        if t0 and t1 > t0 and done > 0:
            proj_span = (t1 - t0) + blocks_left * pace          # elapsed-so-far + remaining at current pace
            ratio = max(0.25, min(4.0, (RETARGET_INTERVAL * TARGET_SPACING) / proj_span))
            info["est"] = {"pct": round((ratio - 1) * 100), "mult": round(ratio, 2),
                           "dir": "harder" if ratio > 1.01 else ("easier" if ratio < 0.99 else "no change"),
                           "diff": round(diff * ratio)}
    except Exception:
        pass
    return info

STATE = {"ready": False}

def update_loop():
    global STATE
    while True:
        try:
            chain = jget(f"{EXP}/chain")
            tip   = int(chain["height"]); diff = chain["difficulty"]
            nethps = float(chain["networkHashps"]); avgbt = float(chain.get("avgBlockTime") or 0)
            if not avgbt:                        # API doesn't always return avgBlockTime — derive it
                lat = chain.get("latest") or []
                if len(lat) >= 2:
                    dt = (lat[0].get("time", 0) or 0) - (lat[-1].get("time", 0) or 0)
                    dh = (lat[0].get("height", 0) or 0) - (lat[-1].get("height", 0) or 0)
                    if dh > 0 and dt > 0: avgbt = dt / dh
                if not avgbt and nethps:          # last resort: theoretical from difficulty + hashrate
                    avgbt = float(diff) * 4294967296.0 / nethps
            reward = 50 >> (tip // HALVING_INTERVAL)

            lo = tip - WINDOW + 1
            for h in range(lo, tip+1): block_at(h)          # fill/refresh window
            # network-hashrate trend: rolling 6-block hashrate across the window (sparkline)
            def _hps(nb):
                a = block_info.get(tip); b = block_info.get(tip-nb)
                if a and b and (a.get("time") or 0) > (b.get("time") or 0):
                    return round(float(diff)*4294967296.0*nb/(a["time"]-b["time"])/1e15, 2)
                return 0
            _sw = 6; hps_series = []; bt_series = []
            for _h in range(lo+_sw, tip+1):
                _a = block_info.get(_h); _b = block_info.get(_h-_sw)
                if _a and _b and (_a.get("time") or 0) > (_b.get("time") or 0):
                    _dt = _a["time"] - _b["time"]
                    hps_series.append(round(float(diff)*4294967296.0*_sw/_dt/1e15, 3))
                    bt_series.append(round(_dt/_sw, 1))          # rolling-6 avg block interval (s)
            # recent block time: avg interval over the last _RN blocks — reflects current
            # conditions (a stall/hashrate drop shows here, unlike the 24h avgBlockTime)
            _RN = 12
            _ra = block_info.get(tip); _rb = block_info.get(tip-_RN)
            recent_bt = round((_ra["time"] - _rb["time"]) / _RN, 1) if (_ra and _rb and (_ra.get("time") or 0) > (_rb.get("time") or 0)) else None
            win = {h: block_info.get(h, {}).get("miner") for h in range(lo, tip+1)}
            cnt = collections.Counter(m for m in win.values() if m)
            total = sum(cnt.values()) or 1
            mine  = sum(cnt.get(a, 0) for a in MY)
            # collapse all of the user's own addresses into ONE "YOU" row
            merged = [(a, n) for a, n in cnt.items() if a not in MY]
            if mine: merged.append(("__YOU__", mine))
            merged.sort(key=lambda x: -x[1])
            winners = [{"addr": ("YOU" if a == "__YOU__" else a), "n": n,
                        "pct": round(100*n/total, 1), "you": a == "__YOU__", "pool": a in POOL_WALLETS}
                       for a, n in merged[:10]]

            # recent-blocks feed (last 8, newest first)
            feed = []
            for h in range(tip, max(lo, tip-8)-1, -1):
                bi = block_info.get(h, {})
                feed.append({"h": h, "miner": bi.get("miner"), "reward": bi.get("reward", reward),
                             "ago": max(0, int(time.time()) - int(bi.get("time") or 0)),
                             "you": bi.get("miner") in MY, "pool": bi.get("miner") in POOL_WALLETS})

            # your miner
            bal = 0.0; blocks_total = 0
            for a in MY:
                try:
                    r = jget(f"{EXP}/address/{a}?window=1")
                    bal += float(r.get("balance", 0)); blocks_total += int(r.get("utxos", 0))
                except Exception: pass
            now = time.time(); bal_hist.append((now, bal))
            rate = 0.0
            for ts, b in bal_hist:
                if now-ts <= 1800 and now-ts > 60:
                    rate = (bal-b)/((now-ts)/3600.0); break

            # hashrate sources (optional): rented rigs (MRR) + local log
            your_hps = miner_log_hps(); rigs = []
            if HAVE_MRR:
                try:
                    for r in mrr("/rental").get("data", {}).get("rentals", []):
                        rg = r["rig"]; h5 = mrr(f"/rig/{rg['id']}").get("data", {}).get("hashrate", {}).get("last_5min", {})
                        hps = float(h5.get("hash", 0)) * MULT.get(h5.get("type", "hash"), 1); your_hps += hps
                        rigs.append({"name": rg.get("name"), "src": "MRR", "hps": h5.get("nice", "0"),
                                     "where": rg.get("region", "?"),
                                     "status": f"{round((int(r.get('end_unix',0))-now)/3600,1)}h left"})
                except Exception as e:
                    rigs.append({"name": "(MRR error — check API key)", "src": "", "hps": "", "where": str(e)[:24], "status": ""})
            if MINER_LOG:
                rigs.append({"name": "local miner (log)", "src": "Local", "hps": nice_hps(miner_log_hps()),
                             "where": "home", "status": "online" if miner_log_hps() else "idle"})
            if HAVE_NH:
                try:
                    orders = nicehash("/main/api/v2/hashpower/myOrders",
                                      "algorithm=SHA256&active=true&limit=100").get("list", [])
                    for o in orders:
                        spd = float(o.get("acceptedCurrentSpeed", 0)) * 1e15   # NiceHash SHA-256 orders are quoted in PH/s
                        your_hps += spd
                        rigs.append({"name": f"NiceHash #{str(o.get('id',''))[:8]}", "src": "NiceHash",
                                     "hps": nice_hps(spd), "where": o.get("market", "NH"),
                                     "status": "active" if o.get("alive", True) else "ended"})
                except Exception as e:
                    rigs.append({"name": "(NiceHash error — check API key)", "src": "", "hps": "",
                                 "where": str(e)[:24], "status": ""})

            # shared-pool payouts + pool-measured hashrate (cached ~30s to spare the pool API)
            pstats = pool_wide(); pm = pool_me_agg()
            _pp = pstats.get("pool", {}) or {}
            _bw = int(_pp.get("blocks_won", 0) or 0); _bo = int(_pp.get("blocks_orphaned", 0) or 0)
            pool_top = [{"addr": e.get("address"), "paid": round(float(e.get("paid", 0) or 0), 2),
                         "pending": round(float(e.get("pending", 0) or 0), 2),
                         "you": e.get("address") in MY, "pool": e.get("address") in POOL_WALLETS}
                        for e in (pstats.get("top") or []) if e.get("address")][:25]
            your_hps += pm["hps"]

            net_pct   = 100*your_hps/nethps if nethps else 0
            share_pct = 100*mine/total
            win_eff   = (share_pct/net_pct) if net_pct else 0

            rl = richlist(); mined = float(rl.get("totalMined", 0) or 0)
            leaders = [{"rank": e.get("rank"), "addr": e.get("address"), "bal": float(e.get("balance", 0)),
                        "pct": e.get("pct", 0), "you": e.get("address") in MY,
                        "pool": e.get("address") in POOL_WALLETS}
                       for e in rl.get("top", [])][:100]
            # shared-pool wallet balance (from the rich list if it's in top-100, else fetched directly)
            pool_wallet = {"addr": POOL_WALLETS[0] if POOL_WALLETS else "", "balance": 0.0, "rank": None}
            if POOL_WALLETS:
                pw = next((e for e in rl.get("top", []) if e.get("address") == POOL_WALLETS[0]), None)
                if pw:
                    pool_wallet.update(balance=float(pw.get("balance", 0)), rank=pw.get("rank"))
                else:
                    try:
                        r = jget(f"{EXP}/address/{urllib.parse.quote(POOL_WALLETS[0])}?window=1")
                        pool_wallet["balance"] = float(r.get("balance", 0))
                    except Exception: pass

            halving_blocks = HALVING_INTERVAL - (tip % HALVING_INTERVAL)
            halving_days   = round(halving_blocks*avgbt/86400, 1) if avgbt else 0

            node = node_stats(tip) if HAVE_NODE else None

            STATE = {"ready": True, "ts": now, "have_mrr": HAVE_MRR, "have_hps": bool(your_hps),
                "node": node,
                "n_wallets": len(MY), "configured": bool(MY),
                # network
                "tip": tip, "diff": diff, "nethps_ph": round(nethps/1e15, 2), "nethps_th": round(nethps/1e12, 0),
                "hps_series": hps_series, "hps_10": _hps(10), "hps_120": round(nethps/1e15, 2),
                "bt_series": bt_series,
                "blocktime": round(avgbt, 1), "blocktime_recent": recent_bt, "bt_n": _RN,
                "reward": reward, "blocks24h": round(86400/avgbt) if avgbt else 0,
                "retarget": retarget_info(tip, diff, avgbt, recent_bt),
                "mined": round(mined), "cap": SUPPLY_CAP, "mined_pct": round(100*mined/SUPPLY_CAP, 1),
                "halving_days": halving_days, "holders": rl.get("holders", 0),
                # you
                "balance": round(bal, 2), "blocks_total": blocks_total, "rate": round(rate),
                "your_hps": nice_hps(your_hps), "net_pct": round(net_pct, 2),
                "share_pct": round(share_pct, 1), "win_eff": round(win_eff, 2),
                "mine_window": mine, "window_total": total,
                # tables
                "rigs": rigs, "feed": feed, "winners": winners, "leaders": leaders,
                "pool_me": {"found": pm["found"], "pending": round(pm["pending"], 2),
                            "paid": round(pm["paid"], 2), "earned": round(pm["earned"], 2), "hps": nice_hps(pm["hps"])},
                "pool": {"lp_ts": (_pp.get("last_payout") or {}).get("ts", 0),
                         "lp_total": (_pp.get("last_payout") or {}).get("total", 0),
                         "lp_recips": (_pp.get("last_payout") or {}).get("recipients", 0),
                         "hps": round(float(_pp.get("hashrate", 0) or 0)/1e15, 2),
                         "miners": _pp.get("miners", 0), "active": _pp.get("active_miners", 0),
                         "blocks_won": _bw, "blocks_mature": int(_pp.get("blocks_mature", 0) or 0),
                         "blocks_immature": int(_pp.get("blocks_immature", 0) or 0), "blocks_orphaned": _bo,
                         "orphan_rate": round(100*_bo/(_bw+_bo), 1) if (_bw+_bo) else 0,
                         "avg_bt": round(float(_pp.get("avg_block_time", 0) or 0), 1),
                         "wallet_balance": round(float(_pp.get("wallet_balance", 0) or 0)),
                         "total_paid": round(float(_pp.get("total_paid", 0) or 0)),
                         "total_pending": round(float(_pp.get("total_pending", 0) or 0))},
                "pool_top": pool_top,
                "pool_wallet": pool_wallet,
                "pool_host": POOL_HOST, "pool_port": POOL_PORT, "solo_port": SOLO_PORT}
        except Exception as e:
            if STATE.get("ready"): STATE = {**STATE, "stale": True, "error": str(e)}
            else: STATE = {"ready": False, "error": str(e)}
        time.sleep(8)

def nice_hps(hps):
    if not hps: return "0"
    for u, m in (("PH",1e15),("TH",1e12),("GH",1e9),("MH",1e6),("kH",1e3)):
        if hps >= m: return f"{hps/m:.2f} {u}/s"
    return f"{hps:.0f} H/s"

def lookup(q):
    q = (q or "").strip()
    if not q: return {"error": "empty"}
    if q.isdigit():
        try:
            b = jget(f"{EXP}/block/{q}")
            return {"type": "block", "height": b.get("height"), "miner": b.get("miner"),
                    "reward": b.get("reward"), "time": b.get("time"), "txCount": b.get("txCount"),
                    "hash": b.get("hash")}
        except Exception as e: return {"error": f"block not found ({e})"}
    if q.startswith("prom1"):
        try:
            r = jget(f"{EXP}/address/{urllib.parse.quote(q)}?window={WINDOW}")
            return {"type": "address", "addr": q, "balance": r.get("balance"),
                    "utxos": r.get("utxos"), "minedCount": r.get("minedCount")}
        except Exception as e: return {"error": f"address not found ({e})"}
    return {"error": "enter a prom1… address or a block height"}

HTML = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Promethium — Community Explorer</title>
<style>
:root{--bg:#0a2bd6;--bg2:#0a27bd;--panel:#0921a8;--line:rgba(188,212,255,.22);--line2:rgba(188,212,255,.40);
--ink:#fff;--title:#bcd4ff;--light:#a9c6ff;--dim:#8fa9e8;--faint:#6f8ce6;--cyan:#00f0ff;--red:#f87171;--pos:#6ef2c0}
*{box-sizing:border-box;margin:0;padding:0}html,body{background:var(--bg)}
body{color:var(--ink);font:13px/1.5 ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-variant-numeric:tabular-nums;
padding:22px;max-width:1220px;margin:0 auto;position:relative;-webkit-font-smoothing:antialiased}
body::after{content:"";position:fixed;inset:0;pointer-events:none;z-index:9999;
background:repeating-linear-gradient(0deg,transparent 0 2px,rgba(0,240,255,.035) 2px 3px)}
.up{text-transform:uppercase;letter-spacing:1.4px}
header{display:flex;align-items:center;gap:13px;margin-bottom:20px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:16px}
.mark{width:40px;height:40px;background:var(--title);color:var(--bg);display:grid;place-items:center;font-size:21px;font-weight:800;flex-shrink:0}
.brand h1{font-size:17px;font-weight:800;letter-spacing:2px}.brand .tag{font-size:11px;color:var(--light);letter-spacing:2px;text-transform:uppercase;margin-top:2px}
.live{margin-left:auto;display:flex;align-items:center;gap:8px;font-size:11px;color:var(--light);border:1px solid var(--line);padding:6px 12px;text-transform:uppercase;letter-spacing:1px}
.dot{width:7px;height:7px;background:var(--cyan);box-shadow:0 0 8px var(--cyan);animation:pulse 1.8s infinite}@keyframes pulse{50%{opacity:.35}}
.sec{display:flex;align-items:center;gap:10px;margin:22px 1px 11px;cursor:pointer;user-select:none}.sec .t{font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--light)}
.chev{color:var(--faint);font-size:9px;width:11px;flex-shrink:0;transition:color .15s}.sec:hover .chev,.tbl .hd:hover .chev{color:var(--cyan)}
.sec .ln{flex:1;height:1px;background:var(--line)}.sec .pill{font-size:10px;color:var(--faint);border:1px solid var(--line);padding:2px 9px;text-transform:uppercase;letter-spacing:1px}
.grid{display:grid;gap:10px}.g4{grid-template-columns:repeat(4,1fr)}.g6{grid-template-columns:repeat(6,1fr)}.g2{grid-template-columns:2fr 1fr}
.card{background:var(--panel);border:1px solid var(--line);padding:14px 15px;position:relative}
.card.hot{border-color:var(--line2)}.card.hot::before{content:"";position:absolute;inset:0 0 auto 0;height:2px;background:var(--cyan);opacity:.8;box-shadow:0 0 8px var(--cyan)}
.k{font-size:10px;font-weight:600;letter-spacing:1.2px;text-transform:uppercase;color:var(--light)}
.v{font-size:25px;font-weight:800;margin-top:7px;letter-spacing:-.3px;color:#fff}.v small{font-size:12px;font-weight:600;color:var(--light)}.v.cy{color:var(--cyan)}
.s{font-size:11px;color:var(--dim);margin-top:4px}.pos{color:var(--pos)}.red{color:var(--red)}.cy{color:var(--cyan)}.lt{color:var(--light)}
.bar{height:6px;background:rgba(0,0,0,.25);overflow:hidden;margin-top:9px;border:1px solid var(--line)}.bar>i{display:block;height:100%;background:var(--cyan);box-shadow:0 0 6px var(--cyan)}
.addrbar{display:flex;gap:9px;align-items:center;background:var(--panel);border:1px solid var(--line2);padding:9px 10px 9px 13px;margin-bottom:11px}
.addrbar .lup{color:var(--faint);text-transform:uppercase;font-size:10px;letter-spacing:1px}
.addrbar input{flex:1;background:transparent;border:0;color:#fff;font:13px ui-monospace,monospace;outline:none}
.addrbar .btn{background:var(--title);color:var(--bg);font-weight:700;font-size:11px;border:0;padding:8px 16px;cursor:pointer;text-transform:uppercase;letter-spacing:1px}
.addrbar .btn:hover{background:#a9c6ff}
.modes{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:11px}
.chip{font-size:10px;color:var(--light);border:1px solid var(--line);padding:4px 11px;text-transform:uppercase;letter-spacing:1px}.chip.on{color:var(--bg);background:var(--title);border-color:transparent;font-weight:700}
.tbl{background:var(--panel);border:1px solid var(--line)}
.tbl .hd{padding:12px 15px;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--line);cursor:pointer;user-select:none}.tbl .hd .k{font-size:11px}.tbl .hd .r{margin-left:auto;font-size:10px;color:var(--faint);text-transform:uppercase;letter-spacing:1px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{text-align:left;color:var(--faint);font-weight:600;font-size:10px;letter-spacing:.8px;text-transform:uppercase;padding:9px 15px;background:var(--bg2)}
td{padding:9px 15px;border-top:1px solid var(--line);vertical-align:middle;color:#eef3ff}tr:hover td{background:rgba(188,212,255,.05)}
.you td{background:rgba(0,240,255,.10)!important;color:var(--cyan);font-weight:700}.you td:first-child{box-shadow:inset 3px 0 0 var(--cyan)}
.rank{color:var(--faint);font-weight:700;width:32px}.medal{font-size:14px}
.pg{display:flex;align-items:center;gap:7px;font-size:11px;color:var(--light);letter-spacing:.5px}
.pg button{background:var(--bg2);border:1px solid var(--line);color:var(--light);cursor:pointer;padding:2px 9px;font-family:inherit;font-size:10px;text-transform:uppercase;letter-spacing:.5px}
.pg button:hover:not(:disabled){background:var(--title);color:var(--bg)}
.pg button:disabled{opacity:.35;cursor:default}
.mbar{display:inline-block;width:64px;height:6px;background:rgba(0,0,0,.25);overflow:hidden;vertical-align:middle;margin-left:8px;border:1px solid var(--line)}.mbar>i{display:block;height:100%;background:var(--cyan);box-shadow:0 0 5px var(--cyan)}
.flag{font-size:10px;padding:1px 7px;background:rgba(0,0,0,.2);border:1px solid var(--line);color:var(--light);text-transform:uppercase}
.tag2{font-size:9.5px;padding:1px 7px;background:rgba(188,212,255,.14);color:var(--title);text-transform:uppercase}.tag2.gpu{background:rgba(0,240,255,.14);color:var(--cyan)}
.feed .row{display:flex;align-items:center;gap:10px;padding:8px 15px;border-top:1px solid var(--line);font-size:12px}
.feed .h{color:var(--cyan);font-weight:700;width:66px}.feed .w{color:#dfe8ff;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.feed .rw{color:var(--light)}.feed .tm{color:var(--faint);width:52px;text-align:right}
.getmine{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.gm{background:var(--panel);border:1px solid var(--line);padding:14px}
.gm h3{font-size:12px;margin-bottom:8px;text-transform:uppercase;letter-spacing:1px;color:var(--title)}
.gm p{font-size:11px;color:var(--dim);margin-bottom:9px}.gm a{color:var(--cyan);text-decoration:none}.gm a:hover{text-decoration:underline}
.gm code{display:block;background:rgba(0,0,0,.28);border:1px solid var(--line);padding:8px 10px;font:11px ui-monospace,monospace;color:var(--cyan);overflow-x:auto;white-space:nowrap;margin-bottom:6px}
.note{margin:16px 0 4px;padding:10px 14px;border:1px dashed var(--line2);color:var(--dim);font-size:11px}
footer{margin-top:22px;text-align:center;color:var(--faint);font-size:10.5px;text-transform:uppercase;letter-spacing:1px}footer a{color:var(--light)}
#look{margin:0 0 11px}#lookres{font-size:12px;color:var(--light);padding:0 2px 8px}
</style></head><body>
<header><div class=mark>&#9874;</div><div class=brand><h1>PROMETHIUM</h1><div class=tag>Community Explorer</div></div>
<div class=live><span class=dot></span> <span id=livets>live</span></div></header>
<div class=addrbar id=look><span class=lup>&#128269; look up</span>
<input id=q placeholder="prom1… address  — or a block height —" spellcheck=false>
<button class=btn onclick=doLookup()>Search</button></div>
<div id=lookres></div>
<div id=app><div class=card>loading…</div></div>
<div class=note>Reads the public Promethium explorer API. Runs locally, standard-library only. Set your address in the CONFIG block to light up the "Your Miner" panels.</div>
<footer>Community tool · not affiliated · docs &amp; setup at <a href="https://promethium.work/docs" target=_blank>promethium.work/docs</a></footer>
<script>
const fmt=n=>(n==null?'-':Number(n).toLocaleString());
const shrt=a=>a?a.slice(0,10)+'…'+a.slice(-7):'';
const ccFlag=cc=>(cc&&cc.length==2&&/[A-Z]{2}/.test(cc))?String.fromCodePoint(...[...cc].map(c=>0x1F1E6+c.charCodeAt(0)-65)):'🏳';
const mmss=s=>{s=Math.round(Number(s)||0);if(s<60)return s+'s';if(s<3600){const m=Math.floor(s/60);return m+'m '+(s%60).toString().padStart(2,'0')+'s';}const h=Math.floor(s/3600);return h+'h '+Math.floor((s%3600)/60).toString().padStart(2,'0')+'m';};
const spark=(arr,w,h)=>{if(!arr||arr.length<2)return '';const mn=Math.min(...arr),mx=Math.max(...arr),r=(mx-mn)||1;const pts=arr.map((v,i)=>`${(i/(arr.length-1)*w).toFixed(1)},${(h-1-(v-mn)/r*(h-3)).toFixed(1)}`).join(' ');return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none" style="margin-top:7px;display:block"><polygon points="0,${h} ${pts} ${w},${h}" fill="rgba(0,240,255,.10)"/><polyline points="${pts}" fill="none" stroke="var(--cyan)" stroke-width="1.5"/></svg>`;};
async function doLookup(){
 const q=document.getElementById('q').value.trim();if(!q)return;
 const el=document.getElementById('lookres');el.textContent='looking up…';
 try{const r=await(await fetch('/api/lookup?q='+encodeURIComponent(q))).json();
  if(r.error){el.innerHTML='<span style="color:#f87171">'+r.error+'</span>';return;}
  if(r.type=='block')el.innerHTML=`&#128230; block <b class=cy>#${fmt(r.height)}</b> · won by <span class=cy>${shrt(r.miner)}</span> · +${r.reward} PROM · ${r.txCount} tx`;
  else el.innerHTML=`&#128179; <span class=cy>${shrt(r.addr)}</span> · balance <b>${fmt(r.balance)} PROM</b> · ${fmt(r.utxos)} utxos · ${fmt(r.minedCount)} blocks mined (recent)`;
 }catch(e){el.textContent='lookup failed';}
}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key=='Enter')doLookup()});
function ago(s){return s<60?s+'s':s<3600?Math.round(s/60)+'m':Math.round(s/3600)+'h';}
const dur=s=>s<3600?Math.round(s/60)+'m':s<86400?Math.round(s/3600)+'h':(s/86400).toFixed(s<6*86400?1:0)+'d';
let LAST=null,lbPage=0;
function lbGo(z){lbPage+=z;if(LAST)render(LAST);}
async function tick(){
 let d;try{d=await(await fetch('/api/data')).json()}catch(e){return}
 LAST=d;render(d);
}
function render(d){
 if(!d.ready){document.getElementById('app').innerHTML='<div class=card>fetching network… '+(d.error||'')+'</div>';return}
 document.getElementById('livets').textContent='live · '+new Date(d.ts*1000).toLocaleTimeString();
 const effc=d.win_eff>=.8?'pos':d.win_eff>=.4?'lt':'red';
 const you=d.configured;
 const winners=(d.winners||[]).map((w,i)=>`<tr class="${w.you?'you':''}"><td class=rank>${i+1}</td><td>${w.you?'★ YOU':(w.pool?'🌐 ':'')+shrt(w.addr)}</td><td>${w.n}</td><td>${w.pct}%<span class=mbar><i style="width:${Math.min(100,w.pct*100/((d.winners[0]||{}).pct||1))}%"></i></span></td></tr>`).join('');
 const PER=20,allL=d.leaders||[],lbPages=Math.max(1,Math.ceil(allL.length/PER));
 if(lbPage>=lbPages)lbPage=lbPages-1; if(lbPage<0)lbPage=0;
 const leaders=allL.slice(lbPage*PER,lbPage*PER+PER).map(l=>`<tr class="${l.you?'you':''}"><td class=rank>${l.rank<=3?['','🥇','🥈','🥉'][l.rank]:l.rank}</td><td>${l.you?'★ YOU':(l.pool?'🌐 ':'')+shrt(l.addr)}${l.pool?' <small style="color:var(--dim)">shared pool</small>':''}</td><td class=cy>${fmt(Math.round(l.bal))}</td><td>${l.pct}%</td></tr>`).join('');
 const lbnav=lbPages>1?`<span class=pg><button onclick="lbGo(-1)" ${lbPage==0?'disabled':''}>‹ prev</button> ${lbPage+1}/${lbPages} <button onclick="lbGo(1)" ${lbPage>=lbPages-1?'disabled':''}>next ›</button></span>`:'';
 const feed=(d.feed||[]).map(f=>`<div class=row><span class="h">#${fmt(f.h)}</span><span class=w>${f.miner?(f.pool?'🌐 ':'')+shrt(f.miner):'—'}${f.you?' ★ you':''}</span><span class=rw>+${f.reward}</span><span class=tm>${ago(f.ago)}</span></div>`).join('');
 const rigs=(d.rigs||[]).map(r=>`<tr><td>${r.name||'—'}</td><td>${r.src?('<span class="tag2'+(r.src=='Local'?' gpu':'')+'">'+r.src+'</span>'):''}</td><td>${r.hps||'—'}</td><td>${r.where?('<span class=flag>'+r.where+'</span>'):''}</td><td class=lt>${r.status||''}</td></tr>`).join('')||'<tr><td colspan=5 style="color:#8fa9e8">no rig/log source — add an MRR key or a miner-log path in CONFIG (optional)</td></tr>';
 let nodeSec='';
 if(d.node){const n=d.node;
  if(n.ok){
   const roll=(n.countries||[]).map(c=>`${ccFlag(c.cc)}${c.n}`).join(' ');
   nodeSec=`<div class=sec><span class=t>Your Node</span><span class=ln></span><span class=pill>local promd · self-hosted</span></div>
   <div class="grid g4">
    <div class="card"><div class=k>Sync Status</div><div class="v ${n.synced?'pos':'red'}">${n.synced?'SYNCED':fmt(n.behind)+' behind'}</div><div class=s>height ${fmt(n.blocks)} · ${n.vp}% verified</div></div>
    <div class="card"><div class=k>Peers</div><div class="v cy">${n.peers}</div><div class=s>${n.cin} in · ${n.cout} out</div></div>
    <div class="card"><div class=k>Mempool</div><div class="v">${fmt(n.mempool)}</div><div class=s>txns waiting</div></div>
    <div class="card"><div class=k>Node Version</div><div class="v" style="font-size:15px;word-break:break-all">${n.subver||'—'}</div><div class=s>${n.chain||''} chain</div></div>
   </div>${roll?`<div class=note style="border-style:solid">🌍 Your peers span <b>${(n.countries||[]).length}</b> ${n.countries.length==1?'country':'countries'}: <span style="font-size:14px">${roll}</span></div>`:''}`;
  } else {
   nodeSec=`<div class=sec><span class=t>Your Node</span><span class=ln></span><span class=pill>local promd</span></div>
   <div class=card style="color:var(--red)">node RPC unreachable — check <b>NODE_RPC</b> / <b>NODE_COOKIE</b> in CONFIG. <span style="color:var(--dim)">(${n.err||''})</span></div>`;
  }
 }
 document.getElementById('app').innerHTML=`
 <div class=sec><span class=t>Network</span><span class=ln></span><span class=pill>$PROM · SHA-256d</span></div>
 <div class="grid g4">
  <div class="card hot"><div class=k>Block Height</div><div class="v">${fmt(d.tip)}</div><div class=s>latest ${d.feed&&d.feed[0]?ago(d.feed[0].ago)+' ago':''}</div></div>
  <div class="card hot"><div class=k>Network Hashrate</div><div class="v cy">${d.hps_10||d.nethps_ph} <small>PH/s</small></div><div class=s>live (last 10 blk) · <span style="color:var(--dim)">~2h avg ${d.hps_120} PH</span></div>${spark(d.hps_series,150,30)}</div>
  <div class="card hot"><div class=k>Difficulty</div><div class="v">${fmt(d.diff)}</div><div class=s>${d.retarget?`retarget in <b>${fmt(d.retarget.blocks_left)}</b> blk · ~${dur(d.retarget.eta_sec)}${d.retarget.est?` · est <span ${d.retarget.est.pct>=0?'class=cy':'style="color:var(--red)"'}>${d.retarget.est.pct>=0?'+':''}${d.retarget.est.pct}% ${d.retarget.est.dir}</span>`:''}`:'retarget every 2016 blocks'}</div>${d.retarget?`<div class=bar title="${d.retarget.progress}% into the 2016-block period → #${fmt(d.retarget.next_height)}"><i style="width:${d.retarget.progress}%"></i></div>`:''}</div>
  <div class="card hot"><div class=k>Block Time <small style="color:var(--dim);font-weight:400">· last ${d.bt_n||12} blk</small></div><div class="v"${(d.blocktime_recent!=null?d.blocktime_recent:d.blocktime)>900?' style="color:var(--red)"':((d.blocktime_recent!=null?d.blocktime_recent:d.blocktime)<540?' class=cy':'')}>${mmss(d.blocktime_recent!=null?d.blocktime_recent:d.blocktime)}</div><div class=s><span style="color:var(--dim)">24h avg <b>${mmss(d.blocktime)}</b> · 10m target</span></div>${spark(d.bt_series,150,30)}</div>
 </div>
 <div class="grid g6" style="margin-top:10px">
  <div class=card><div class=k>Block Reward</div><div class="v">${d.reward}<small> PROM</small></div></div>
  <div class=card><div class=k>Blocks / 24h</div><div class="v">${fmt(d.blocks24h)}</div></div>
  <div class=card><div class=k>Coins Mined</div><div class="v">${fmt(d.mined)}</div><div class=bar><i style="width:${d.mined_pct}%"></i></div></div>
  <div class=card><div class=k>Supply Cap</div><div class="v">${(d.cap/1e6).toFixed(1)}<small>M</small></div></div>
  <div class=card><div class=k>Next Halving</div><div class="v">~${d.halving_days}<small>d</small></div></div>
  <div class=card><div class=k>Holders</div><div class="v">${fmt(d.holders)}</div></div>
 </div>
 <div class=card style="margin-top:10px"><div class=k>🌐 Shared Pool · :${d.pool_port} · PPLNS</div>
  <div style="display:flex;gap:30px;align-items:baseline;margin-top:9px;flex-wrap:wrap">
   <div><span class="v cy" style="font-size:23px;margin:0">${d.pool.hps>=1?d.pool.hps+' PH/s':Math.round(d.pool.hps*1000)+' TH/s'}</span> <small style="color:var(--dim)">pool hashrate</small></div>
   <div><b class=cy>${d.pool.hps&&d.nethps_ph?(d.pool.hps/d.nethps_ph*100).toFixed(0):0}%</b> <small style="color:var(--dim)">of network</small></div>
   <div><b>${d.pool.active}/${d.pool.miners}</b> <small style="color:var(--dim)">miners active</small></div>
   <div><b>${fmt(d.pool.blocks_won)}</b> <small style="color:var(--dim)">blocks won by pool</small></div>
   ${d.pool_wallet?`<div><b class=cy>${fmt(Math.round(d.pool_wallet.balance))}</b> <small style="color:var(--dim)">PROM in pool wallet${d.pool_wallet.rank?' · rank #'+d.pool_wallet.rank:''}</small></div>`:''}
  </div>
  <div style="display:flex;gap:24px;align-items:baseline;margin-top:11px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:10px">
   <div><b>${mmss(d.pool.avg_bt)}</b> <small style="color:var(--dim)">pool block time</small></div>
   <div><b class=pos>${fmt(d.pool.blocks_mature)}</b><span style="color:var(--dim)"> / ${fmt(d.pool.blocks_immature)}</span> <small style="color:var(--dim)">mature / immature</small></div>
   <div><b class="${d.pool.orphan_rate>10?'red':'lt'}">${d.pool.orphan_rate}%</b> <small style="color:var(--dim)">orphaned (${fmt(d.pool.blocks_orphaned)})</small></div>
   <div><b class=cy>${fmt(d.pool.total_paid)}</b> <small style="color:var(--dim)">PROM paid all-time</small></div>
   <div><b>${fmt(d.pool.total_pending)}</b> <small style="color:var(--dim)">pending</small></div>
  </div>
  <div style="margin-top:8px;font-size:10.5px;color:var(--faint);word-break:break-all">🌐 pool wallet: ${d.pool_wallet?d.pool_wallet.addr:''}</div></div>
 ${d.pool_top&&d.pool_top.length?`<div class=tbl style="margin-top:10px"><div class=hd><span class=k>🏭 Top Pool Miners</span><span class=r>by earnings · shared pool</span></div>
  <table><tr><th class=rank>#</th><th>miner</th><th>paid</th><th>pending</th></tr>
  ${d.pool_top.map((m,i)=>`<tr class="${m.you?'you':''}"><td class=rank>${i+1}</td><td>${m.you?'★ YOU':(m.pool?'🌐 ':'')+shrt(m.addr)}</td><td class=cy>${fmt(Math.round(m.paid))}</td><td>${fmt(Math.round(m.pending))}</td></tr>`).join('')}</table></div>`:''}
 ${nodeSec}
 <div class=sec><span class=t>Your Miner</span><span class=ln></span><span class=pill>pool · solo · rented · local</span></div>
 ${you?`<div class="grid g4">
  <div class=card><div class=k>PROM Held</div><div class="v">${fmt(d.balance)}</div><div class=s>${d.blocks_total} coinbase utxos${d.n_wallets>1?' · '+d.n_wallets+' wallets':''}</div></div>
  <div class=card><div class=k>Earn Rate</div><div class="v ${d.rate>0?'pos':''}">${d.rate>0?'+':''}${fmt(d.rate)}<small>/hr</small></div><div class=s>${d.rate>0?'~'+(d.rate/60).toFixed(1)+' PROM/min':'measuring…'}</div></div>
  <div class=card><div class=k>Your Hashrate</div><div class="v cy">${d.have_hps?d.your_hps:'—'}</div><div class=s>${d.have_hps?d.net_pct+'% of network':'add MRR key / miner log'}</div>${d.have_hps?`<div class=bar><i style="width:${Math.min(100,d.net_pct)}%"></i></div>`:''}</div>
  <div class=card><div class=k>Win Efficiency</div><div class="v ${d.have_hps?effc:''}">${d.have_hps?d.win_eff+'×':'—'}</div><div class=s>${you?'won '+d.mine_window+' of last '+d.window_total+' blocks':''}</div></div>
 </div>`:`<div class=card style="color:#a9c6ff">Set <b>PROM_ADDRESS</b> in the CONFIG block (top of explorer.py) to track your balance, earnings, hashrate and blocks won. No address yet? <span class=cy>promethium.work/downloads/prom-keygen.py</span></div>`}
${d.pool_me&&d.pool_me.found?`
 <div class=sec><span class=t>Pool Payouts</span><span class=ln></span><span class=pill>shared pool · :${d.pool_port} · PPLNS</span></div>
 <div class="grid g4">
  <div class=card><div class=k>Pending</div><div class="v cy">${fmt(d.pool_me.pending)} <small>PROM</small></div><div class=s>unpaid — accruing from your shares</div></div>
  <div class=card><div class=k>Paid Out</div><div class="v pos">${fmt(d.pool_me.paid)} <small>PROM</small></div><div class=s>total sent to your address</div></div>
  <div class=card><div class=k>Your Pool Hashrate</div><div class="v">${d.pool_me.hps}</div><div class=s>measured by the pool via shares</div></div>
  <div class=card><div class=k>Pool Last Payout</div><div class="v">${fmt(Math.round(d.pool.lp_total))} <small>PROM</small></div><div class=s>${d.pool.lp_recips} miners · ${d.pool.lp_ts?ago(Math.floor(Date.now()/1000)-d.pool.lp_ts)+' ago':'—'}</div></div>
 </div>
 <div class=note>You're mining the shared pool (:${d.pool_port}, PPLNS): blocks are won by the <b>pool</b> and your cut is paid to your address — so "Blocks Won" below counts only solo/coinbase wins. Your real pool earnings are <b>Pending + Paid</b> above.</div>`:''}
 <div class="grid g2" style="margin-top:10px;align-items:start">
  <div style="display:flex;flex-direction:column;gap:10px">
   <div class=tbl><div class=hd><span class=k>⛏ Your Hardware</span><span class=r>delivered · 5 min</span></div>
    <table><tr><th>device / rig</th><th>source</th><th>hashrate</th><th>where</th><th>status</th></tr>${rigs}</table></div>
   <div class="tbl feed"><div class=hd><span class=k>📜 Recent Blocks</span><span class=r>live feed</span></div>${feed}</div>
  </div>
  <div class=tbl><div class=hd><span class=k>🔥 Top Block Winners</span><span class=r>last ${d.window_total}</span></div>
   <table><tr><th class=rank>#</th><th>miner</th><th>won</th><th>share</th></tr>${winners}</table></div>
 </div>
 <div class=sec><span class=t>Leaderboard</span><span class=ln></span><span class=pill>top holders · all-time</span></div>
 <div class=tbl><div class=hd><span class=k>🏆 Top Holders</span>${lbnav}<span class=r>${fmt(d.holders)} holders · ${fmt(d.mined)} PROM mined</span></div>
  <table><tr><th class=rank>#</th><th>miner</th><th>PROM held</th><th>% of supply</th></tr>${leaders}</table></div>
 <div class=sec><span class=t>Get Mining</span><span class=ln></span><span class=pill>official setup docs</span></div>
 <div class=getmine>
  <div class=gm><h3>🌐 Shared Pool · :${d.pool_port}</h3><p>PPLNS · 0% fee · steady, proportional — best for CPUs &amp; smaller rigs. Guide: <a href="https://promethium.work/docs/mining-pool" target=_blank>docs/mining-pool</a></p>
   <code>stratum+tcp://${d.pool_host}:${d.pool_port}</code><code>-u prom1qYOUR…addr -p x</code></div>
  <div class=gm><h3>🎯 Solo · :${d.solo_port}</h3><p>Keep every block you find — high-variance. Guide: <a href="https://promethium.work/docs/run-a-miner" target=_blank>docs/run-a-miner</a></p>
   <code>stratum+tcp://${d.pool_host}:${d.solo_port}</code><code>-u prom1qYOUR…addr -p x</code></div>
  <div class=gm><h3>💻 Tools &amp; Skills</h3><p>Official agent skills &amp; helpers:</p>
   <code><a href="https://promethium.work/downloads/prom-miner.py" target=_blank>prom-miner.py</a> · <a href="https://promethium.work/downloads/prom-keygen.py" target=_blank>prom-keygen.py</a></code>
   <code><a href="https://promethium.work/downloads/pool-skill.md" target=_blank>pool-skill.md</a> · <a href="https://promethium.work/downloads/node-skill.md" target=_blank>node-skill.md</a></code></div>
 </div>`;
 applyCollapse();
}
const _COLL=JSON.parse(localStorage.getItem('prom_coll')||'{}');
function _keyOf(el){const t=el.querySelector('.t,.k');return (t?t.textContent:el.textContent).trim().slice(0,48);}
function applyCollapse(){
 const app=document.getElementById('app');
 app.querySelectorAll('.sec').forEach(sec=>{
  const key='S:'+_keyOf(sec); let c=sec.querySelector('.chev');
  if(!c){c=document.createElement('span');c.className='chev';sec.insertBefore(c,sec.firstChild);}
  const col=!!_COLL[key]; c.textContent=col?'▸':'▾';
  let el=sec.nextElementSibling;
  while(el&&!el.classList.contains('sec')){el.style.display=col?'none':'';el=el.nextElementSibling;}
 });
 app.querySelectorAll('.tbl').forEach(tbl=>{
  const hd=tbl.querySelector('.hd'); if(!hd)return;
  const key='T:'+_keyOf(hd); let c=hd.querySelector('.chev');
  if(!c){c=document.createElement('span');c.className='chev';hd.insertBefore(c,hd.firstChild);}
  const col=!!_COLL[key]; c.textContent=col?'▸':'▾';
  let el=hd.nextElementSibling; while(el){el.style.display=col?'none':'';el=el.nextElementSibling;}
 });
}
document.getElementById('app').addEventListener('click',e=>{
 if(e.target.closest('a,button,input,.pg'))return;
 const hd=e.target.closest('.hd'), sec=hd?null:e.target.closest('.sec');
 const t=hd||sec; if(!t)return;
 const key=(hd?'T:':'S:')+_keyOf(t);
 _COLL[key]=!_COLL[key]; localStorage.setItem('prom_coll',JSON.stringify(_COLL)); applyCollapse();
});
tick();setInterval(tick,5000);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def _send(self, body, ctype):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith("/api/lookup"):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self._send(json.dumps(lookup((qs.get("q") or [""])[0])), "application/json")
        elif self.path.startswith("/api/data"):
            self._send(json.dumps(STATE), "application/json")
        else:
            self._send(HTML, "text/html; charset=utf-8")

if __name__ == "__main__":
    if not MY:
        print("!! Tip: set PROM_ADDRESS in the CONFIG block to enable the 'Your Miner' panels.")
        print("   No address? -> https://promethium.work/downloads/prom-keygen.py")
    threading.Thread(target=update_loop, daemon=True).start()
    print(f"Promethium dashboard -> http://localhost:{PORT}   (leave open; Ctrl+C to stop)")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
