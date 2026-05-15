# 嫒小虾飞书群组配置（稳定常量）

> 跨会话不变的事实，无需每次确认，直接使用。

## 飞书群组 ID

| 用途 | chat_id |
|------|---------|
| **股票监控/利润增速群** | `oc_00d283ede2f3f972b2e8137102aae3b2` |
| 热点新闻群 | `oc_6b7f2481082e778eb4172dfa01347d45` |

## 飞书个人 ID

| 用途 | open_id |
|------|---------|
| 主人（张钦） | `ou_a8ac19dda72aa049c926f5095f9c6984` |

## OpenClaw Cron Jobs → Hermes Job ID 映射

| 任务名 | OpenClaw ID | Hermes Job ID | 状态 |
|--------|-------------|---------------|------|
| AI模型充值提醒 | `ac9ba226-279f-44da-bbf4-34493c2662c9` | `752e03322a35` | ✅ 已迁移 |
| 股票持仓定时汇报-半点 | `c8f78eb2-efe6-40c9-90e4-407a677bc685` | `01813b93de07` | ✅ 已迁移 |
| 每日利润增速汇报 | `b41c7fa6-7e8d-43eb-82d6-f34b1f08a0f6` | `998ef4fc14f0` | ✅ 已迁移 |
| 每日热点搜集-权威媒体版 | `e939f073-1ca4-4e4f-ba2d-15f28b5f76ed` | `5a79d0b6a090` | ✅ 已迁移 |
| WiFi评估进展-每周三五提醒 | `2890d46b-35de-4862-86dc-2fa4ccd08f65` | `98b1f19618c9` | ✅ 已迁移 |
| 跨会话上下文同步→微信 | — | `5b5df270607f` | ❌ 已删除 |
| 各群记忆汇总 | `82ceb78b-7cd4-4ec3-b968-19b8eea82298` | — | ❌ 未迁移 |
| Token使用记录 | `1fd74c00-3977-4e35-a0b8-2d689003be77` | — | ❌ 未迁移 |
| 薛斯通道条件触发预警 | `e086a669-1a56-48c1-989f-374bfa2d3701` | — | ❌ 未迁移 |

## 脚本路径（OpenClaw 工作区）

| 脚本 | 路径 |
|------|------|
| 股票监控主脚本 | `/Users/slug/.openclaw/workspace/xs_monitor.py` |
| 利润增速报告 | `/Users/slug/.openclaw/workspace/profit_growth_report.py` |
| 热点新闻搜集 | `/Users/slug/.openclaw/workspace/scripts/hot_news_cron_lightweight.py` |
| Token 统计（Hermes用） | `~/.hermes/skills/openclaw-imports/token-stats-reporter/scripts/token-show.py` |
| Token 统计（OpenClaw用） | `/Users/slug/.openclaw/workspace/scripts/token-show.py` |

## 迁移检查清单

When migrating OpenClaw cron jobs to Hermes:
1. ✅ 原始配置：`~/.openclaw/cron/jobs.json`
2. ✅ 检查 deliver target 是否有变化（**热点群 ID 2026-05-14 已变更**）
3. ✅ 更新 prompt 中的脚本路径（OpenClaw path → 保持不变，因为脚本还在原位）
4. ✅ 附加 `skills: ["token-stats-reporter"]`
5. ✅ verify 调度表达式是否兼容 Hermes cron 格式

## ⚠️ 跨底座发送飞书消息的认证陷阱（2026-05-14 实录）

**问题现象：**
- OpenClaw Gateway API (`47.253.204.91:12537`, token: `cd23b5d4b689a0cfd5c76ae83dca43e4`) 在 OpenClaw agent 内运行正常
- 但从 Hermes cron job 调用时返回 `401 Unauthorized`
- 两个底座的 Gateway token 互相不通用

**影响范围：**
- 所有需要从 Hermes → 飞书群发送消息的 cron job
- 包括但不限于：热点新闻发送、利润增速报告、股票监控预警

**已知的成功方案：**

方案A（推荐）：直接调用飞书开放平台 API，不依赖 Gateway token
```python
import subprocess, json

# 1. 获取 tenant_access_token（env变量FEISHU_APP_ID和FEISHU_APP_SECRET在cron容器中同样可用）
token_result = subprocess.run([
    'curl', '-s', '-X', 'POST',
    'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
    '-H', 'Content-Type: application/json',
    '-d', json.dumps({
        "app_id": "cli_a9309b66b3385cd5",
        "app_secret": "mzD4BOEsnlH6yVilw0Z2zcPMNtxVaMbV"
    })
], capture_output=True, text=True)
token = json.loads(token_result.stdout)['tenant_access_token']

# 2. 发送消息到任意chat_id
payload = {
    "receive_id": "oc_00d283ede2f3f972b2e8137102aae3b2",
    "msg_type": "text",
    "content": json.dumps({"text": content})
}
subprocess.run([
    'curl', '-s', '-X', 'POST',
    'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id',
    '-H', f'Authorization: Bearer {token}',
    '-H', 'Content-Type: application/json',
    '-d', json.dumps(payload)
], capture_output=True, text=True)
```

方案B：如果 cron job 配置了 `"delivery": {"mode": "announce", "channel": "feishu", "to": "chat:oc_xxx"}`，由 Hermes 系统自动处理发送

方案C：消息写入 `/tmp/xs_feishu_message.txt`，由独立发送 cron 读取并发送

**教训（2026-05-14 实录）：**
调用 Gateway API (`47.253.204.91:12537`) 从 Hermes → 飞书会 401 失败，两个底座的 Gateway token 互不通用。
直接用飞书开放平台 API + bot 凭证，✅ 完全成功。env变量 `FEISHU_APP_ID`, `FEISHU_APP_SECRET` 在 cron 容器中同样可用。
