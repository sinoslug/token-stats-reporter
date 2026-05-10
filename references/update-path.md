# Skill 更新路径（2026-05-10）

## 问题
GitHub API 有频率限制（403 Rate Limit），直接 `api.github.com` 可能失败。

## 可行的更新路径

### 路径1：clawhub.ai 下载（推荐，2026-05-10 验证可用）
```
https://wry-manatee-359.convex.site/api/v1/download?slug=<skill-slug>
```
返回 zip 包，内含 `_meta.json`、`SKILL.md`、`scripts/` 等文件。

**注意**：clawhub 上的版本 `scripts/token-show.py` 只读 OpenClaw JSONL，不支持 Hermes state.db。
更新时需要将 clawhub 的新功能（如 `--model opus4.7/openai` 费率参数）合并进本地双底座版脚本，
不要直接用 clawhub 脚本覆盖。详见 `references/skill-update-checklist.md` Step 3。

### 路径2：GitHub API（受频率限制）
```
https://api.github.com/repos/<owner>/<repo>/git/trees/main?recursive=1
```
需要 `Authorization: token <gh_token>` header 才能突破匿名限制。

### 路径3：raw.githubusercontent.com（受频率限制）
```
https://raw.githubusercontent.com/<owner>/<repo>/main/<path>
```

## 验证命令
```bash
# 下载并验证
python3 ~/.hermes/skills/openclaw-imports/token-stats-reporter/scripts/token-show.py
cat ~/.hermes/skills/openclaw-imports/token-stats-reporter/_meta.json
```

## SKILL.md 人工检查清单
下载新版本后，检查以下字段是否与脚本实际输出一致：
- [ ] 输出格式模板（`📊 Token: ...`）
- [ ] `--model` 参数名（clawhub 版本用 `opus4.7` / `openai`）
- [ ] 字段名（无 `本次计费token`，用 `本次总消耗`）
- [ ] 数据源是否包含 Hermes（`~/.hermes/state.db`）
- [ ] ZhangQin 必加 token 统计的特殊要求
