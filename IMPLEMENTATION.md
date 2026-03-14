# 前瞻性记忆（Prospective Memory）实现总结

## 实现完成的功能

### 1. Perceiver识别"未来意图" ✅
- 在 `server/engine/perceiver.py` 中增加了 `prospective` category
- 新增字段：`trigger_type`, `trigger_value`, `action`
- 支持三种触发器类型：
  - `time`: 时间触发（如"明天早上9点提醒我交报告"）
  - `event`: 事件触发（如"下次聊到减肥时提醒我记录饮食"）
  - `condition`: 条件触发（如"如果BTC跌破6万提醒我"）

### 2. Encoder创建前瞻性记忆节点 ✅
- 在 `server/engine/encoder.py` 中增加了 `_encode_prospective` 方法
- 创建的节点特征：
  - `tags`: ["计划", "提醒"]
  - `zone`: "procedural"
  - `importance`: 8.0（高优先级）
  - `properties`: 包含 trigger_type, trigger_value, action, status, created_from
- 直接写入图谱（不走buffer巩固流程，确保立即可查）
- 同时写入buffer供retriever检索

### 3. 前瞻性记忆检查器 ✅
- 新建 `server/engine/prospective_checker.py`
- 实现了两个核心方法：
  - `check_time_triggers`: 检查时间触发器（北京时间UTC+8）
  - `check_event_triggers`: 检查事件触发器（关键词匹配）
- 触发后自动更新节点status为"completed"

### 4. 集成到hooks ✅
- **session-start hook**: 检查时间触发器，将到期提醒加入pending_reminders
- **before-query hook**: 检查事件触发器，匹配时将提醒注入到context中
- **新增 /hooks/check-prospective 端点**: 供外部cron调用检查时间触发器

### 5. app.py路由 ✅
- 在 `_process_after_response` 中增加了prospective category的路由
- prospective消息跳过evaluator，直接auto-encode（高优先级）
- 将perceiver输出的trigger字段传递给encoder

## 文件修改清单

1. ✅ `server/engine/perceiver.py` - 增加prospective category识别
2. ✅ `server/engine/encoder.py` - 增加_encode_prospective方法
3. ✅ `server/engine/prospective_checker.py` - **新建**检查器类
4. ✅ `server/app.py` - 路由集成 + hooks集成 + 新增API端点

## 测试用例

### 测试1: 时间触发器
```
输入: "明天早上9点提醒我交报告"
预期:
- Perceiver输出: category=prospective, trigger_type=time, trigger_value="2026-03-15T09:00:00+08:00", action="提醒交报告"
- Encoder创建节点: zone=procedural, tags=["计划","提醒"], status=pending
- session-start时检查: 如果当前时间>=触发时间，返回提醒
```

### 测试2: 事件触发器
```
输入: "下次聊到减肥时提醒我记录饮食"
预期:
- Perceiver输出: category=prospective, trigger_type=event, trigger_value="减肥", action="提醒记录饮食"
- Encoder创建节点: status=pending
- before-query时检查: 如果query包含"减肥"，注入提醒到context
```

### 测试3: 条件触发器
```
输入: "如果BTC跌破6万提醒我"
预期:
- Perceiver输出: category=prospective, trigger_type=condition, trigger_value="BTC<60000", action="提醒BTC跌破6万"
- Encoder创建节点: status=pending
- 注：条件触发器需要外部系统监控，本次实现仅创建节点
```

## 技术细节

### 时间解析
- Perceiver的LLM负责将相对时间（"明天"、"下周"）解析为ISO格式datetime
- 使用北京时间（UTC+8）
- 格式示例: "2026-03-15T09:00:00+08:00"

### 状态管理
- `pending`: 待触发
- `completed`: 已触发
- `expired`: 已过期（可选，未实现）

### 触发器更新
- 使用Neo4j的JSON属性更新
- 优先使用APOC函数，fallback到手动JSON解析

## 运行测试

```bash
# 测试Perceiver分类
python3 test_prospective.py

# 启动服务
cd /tmp/bm-prospective
python3 -m uvicorn server.app:app --reload

# 测试API
curl -X POST http://localhost:8000/hooks/check-prospective \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "test", "user_id": "user1"}'
```

## 注意事项

1. **时间触发器依赖外部调度**: 需要配置cron job定期调用 `/hooks/check-prospective` 端点
2. **条件触发器需要外部监控**: 本实现仅创建节点，实际监控需要外部系统
3. **事件触发器使用简单关键词匹配**: 可以后续升级为语义匹配
4. **Neo4j APOC插件**: 如果没有安装APOC，会fallback到手动JSON更新

## 后续优化建议

1. 增加时间触发器的重复模式（每天、每周等）
2. 事件触发器升级为语义匹配（使用embedding相似度）
3. 条件触发器集成外部监控系统（如价格监控、天气监控等）
4. 增加提醒的优先级和紧急程度
5. 支持提醒的延期和取消操作
