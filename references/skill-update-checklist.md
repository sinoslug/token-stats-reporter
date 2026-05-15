# 技能更新检查清单（Hermes 版）

## ⚠️ 本 skill 从 v2.6.0 起仅适用于 Hermes

OpenClaw 有独立同名脚本：`~/.openclaw/workspace/scripts/token-show.py`（JSONL 版），数据互不相通。

## 更新步骤

### Step 1: GitHub pull（唯一更新源）

```bash
cd ~/.hermes/skills/openclaw-imports/token-stats-reporter
git pull
```

### Step 2: 验证脚本正常运行

```bash
python3 ~/.hermes/skills/openclaw-imports/token-stats-reporter/scripts/token-show.py
```

输出应为：
```
📊 Token: {in} in / {out} out | cacheRead: {cache} | 本次总消耗: {total} | 本次计费token: {billable} | 本月: {user_msgs} 条用户消息 | 月累计总消耗: {monthly} | 本次费用: {fee} | 本月费用: {monthly_fee} | 💰 本次(参考Opus 4.7): {opus_cost} | 💰 本月(参考Opus 4.7): {opus_monthly_cost} | 模型: {model}
```

### Step 3: 检查项

- [ ] 数据源为 `~/.hermes/state.db`（不是 JSONL）
- [ ] SKILL.md 版本号已更新
- [ ] `SESSIONS_DIR` 指向 `~/.hermes/sessions`（不是 `~/.openclaw/...`）

## 版本变更记录

| 日期 | 版本 | 重大变更 |
|------|------|----------|
| 2026-05-15 | 2.6.0 | Hermes-only 明确标注；新增踩坑记录；更新路径改为 GitHub only |
| 2026-05-15 | 2.5.0 | 6个 bug 一起修复（cur=cursor漏写、SELECT缺列、路径错误、session选择策略） |
| 2026-05-15 | 2.4.0 | 移除 ended_at>0 过滤，活跃 session 计入月累计 |
