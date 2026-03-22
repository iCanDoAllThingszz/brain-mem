# Brain Memory OpenClaw Hooks

符合 OpenClaw 官方规范的 hooks 实现，用于集成 brain-memory 系统。

## Hooks 列表

### 1. brain-memory-capture 📥
- **触发时机**: `message:preprocessed`
- **功能**: 捕获预处理后的用户消息，暂存待编码

### 2. brain-memory-recall 🧠
- **触发时机**: `message:preprocessed`
- **功能**: 在查询前注入工作记忆和长期记忆上下文

### 3. brain-memory-encode 💾
- **触发时机**: `message:sent`
- **功能**: 将用户消息和助手响应编码到记忆缓冲区

### 4. brain-memory-session 📝
- **触发时机**: `command:new`
- **功能**: 会话结束时生成摘要并清理工作记忆

## 安装

将 hooks 目录复制到以下位置之一：

```bash
# 工作区级别（推荐）
cp -r hooks <workspace>/hooks/

# 用户级别（跨工作区共享）
cp -r hooks ~/.openclaw/hooks/
```

## 配置

在 OpenClaw 配置中设置环境变量：

```json
{
  "hooks": {
    "internal": {
      "enabled": true,
      "entries": {
        "brain-memory-capture": {
          "enabled": true,
          "env": {
            "BRAIN_SERVER_URL": "http://localhost:8100",
            "BRAIN_TENANT_ID": "default",
            "BRAIN_USER_ID": "yugo"
          }
        },
        "brain-memory-recall": { "enabled": true },
        "brain-memory-encode": { "enabled": true },
        "brain-memory-session": { "enabled": true }
      }
    }
  }
}
```

## 管理

```bash
# 列出所有 hooks
openclaw hooks list

# 启用/禁用
openclaw hooks enable brain-memory-recall
openclaw hooks disable brain-memory-encode

# 查看详情
openclaw hooks info brain-memory-recall
```

## 验证 Hooks 是否正常工作

### 1. 检查 hooks 是否被识别

```bash
# 查看所有已发现的 hooks
openclaw hooks list

# 应该看到 4 个 brain-memory hooks
openclaw hooks list --eligible
```

### 2. 检查 brain-memory 服务状态

```bash
# 确认服务器运行正常
curl http://localhost:8100/health

# 预期返回: {"status": "ok"}
```

### 3. 测试各个 hook 功能

**测试 capture + encode（消息捕获和编码）：**
```bash
# 1. 发送一条测试消息给 agent
# 2. 查看服务器日志，应该看到 after-response 调用
curl http://localhost:8100/logs?n=10
```

**测试 recall（记忆召回）：**
```bash
# 发送查询，检查是否注入了 <working-memory> 或 <retrieved-memories>
# 在 agent 响应中应该能看到相关上下文
```

**测试 session（会话管理）：**
```bash
# 1. 执行 /new 命令
# 2. 查看日志，应该看到 session-end 调用和 "Session summary generated" 消息
```

### 4. 查看 OpenClaw 日志

```bash
# 检查 hook 执行日志
tail -f ~/.openclaw/logs/commands.log

# 应该看到类似：
# [brain-memory-recall] ...
# [brain-memory-encode] ...
# [brain-memory-session] ...
```

### 5. 常见问题排查

**Hooks 未被加载：**
- 检查目录结构是否正确（每个 hook 需要 HOOK.md + handler.ts）
- 确认 hooks 配置中 `enabled: true`
- 重启 OpenClaw Gateway

**服务器连接失败：**
- 确认 brain-memory 服务运行在 8100 端口
- 检查环境变量配置是否正确
- 查看网络连接和防火墙设置

**记忆未注入：**
- 确认 brain-memory-recall hook 已启用
- 检查是否过滤了系统消息（cron、subagent）
- 查看服务器日志确认 API 调用成功