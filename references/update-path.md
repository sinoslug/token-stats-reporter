# Skill 更新路径（2026-05-15 更新）

## ⚠️ 重要前提

**本 skill（token-stats-reporter）从 v2.6.0 起仅适用于 Hermes 平台。**

- 数据源：`~/.hermes/state.db` + `~/.hermes/sessions/`
- OpenClaw 平台有**独立的同名脚本**：`~/.openclaw/workspace/scripts/token-show.py`（基于 JSONL）
- 两者数据互不相通，clawhub 上的通用版不再适用于此 skill

## 更新源

### 源1：GitHub（推荐，本 skill 的唯一更新源）
```
https://github.com/sinoslug/token-stats-reporter
```
```bash
cd ~/.hermes/skills/openclaw-imports/token-stats-reporter
git pull
```

### 源2：clawhub.ai（❌ 已废弃，不建议使用）
clawhub 上的 token-stats-reporter 是通用版本（含 OpenClaw JSONL 支持），与 Hermes 版本不兼容。
如果 clawhub 有新版本，**不要直接覆盖**，请对比 SKILL.md 和脚本差异后手动合并。
