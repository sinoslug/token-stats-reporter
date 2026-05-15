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
SESSIONS_DIR = HOME / ".hermes/sessions"

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
    """获取当前对话 session 的 token 用量。

    策略：
    1. 从 state.db 找本月的 session（按 ended_at DESC），排除 cron 空 session
    2. 如果最近 session 消息数 > 5，用它（state.db 数据是准的）
    3. 否则从 session 文件估算（活跃 session 还没落库）
    """
    try:
        import glob as _glob, os as _os, re as _re
        from datetime import datetime as _datetime

        conn = sqlite3.connect(STATE_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT id, input_tokens, output_tokens, cache_read_tokens, model, ended_at, message_count, started_at
            FROM sessions
            WHERE ended_at > 0
            ORDER BY ended_at DESC
            LIMIT 15
        """)
        rows = cur.fetchall()
        conn.close()

        this_month = _datetime.now().strftime("%Y-%m")
        for r in rows:
            started = r["started_at"]
            if started:
                if _datetime.fromtimestamp(started).strftime("%Y-%m") != this_month:
                    continue
            msg_count = r["message_count"] or 0
            inp = r["input_tokens"] or 0
            # 跳过空 session（cron 任务等）
            if msg_count > 5 or inp > 1000:
                return {
                    "input": inp,
                    "output": r["output_tokens"] or 0,
                    "cacheRead": r["cache_read_tokens"] or 0,
                    "model": r["model"] or "unknown",
                    "ended_at": r["ended_at"],
                }

        # 没找到有内容的 session，从文件估算
        session_files = _glob.glob(str(SESSIONS_DIR / "session_*.json"))
        candidates = []
        for fp in session_files:
            try:
                mtime = _os.path.getmtime(fp)
                with open(fp, encoding="utf-8") as f:
                    data = json.load(f)
                msgs = data.get("messages", [])
                if len(msgs) > 10:
                    candidates.append((mtime, len(msgs), fp, data))
            except Exception:
                continue

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            mtime, msg_count, fp, data = candidates[0]
            total_in = 0
            for msg in data.get("messages", []):
                content = ""
                if msg.get("role") == "user":
                    content = str(msg.get("content", ""))
                elif msg.get("role") == "assistant":
                    content = str(msg.get("content", "")) + str(msg.get("reasoning", ""))
                if content:
                    cn = len(_re.findall(r"[\u4e00-\u9fff]", content))
                    en = len(_re.sub(r"[\u4e00-\u9fff]", "", content))
                    total_in += cn * 2 + en * 0.25
            total_out = int(total_in * 0.05)
            total_cache = int(total_in * 0.80)
            return {
                "input": int(total_in),
                "output": total_out,
                "cacheRead": total_cache,
                "model": data.get("model", "MiniMax-M2.7"),
                "source": "estimate",
            }
    except Exception as e:
        import sys as _sys
        _sys.stderr.write(f"hermes_get_last_session error: {e}\n")
        import traceback as _tb
        _tb.print_exc(file=_sys.stderr)
    return {"input": 0, "output": 0, "cacheRead": 0}


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
    """从 Hermes state.db 扫描当月累计 token。
    ⚠️ 包含 ended_at = 0 的活跃 session（不过滤 ended_at）。
    2026-05-15 发现：原 WHERE ended_at > 0 会排除所有未结束 session，
    导致月累计少了正在进行的对话。
    """
    if month is None:
        month = get_current_month()
    try:
        conn = sqlite3.connect(STATE_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # 不过滤 ended_at — 活跃 session（ended_at=0）也要计入月累计
        cur.execute("""
            SELECT input_tokens, output_tokens, cache_read_tokens, started_at
            FROM sessions
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
            "session_count": msg_count,  # 已废弃，名存实亡
        }
    except Exception:
        return {"input": 0, "output": 0, "cacheRead": 0, "session_count": 0}


def hermes_scan_monthly_user_messages(month=None):
    """从 session 文件扫描当月用户消息数（轮数）"""
    if month is None:
        month = get_current_month()
    try:
        sessions_dir = HOME / ".hermes/sessions"
        total_user_msgs = 0
        for fp in sessions_dir.glob("session_*.json"):
            try:
                with open(fp, encoding="utf-8") as f:
                    data = json.load(f)
                ss = data.get("session_start", "")
                if not ss or ss[:7] != month:
                    continue
                for msg in data.get("messages", []):
                    if msg.get("role") == "user":
                        total_user_msgs += 1
            except Exception:
                continue
        return {"user_messages": total_user_msgs}
    except Exception:
        return {"user_messages": 0}


# ─── Hermes 当前会话文件估算（解决 state.db 不记录活跃会话的问题）───

def estimate_tokens_from_session_file(sessions_dir, cutoff_ended_at):
    """
    从 session JSON 文件估算 token 用量。
    仅用于 mtime 晚于 cutoff_ended_at 的 session。
    当有多个候选时，优先选择消息数最多的 session（避免 session 切换
    后新创建的空 session 被错误选中）。
    """
    import glob, os, re

    session_files = glob.glob(os.path.join(sessions_dir, "session_*.json"))

    # 收集所有 mtime > cutoff 的 session，按消息数排序
    candidates = []
    for fp in session_files:
        try:
            mtime = os.path.getmtime(fp)
            if mtime <= cutoff_ended_at:
                continue
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            msgs = data.get("messages", [])
            if not msgs:
                continue
            candidates.append((len(msgs), fp, data))
        except Exception:
            continue

    if not candidates:
        return None

    # 选消息数最多的 session（主对话 session）
    candidates.sort(key=lambda x: x[0], reverse=True)
    _, fp, data = candidates[0]

    msgs = data.get("messages", [])
    total_in = 0
    for msg in msgs:
        content = ""
        if msg.get("role") == "user":
            content = str(msg.get("content", ""))
        elif msg.get("role") == "assistant":
            content = str(msg.get("content", "")) + str(msg.get("reasoning", ""))
        if content:
            cn = len(re.findall(r"[\u4e00-\u9fff]", content))
            en = len(re.sub(r"[\u4e00-\u9fff]", "", content))
            total_in += cn * 2 + en * 0.25

    # 估算 output ≈ input 的 5%（经验值）
    total_out = int(total_in * 0.05)
    # 估算 cache ≈ input 的 80%（MiniMax cache 命中率高）
    total_cache = int(total_in * 0.80)

    return {
        "input": int(total_in),
        "output": total_out,
        "cacheRead": total_cache,
        "model": data.get("model", "MiniMax-M2.7"),
        "source": "session_file_estimate",
        "msg_count": len(msgs),
    }


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
    """获取当前活跃 session 的 token 用量。

    hermes_get_last_session() 已经内置了完整的判断逻辑：
    - 优先用 session 文件中 mtime 最新且消息数 > 10 的（活跃 session）
    - 如果文件不比 db 新，用 state.db（更准确）
    """
    if hermes_available():
        return hermes_get_last_session()
    if openclaw_available():
        data = openclaw_get_last_msg_usage()
        if data:
            return data
    return {"input": 0, "output": 0, "cacheRead": 0}


def scan_monthly_tokens(month=None):
    data = {}
    if hermes_available():
        data = hermes_scan_monthly(month)
    elif openclaw_available():
        data = openclaw_scan_monthly(month)
    # 补充用户消息数
    data.setdefault("session_count", 0)
    if hermes_available():
        um = hermes_scan_monthly_user_messages(month)
        data["user_messages"] = um.get("user_messages", 0)
    else:
        data["user_messages"] = 0
    return data


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
        f"本月: {format_int(monthly.get('user_messages', 0))} 条用户消息 | "
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
