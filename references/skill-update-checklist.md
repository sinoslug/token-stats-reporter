# 技能更新检查清单

## 背景

当需要检查 `token-stats-reporter` 或其他 OpenClaw 迁移技能的更新时，GitHub API 经常遇到 rate limit（403）。此时clawhub.ai 提供了另一条获取途径。

## 检查流程

### Step 1: GitHub 直接访问（可能 403 rate limit）

```bash
curl -s --max-time 10 "https://api.github.com/repos/NousResearch/hermes-agent/git/trees/main?recursive=1" \
  | python3 -c "import sys,json; [print(f['path']) for f in json.load(sys.stdin)['tree'] if 'token-stats' in f['path'].lower()]"
```

### Step 2: clawhub.ai API（备用，2026-05-10 验证有效）

clawhub hosts OpenClaw skills at `https://clawhub.ai/skills/<slug>`.

**查询版本和发布信息：**
```python
import urllib.request
url = "https://clawhub.ai/skills/token-stats-reporter"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=10) as r:
    content = r.read().decode('utf-8', errors='ignore')
# 版本信息在页面 meta 标签中：version=1.5.0
```

**下载完整技能包（ZIP）：**
```python
import urllib.request, zipfile, io
url = "https://wry-manatee-359.convex.site/api/v1/download?slug=token-stats-reporter"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=10) as r:
    zip_data = r.read()
z = zipfile.ZipFile(io.BytesIO(zip_data))
print(z.namelist())  # ['_meta.json', 'scripts/token-show.py', 'SKILL.md']
for name in z.namelist():
    content = z.read(name).decode('utf-8', errors='ignore')
    print(f"=== {name} ===\n{content}")
```

### Step 3: 版本比对逻辑

clawhub 包版本（如 v1.5.0）vs 本地版本：
- 本地 skill 路径：`~/.hermes/skills/openclaw-imports/token-stats-reporter/`
- 查看本地版本：`grep "version:" SKILL.md` 或 `cat _meta.json`
- **重要（2026-05-10 修正）**：clawhub 的 zip 包里的 `scripts/token-show.py` 只支持 OpenClaw JSONL，**不能直接覆盖**本地 Hermes 版本的脚本。正确做法：

1. 下载 clawhub zip 得到 `SKILL.md`（文档更新）和费率参数（v1.5.0 新增 `--model opus4.7/openai`）
2. 将费率参数代码合并进本地 Hermes 版 `token-show.py`（`~/.hermes/...` 版本已支持双底座自动切换）
3. 将合并后的脚本写回 `scripts/token-show.py`
4. SKILL.md 里的费率格式、`--model` 参数名需与脚本实际输出一致（clawhub 文档有时与脚本输出不匹配，如 `本次计费token` 字段是文档残留，脚本早已移除）

### Step 4: 判断是否需要更新

| 场景 | 操作 |
|------|------|
| clawhub 版本 > 本地 SKILL.md 版本 | 更新 `SKILL.md`（文档 + 费率参数说明） |
| 脚本新增功能（如新 --model 选项） | 将 clawhub 脚本的新函数/参数合并进本地 Hermes 脚本 |
| 版本号相近但功能无变化 | 跳过，不覆盖 |

## 已知版本映射

| 来源 | 版本 | 数据底座 | 状态 |
|------|------|----------|------|
| clawhub (2026-05-10) | v1.5.0 | OpenClaw JSONL | 发布最新，含双费率参数 |
| 本地合并脚本 | v1.5.0 (2026-05-10) | Hermes state.db + OpenClaw JSONL（双底座自动） | 当前使用中 |
| 本地 OpenClaw script | 未知 | OpenClaw JSONL | 可能比 v1.5.0 旧 |

**下次检查时**：优先用 Step 2 Python/curl 获取 clawhub 版本，比 GitHub API 更稳定。
