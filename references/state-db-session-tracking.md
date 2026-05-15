# Hermes state.db Session Token Tracking — 关键限制（v2.5.0）

## 核心行为（实测确认）

| 行为 | 实际表现 |
|------|---------|
| Hermes 在每次 API 调用后写 state.db | ✅ 是，每次响应都增量写入 |
| `ended_at = 0` 表示活跃 session | ❌ Hermes 从不写 `ended_at = 0` |
| session 结束后立刻写入 state.db | ✅ 是 |
| 活跃 session 在 state.db 里吗？ | ❌ **不在**——活跃 session 只有 session 文件，没有 state.db 记录 |

**结论：state.db 只存已结束的 session 的累计值。活跃 session 的 token 是实时增量写的，但 session 本身不到结束不进 db。**

## Session 生命周期

```
用户发消息 → Hermes 开新 session 文件（session_N.json）
                    ↓
              API 调用发生
                    ↓
         run_agent.py: update_token_counts(absolute=False)
                    ↓
              state.db 更新该 session 的 input_tokens += N
                    ↓
              用户继续发消息 → 还是同一个 session
                    ↓
              用户结束对话 / 超时
                    ↓
              Hermes 写 ended_at = <timestamp>
              （注意：不是写 0，是写实际的结束时间戳）
              然后立刻开一个新 session 文件（可能只有几条消息）
```

## state.db sessions 表关键字段

| 字段 | 格式 | 说明 |
|------|------|------|
| `started_at` | Unix timestamp（秒） | session 开始时间 |
| `ended_at` | Unix timestamp（秒） | session 结束时间；**0 表示从未结束** |
| `input_tokens` | 整数 | 实时增量写入，session 结束时就是最终值 |
| `message_count` | 整数 | 消息总数 |
| `model` | 字符串 | 模型名称 |

**重要：`ended_at = 0` 表示 session 从未结束，不是"进行中"的标记。** 实际上 Hermes 活跃 session 的 `ended_at` 在 state.db 里根本没有记录（因为 session 还没结束就不会写 ended_at）。

## 正确的 Session 选择逻辑（v2.5.0）

```python
def hermes_get_last_session():
    """
    策略：
    1. 从 state.db ORDER BY ended_at DESC LIMIT 15
    2. 跳过 msg_count ≤ 5 AND input_tokens ≤ 1000 的空 session
    3. 必须是本月（按 started_at 的月份判断）
    4. 返回第一个匹配 → state.db 准确值

    若没有符合条件的已结束 session：
    → 从 session 文件估算
    """
    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, input_tokens, output_tokens, cache_read_tokens,
               model, ended_at, message_count, started_at
        FROM sessions
        WHERE ended_at > 0
        ORDER BY ended_at DESC
        LIMIT 15
    """)
    rows = cur.fetchall()
    conn.close()

    this_month = datetime.now().strftime("%Y-%m")
    for r in rows:
        started = r["started_at"]
        if started:
            if datetime.fromtimestamp(started).strftime("%Y-%m") != this_month:
                continue  # 跳过非本月
        msg_count = r["message_count"] or 0
        inp = r["input_tokens"] or 0
        if msg_count > 5 or inp > 1000:
            # ✅ 找到了有内容的已结束 session
            return {
                "input": inp,
                "output": r["output_tokens"] or 0,
                "cacheRead": r["cache_read_tokens"] or 0,
                "model": r["model"] or "unknown",
            }

    # 没有符合条件的 session → 文件估算（备用）
    return estimate_from_session_files()
```

## 关键陷阱

### 陷阱 1：空 cron session 被误选

Hermes 在上一个 session 结束后**立刻创建一个新的空 session**（通常 0 条消息）。这个新文件的 `ended_at` 是当前时间，所以 `ORDER BY ended_at DESC LIMIT 1` 会直接选中它。

**症状：** 本次 token 显示 0 或极小值（如 8k vs 实际 200k）

**解法：** 加 `msg_count > 5 OR input_tokens > 1000` 过滤

### 陷阱 2：mtime 最新 ≠ 主会话

session 文件的 mtime 反映最后修改时间。新开的空 session 文件 mtime 最新，但消息数少。主 session 消息多但 mtime 较旧。

**症状：** 按 mtime 选文件时选到空 session，token 估算严重偏低

**解法：** 不按 mtime 选；用上面的过滤条件

### 陷阱 3：`SELECT` 列和 `r["key"]` 不匹配

如果 SQL SELECT 列表里没有某个列，但 Python 代码访问 `r["该列"]`，会触发 `KeyError`，被 `except` 静默吃掉，返回 `None` → 最终变成全 0。

**解法：** 每次写 SQL 前先 `PRAGMA table_info(sessions)` 确认列名

### 陷阱 4：`conn.row_factory = sqlite3.Row` 后忘记 `cur = conn.cursor()`

设置 `row_factory` 后立刻执行 SQL 但忘记创建 cursor，`NameError` 被 `except` 静默吃掉。

**解法：** `row_factory` 和 `cursor()` 要紧挨着写

## 各指标精度（v2.5.0）

| 指标 | 精度 | 说明 |
|------|------|------|
| 本次（最近已结束 session） | ✅ 精确 | state.db，`msg>5 or in>1000` 过滤 |
| 本次（无已结束 session 时） | ⚠️ 估算 | 字符数×比例，仅作参考 |
| 本次（单轮交换） | ❌ 不可能 | Hermes 不存 per-turn 数据 |
| 本月总消耗 | ✅ 精确 | state.db SUM（包含所有已结束 session） |
| 本月活跃 session | ✅ 精确 | 已在 state.db 实时写入，v2.4.0 修复后计入 |
| 本月用户消息数 | ✅ 精确 | session 文件逐条统计 |

## 为什么月累计差 6M（2026-05-15 实测）

| 查询方式 | 月累计 |
|---------|-------|
| `WHERE ended_at > 0`（旧，有 bug） | 62.13M |
| 无 `WHERE ended_at` 限制（已修复） | 68.24M |

差值 6.11M 来自 10 个还在进行的 session（如 `20260501_084612` 从5月1日就开始了），它们的 token 已被实时写入 state.db，但 `WHERE ended_at > 0` 把它们排除了。
