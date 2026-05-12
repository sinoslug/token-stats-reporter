#!/usr/bin/env python3
"""
token-show.py - Token 统计输出脚本（双底座版）
支持 OpenClaw（jsonl）和 Hermes（state.db）两种数据源
支持自定义参考费率，默认使用 Anthropic Claude Opus 4.7 费率

用法:
    python3 token-show.py                          # 使用默认 Opus 4.7 费率
    python3 token-show.py --model opus4.7           # Opus 4.7
    python3 token-show.py --model openai            # GPT-5.5
    python3 token-show.py --rates 3 15 0.3         # 自定义费率 (input output cache)
"""
import json
import argparse
import sqlite3
from pathlib import Path
from datetime import datetime

HOME = Path.home()

# OpenClaw 数据源
SESSIONS_DIR = HOME / ".openclaw/agents/main/sessions"

# Hermes 数据源
STATE_DB = HOME / ".hermes/state.db"

# Anthropic Claude Opus 4.7 参考费率
OPENAI_INPUT_RATE = 15.00
OPENAI_OUTPUT_RATE = 75.00
OPENAI_CACHE_RATE = 1.125

# OpenAI GPT-5.5 参考费率
OPENAI_INPUT_RATE_OPENAI = 5.00
OPENAI_OUTPUT_RATE_OPENAI = 30.00
OPENAI_CACHE_RATE_OPENAI = 1.25

DEFAULT_RATES = {
    "opus4.7": {"input": OPENAI_INPUT_RATE, "output": OPENAI_OUTPUT_RATE, "cache": OPENAI_CACHE_RATE, "name": "Opus 4.7"},
    "openai": {"input": OPENAI_INPUT_RATE_OPENAI, "output": OPENAI_OUTPUT_RATE_OPENAI, "cache": OPENAI_CACHE_RATE_OPENAI, "name": "OpenAI GPT-5.5"},
}

USD_TO_CNY = 7.20


def get_current_month():
    return datetime.now().strftime("%Y-%m")


def format_int(n):
    return str(int(n))


