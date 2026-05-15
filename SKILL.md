---
name: token-stats-reporter
description: |
  生成 Token 使用统计和参考费用报告。支持 Anthropic Claude Opus 4.7 和 OpenAI GPT-5.5 两种参考费率，默认 Opus 4.7，输出"省了多少"的满足感。
  适用场景：用户要求查看 Token 使用统计、需要展示"本应多少费用"、生成每条消息末尾的 Token 统计行。
  触发词：token统计、费用多少、省了多少钱、Token统计。
  ⚠️ 本 skill 专为 Hermes 平台设计（数据源：~/.hermes/state.db），不适用于 OpenClaw 平台。
  ⚠️ OpenClaw 有独立的 token 统计脚本（位于 ~/.openclaw/workspace/scripts/token-show.py），两者数据互不相通。
version: 2.6.0
updated: 2026-05-15
author: 妮小虾 🦐
---

# Token 使用统计报告技能

生成 Token 使用统计和参考费用报告。

## 输出格式（v2.3.0，唯一标准）

```
📊 Token: {in} in / {out} out | cacheRead: {cache} | 本次总消耗: {total} | 本次计费token: {billable} | 本月: {user_msgs} 条用户消息 | 月累计总消耗: {monthly} | 本次费用: {fee} | 本月费用: {monthly_fee} | 💰 本次(参考Opus 4.7): {opus_cost} | 💰 本月(参考Opus 4.7): {opus_monthly_cost} | 模型: {model}
```

字段说明：
- `{in}` 本次 input tokens（整数）
- `{out}` 本次 output tokens（整数）
- `{cache}` 本次缓存读取 tokens（整数）
- `{total}` 本次总消耗（in + out + cache，紧凑 k/M 格式）
- `{user_msgs}` **本月用户消息数**（从 session 文件逐条统计，非会话数）
- `{monthly}` 当月总 tokens（in+out+cache，紧凑 k/M 格式）
- `{cost}` 按所选参考费率计算的费用
- `{model}` 当前模型名称

## IMPORTANT — Per-User Requirement (ZhangQin)

**For 主人 ZhangQin: Append token stats to EVERY reply without exception.**
- Even confirmations, acknowledgments, and one-liners
- Never skip, never ask "要不要加", never handwrite numbers
- Run the script before sending, validate the output, then append
- If the script fails, do not send — fix the script path first

This is a standing instruction, not optional.

## 费率标准

| 模型 | Input | Output | Cache Read |
|------|-------|--------|------------|
| Anthropic **Opus 4.7**（默认） | $15.00/M | $75.00/M | $1.125/M |
| OpenAI **GPT-5.5** | $5.00/M | $30.00/M | $1.25/M |

汇率固定：USD → CNY = 7.20

## 使用方式

```bash
python3 ~/.hermes/skills/openclaw-imports/token-stats-reporter/scripts/token-show.py
```

## 数据来源

### 嫒小虾（Hermes 底座）

数据源：`~/.hermes/state.db`（SQLite）+ `~/.hermes/sessions/session_*.json`（实时扫描）

**\"本次\"数据逻辑（v2.5.0）：**

```
Session 选择策略（已验证，最终版）：
1. 从 state.db ORDER BY ended_at DESC LIMIT 15 取最近结束的 session
2. 跳过 msg_count ≤ 5 AND input_tokens ≤ 1000 的空 session（cron 任务等）
3. 必须是本月（按 started_at 的月份判断）
4. 返回匹配的第一个 → ✅ state.db 准确值

若没有符合条件的已结束 session：
→ 从 session 文件估算（活跃 session 还没落库）
```

**关键行为（已踩坑，实测验证）：**

- `state.db` 只在 session **结束时**才写入；活跃 session 的 token 是实时增量写入的
- Hermes **从来不写 `ended_at = 0`**，`WHERE ended_at = 0` 永远返回空
- `WHERE ended_at > 0` 会排除仍在进行的 session → 月累计少算（已修复，v2.4.0）
- Hermes 每个对话轮次会开新 session 并立刻创建文件；该文件 mtime 总是最新，但消息可能只有几条（空 cron session）
- **不能按 mtime 选 session**，必须按 `message_count` 或 `input_tokens` 过滤空 session

## 已知 bug 及修复记录

| Bug | 症状 | 修复 | 版本 |
|-----|------|------|------|
| `hermes_scan_monthly` 加了 `WHERE ended_at > 0` | 月累计少算活跃 session | 移除该条件 | v2.4.0 |
| `hermes_get_last_session` 漏写 `cur = conn.cursor()` | 函数静默返回 None，所有数据变成 0 | 补上 | v2.5.0 |
| SELECT 列表缺 `started_at` 但代码访问了 `r["started_at"]` | `KeyError` 被 `except pass` 静默吃掉 → 返回全 0 | SELECT 加 `started_at` | v2.5.0 |
| `SESSIONS_DIR` 指向 `~/.openclaw/agents/main/sessions` | 文件估算永远找不到 Hermes session | 改为 `~/.hermes/sessions` | v2.5.0 |
| 按 `ended_at DESC LIMIT 1` 选了空 cron session | 本次 token 估算值极小（8k vs 实际 206k） | 加 `msg_count > 5 OR input > 1000` 过滤 | v2.5.0 |
| `except Exception: pass` 静默掩盖所有错误 | bug 导致数据全 0 但无任何提示 | 改为打印 traceback | v2.5.0 |

## 各指标精度一览（v2.5.0）

| 指标 | 精度 | 说明 |
|------|------|------|
| 本次（最近已结束 session） | ✅ 精确 | state.db，`msg>5 or in>1000` 过滤 |
| 本次（无已结束 session 时） | ⚠️ 估算 | 字符数×比例，仅作参考 |
| 本次（单轮交换） | ❌ 不可能 | Hermes 不存 per-turn 数据 |
| 本月总消耗 | ✅ 精确 | state.db SUM（包含所有已结束 session） |
| 本月活跃 session | ✅ 精确 | 已在 state.db 实时写入，v2.4.0 修复后计入 |
| 本月用户消息数 | ✅ 精确 | session 文件逐条统计 |
| 本月总花费（参考） | ✅ 精确 | 费率×token |

## 更新记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-05-15 | 2.5.0 | **Critical bug fix**：6个 bug 一并修复——`cur = conn.cursor()` 漏写、SELECT 缺 `started_at` 列、`SESSIONS_DIR` 路径错误、按 mtime 选空 session、`except pass` 静默掩盖错误。Session 选择策略改为：`ORDER BY ended_at DESC LIMIT 15` + 跳过空 session（msg≤5 AND in≤1000）|
| 2026-05-15 | 2.4.0 | **Critical bug fix**：`hermes_scan_monthly` 移除 `WHERE ended_at > 0`，活跃 session（ended_at=0）现已计入月累计。月累计从 62.13M 修正为 ~68M |
| 2026-05-15 | 2.3.0 | **重大修复**：① 输出格式 `本月: X 次` → `本月: X 条用户消息`；② 新增 `hermes_scan_monthly_user_messages()` 从 session 文件统计实际用户消息数；③ session 文件选择逻辑：收集所有 mtime>cutoff 的候选，按 messages 数组长度降序选最多的；④ session 时间戳格式明确；⑤ 估算回退条件改为估算input > state.db input 才用估算值 |
| 2026-05-15 | 2.2.0 | 新增 state-db-session-tracking.md：新增 Solution 1（session file estimation），解决"本次"token不更新问题 |
| 2026-05-12 | 2.0.0 | 新增本次计费token字段；新增实际费用；保留Opus 4.7参考费率双行显示；月累计字段名统一为月累计总消耗 |
| 2026-05-08 | 1.4.0 | 完善文档（费率表、FAQ、维护记录） |
| 2026-05-07 | 1.3.x | 升级为 Opus 4.7 参考费率 |
| 2026-04-06 | 1.0.0 | 初始版本 |

## 参考资料

- `references/feishu-groups.md` — 飞书群组ID、OpenClaw→Hermes Job ID 映射表、迁移检查清单
- `references/state-db-session-tracking.md` — Hermes state.db session token 跟踪限制、\"本次\"数据为什么总是上一个已关闭会话的值