def format_compact(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    elif n >= 1_000:
        return f"{n / 1_000:.2f}k"
    return str(int(n))


def format_cost(c):
    if c < 0.01:
        return f"¥{c:.4f}"
    return f"¥{c:.2f}"


def calc_cost(inp, out, cache, rates):
    inp_usd = inp / 1_000_000 * rates["input"]
    out_usd = out / 1_000_000 * rates["output"]
    cache_usd = cache / 1_000_000 * rates["cache"]
    return (inp_usd + out_usd + cache_usd) * USD_TO_CNY


# ─── Hermes state.db 数据源 ────────────────────────────────────────────

def hermes_available():
    return STATE_DB.exists()


def hermes_get_last_session():
    """获取最近一个已结束的 session 的 token 用量"""
    try:
        conn = sqlite3.connect(STATE_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT input_tokens, output_tokens, cache_read_tokens, model
            FROM sessions
            WHERE ended_at > 0
            ORDER BY ended_at DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        conn.close()
        if row:
            return {
                "input": row["input_tokens"] or 0,
                "output": row["output_tokens"] or 0,
                "cacheRead": row["cache_read_tokens"] or 0,
                "model": row["model"] or "unknown"
            }
    except Exception:
        pass
    return None


def hermes_get_model():
    """从 Hermes state.db 获取当前模型"""
    try:
        conn = sqlite3.connect(STATE_DB)
        cur = conn.cursor()
        cur.execute("""
            SELECT model FROM sessions
            WHERE ended_at > 0
            ORDER BY ended_at DESC LIMIT 1
        """)
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            m = row[0]
            return m.split("/")[-1] if "/" in m else m
    except Exception:
        pass
    return "unknown"


def hermes_scan_monthly(month=None):
    """从 Hermes state.db 扫描当月累计 token（仅统计 ended_at > 0 的 sessions）"""
    if month is None:
        month = get_current_month()
    try:
        conn = sqlite3.connect(STATE_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # ended_at 是 Unix timestamp (秒)
        cur.execute("""
            SELECT input_tokens, output_tokens, cache_read_tokens, started_at
            FROM sessions
            WHERE ended_at > 0
            ORDER BY started_at DESC
        """)
        rows = cur.fetchall()
        conn.close()

        total_in = total_out = total_cache = 0
        msg_count = 0
        for row in rows:
            # started_at 是秒级 timestamp
            ts = row["started_at"]
            if ts:
                msg_month = datetime.fromtimestamp(ts).strftime("%Y-%m")
                if msg_month != month:
                    continue
            inp = row["input_tokens"] or 0
            out = row["output_tokens"] or 0
            cache = row["cache_read_tokens"] or 0
            if inp <= 0 and out <= 0:
                continue
            total_in += inp
            total_out += out
            total_cache += cache
            msg_count += 1

        return {
            "input": total_in,
            "output": total_out,
            "cacheRead": total_cache,
            "msg_count": msg_count,
        }
    except Exception:
        return {"input": 0, "output": 0, "cacheRead": 0, "msg_count": 0}


# ─── OpenClaw jsonl 数据源（备用） ──────────────────────────────────

def openclaw_available():
    return SESSIONS_DIR.exists() and any(SESSIONS_DIR.glob("*.jsonl"))


def openclaw_get_model():
    try:
        files = list(SESSIONS_DIR.glob("*.jsonl"))
        if not files:
            return "unknown"
        latest = max(files, key=lambda f: f.stat().st_mtime)
        with open(latest) as f:
            for line in reversed(f.readlines()):
                if not line.strip():
                    continue
                try:
                    d = json.loads(line.strip())
                    if d.get("type") == "message":
                        m = d.get("message", {}).get("model", "")
                        if m:
                            return m.split("/")[-1] if "/" in m else m
                except:
                    continue
        return "unknown"
    except:
        return "unknown"


def openclaw_get_last_msg_usage():
    try:
        files = list(SESSIONS_DIR.glob("*.jsonl"))
        if not files:
            return None
        latest = max(files, key=lambda f: f.stat().st_mtime)
        with open(latest) as f:
            for line in reversed(f.readlines()):
                if not line.strip():
                    continue
                try:
                    d = json.loads(line.strip())
                    if d.get("type") == "message":
                        msg = d.get("message", {})
                        if msg.get("role") == "assistant":
                            u = msg.get("usage", {})
                            if u:
                                inp = u.get("input", 0) or u.get("inputTokens", 0)
                                out = u.get("output", 0) or u.get("outputTokens", 0)
                                cache = u.get("cacheRead", 0) or u.get("cacheTokens", 0)
                                return {"input": inp, "output": out, "cacheRead": cache}
                except:
                    continue
        return None
    except:
        return None


def openclaw_scan_monthly(month=None):
    if month is None:
        month = get_current_month()
    total_in = total_out = total_cache = 0
    msg_count = 0
    for jf in list(SESSIONS_DIR.glob("*.jsonl")):
        try:
            with open(jf) as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        d = json.loads(line.strip())
                    except:
                        continue
                    if d.get("type") != "message":
                        continue
                    msg = d.get("message", {})
                    if msg.get("role") != "assistant":
                        continue
                    u = msg.get("usage", {})
                    if not u:
                        continue
                    inp = u.get("input", 0) or u.get("inputTokens", 0)
                    out = u.get("output", 0) or u.get("outputTokens", 0)
                    if inp <= 0 and out <= 0:
                        continue
                    ts = msg.get("timestamp", 0)
                    if ts:
                        msg_month = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m")
                        if msg_month != month:
                            continue
                    total_in += inp
                    total_out += out
                    total_cache += u.get("cacheRead", 0) or u.get("cacheTokens", 0)
                    msg_count += 1
        except:
            continue
    return {
        "input": total_in,
        "output": total_out,
        "cacheRead": total_cache,
        "msg_count": msg_count,
    }


# ─── 统一入口 ────────────────────────────────────────────────────────

def get_model():
    if hermes_available():
        m = hermes_get_model()
        if m != "unknown":
            return m
    if openclaw_available():
        return openclaw_get_model()
    return "unknown"


def get_last_msg_usage():
    if hermes_available():
        data = hermes_get_last_session()
        if data:
            return data
    if openclaw_available():
        data = openclaw_get_last_msg_usage()
        if data:
            return data
    return {"input": 0, "output": 0, "cacheRead": 0}


def scan_monthly_tokens(month=None):
    if hermes_available():
        return hermes_scan_monthly(month)
    if openclaw_available():
        return openclaw_scan_monthly(month)
    return {"input": 0, "output": 0, "cacheRead": 0, "msg_count": 0}


def get_current_model_rates():
    """根据当前模型返回实际费率（MiniMax 免费额度内返回0）"""
    model = get_model().lower()
    # MiniMax 模型暂不收费
    if "minimax" in model or "m2.7" in model:
        return {"input": 0, "output": 0, "cache": 0, "name": "MiniMax"}
    # 其他模型暂用 Opus 4.7 费率
    return DEFAULT_RATES["opus4.7"]


def main():
    parser = argparse.ArgumentParser(description="Token 统计输出")
    parser.add_argument("--model", "-m", choices=["opus4.7", "openai"], default="opus4.7",
                        help="选择参考费率模型 (默认: opus4.7)")
    parser.add_argument("--rates", "-r", nargs=3, type=float, metavar=("INPUT", "OUTPUT", "CACHE"),
                        help="自定义费率 (美元/百万tokens)")
    args = parser.parse_args()

    if args.rates:
        ref_rates = {"input": args.rates[0], "output": args.rates[1], "cache": args.rates[2], "name": "custom"}
    else:
        ref_rates = DEFAULT_RATES[args.model]

    # 实际计费费率（当前模型）
    actual_rates = get_current_model_rates()
    # Opus 4.7 参考费率固定
    opus_rates = DEFAULT_RATES["opus4.7"]

    monthly = scan_monthly_tokens(get_current_month())
    last = get_last_msg_usage()
    si = last.get("input", 0)
    so = last.get("output", 0)
    sc = last.get("cacheRead", 0)
    st = si + so + sc
    billable = si + sc  # 计费token = input + cacheRead
    monthly_total = monthly["input"] + monthly["output"] + monthly["cacheRead"]

    single_cost_actual = calc_cost(si, so, sc, actual_rates)
    monthly_cost_actual = calc_cost(monthly["input"], monthly["output"], monthly["cacheRead"], actual_rates)
    single_cost_opus = calc_cost(si, so, sc, opus_rates)
    monthly_cost_opus = calc_cost(monthly["input"], monthly["output"], monthly["cacheRead"], opus_rates)

    line = (
        f"📊 Token: {format_int(si)} in / {format_int(so)} out | "
        f"cacheRead: {format_int(sc)} | "
        f"本次总消耗: {format_compact(st)} | "
        f"本次计费token: {format_int(billable)} | "
        f"本月: {format_int(monthly['msg_count'])} 次 | "
        f"月累计总消耗: {format_compact(monthly_total)} | "
        f"本次费用: {format_cost(single_cost_actual)} | "
        f"本月费用: {format_cost(monthly_cost_actual)} | "
        f"💰 本次(参考Opus 4.7): {format_cost(single_cost_opus)} | "
        f"💰 本月(参考Opus 4.7): {format_cost(monthly_cost_opus)} | "
        f"模型: {get_model()}"
    )
    print(line)


if __name__ == "__main__":
    main()
