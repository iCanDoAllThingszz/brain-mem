# encoder.py - 编码器引擎

## 文件整体功能

`encoder.py` 是 Brain Memory Service 的记忆编码器，对应人脑的**海马体**。它负责：

1. **记忆编码**：将原始消息转换为结构化记忆单元并写入缓冲区
2. **实体生命周期管理**：实体提取、tag归属、去重、关系构建
3. **多类别编码**：支持认知、日志、重固化、前瞻记忆、遗忘等多种编码路径
4. **语义去重**：混合关键词和 LLM 判断，避免重复编码
5. **干扰检测**：检测新旧信息之间的矛盾或状态更新
6. **会话总结**：生成结构化会话摘要

---

## 核心类

### `Encoder`

**功能**：记忆编码器 — 记忆系统的海马体

**初始化参数**：
- `graph` (GraphStore)：图数据库存储
- `tag_dict` (TagDict)：标签字典
- `buffer` (EncoderBuffer)：编码缓冲区

**方法**：
- `encode_message()` → 编码消息到记忆单元
- `generate_session_summary()` → 生成会话总结
- 内部方法：`_encode_cognition()`, `_encode_log()`, `_encode_reconsolidation()`, `_encode_prospective()`, `_encode_forget()`

---

## 核心方法

### 1. `encode_message(message, evaluation, tenant_id, user_id, session_id, working_memory) -> Dict[str, Any]`

**功能**：编码消息到结构化记忆单元

**参数**：
- `message` (str)：消息文本
- `evaluation` (Dict[str, Any])：评估结果（包含 category、target_entity 等）
- `tenant_id` (str)：租户 ID
- `user_id` (str)：用户 ID
- `session_id` (str)：会话 ID
- `working_memory` (Optional[Dict[str, Any]])：工作记忆上下文

**返回**：
- 编码结果字典，包含 `type`、`entities`、`relations`、`importance` 等

**流程**：
```
1. 根据 category 路由到不同的编码流程：
   - "cognition" → _encode_cognition()
   - "log_*" → _encode_log()
   - "reconsolidation" → _encode_reconsolidation()
   - "prospective" → _encode_prospective()
   - "forget" → _encode_forget()
2. 返回编码结果
```

**调用链路**：
- `app.py` `_process_after_response()` → `Encoder.encode_message()`

---

### 2. `_encode_cognition(message, evaluation, tenant_id, user_id, session_id, working_memory) -> Dict[str, Any]`

**功能**：认知编码流程（v2）

**流程**：
```
1. 语义去重检查（混合方法）：
   a. 读取最近 20 条缓冲区记录
   b. 调用 _is_semantic_duplicate() 检查
   c. 如果重复，跳过编码
2. 粗提取实体和关系：
   a. 调用 _extract_raw() 提取原始实体和关系
   b. 调用 _smart_resolve_entities() 智能过滤实体
3. 解析每个实体：
   a. 调用 _resolve_entity() 进行 tag归属 + 去重 + 关系构建
   b. 收集所有新关系
4. 组装记忆单元：
   a. 计算重要性分数
   b. 生成嵌入向量
   c. 写入缓冲区
5. 返回编码结果
```

**关键逻辑**：

#### 语义去重（混合方法）
```
1. 快速关键词重叠过滤（70%+ 重叠 → 重复）
2. 边界情况（40-70% 重叠）→ LLM 判断
3. 精确匹配 → 重复
```

#### 实体智能过滤
```
1. 对每个候选实体，查找图中相关实体
2. 调用 LLM 决策：
   - "create"：新实体，不在图中
   - "merge"：与已有实体相同，合并
   - "update"：为已有实体添加新信息
   - "skip"：不值得添加（纯数字、食物、通用概念等）
3. 只保留非 "skip" 的实体
```

#### 实体解析
```
1. 严格去重检查（精确名称、别名、子串匹配）
2. Tag归属：查 tag 字典，确定实体应归入哪个 tag
3. 同类检索：按 tag 去图谱检索同类实体
4. LLM 判断：create/merge/update + 关系构建（一次调用）
5. 干扰检测：检查是否存在矛盾或状态更新
```

**调用链路**：
- `encode_message()` → `_encode_cognition()` → `_is_semantic_duplicate()` → `_extract_raw()` → `_smart_resolve_entities()` → `_resolve_entity()` → `_check_interference()`

---

### 3. `_encode_log(message, evaluation, category, tenant_id, user_id, session_id) -> Dict[str, Any]`

**功能**：日志编码流程（v3）

**流程**：
```
1. 提取 target_entity（如"减肥计划"）
2. 调用 LogWriter.write_log() 写入日志文件并更新图索引
3. 写入缓冲区索引记录（便于检索器发现）
4. 返回编码结果
```

**返回**：
```python
{
  "type": "log",
  "category": "log_diet",
  "target_entity": "减肥计划",
  "file_path": "/path/to/log/file",
  "log_date": "2026-03-17",
  "target_entity_updated": True,
  "session_id": "uuid",
  "timestamp": "2026-03-17T14:30:45"
}
```

**调用链路**：
- `encode_message()` → `_encode_log()` → `LogWriter.write_log()` → `EncoderBuffer.write()`

---

### 4. `_encode_reconsolidation(message, evaluation, tenant_id, user_id, session_id) -> Dict[str, Any]`

**功能**：重固化编码流程（记忆更新）

**流程**：
```
1. 提取 target_entity 和 correction_type
2. 查找目标节点（按名称或模糊匹配）
3. 如果节点不存在，自动创建
4. 根据 correction_type 准备更新：
   - "correct"：事实纠正，更新 summary 和 content
   - "supplement"：补充信息，追加到 content
   - "reframe"：情感重新诠释，更新 emotional_tag
5. 记录纠正历史到 properties._correction_history
6. 增加版本号
7. 更新节点
8. 返回编码结果
```

**返回**：
```python
{
  "type": "reconsolidation",
  "node_id": "uuid",
  "target_entity": "跳槽计划",
  "correction_type": "supplement",
  "nodes_updated": 1,
  "old_version": 1,
  "new_version": 2,
  "session_id": "uuid",
  "timestamp": "2026-03-17T14:30:45"
}
```

**调用链路**：
- `encode_message()` → `_encode_reconsolidation()` → `GraphStore.find_nodes_by_name()` → `GraphStore.update_node()`

---

### 5. `_encode_prospective(message, evaluation, tenant_id, user_id, session_id) -> Dict[str, Any]`

**功能**：前瞻记忆编码流程（提醒/意图）

**流程**：
```
1. 提取 trigger_type、trigger_value、action
2. 创建记忆节点：
   - name: "提醒: {action}"
   - tags: ["计划", "提醒"]
   - zone: "procedural"
   - importance: 8.0（高优先级）
   - properties: {trigger_type, trigger_value, action, status: "pending"}
3. 直接写入图数据库（绕过缓冲区/巩固，立即可用）
4. 写入缓冲区索引记录（便于检索器发现）
5. 返回编码结果
```

**返回**：
```python
{
  "type": "prospective",
  "node_id": "uuid",
  "trigger_type": "time",
  "trigger_value": "2026-03-15T09:00:00+08:00",
  "action": "提醒交报告",
  "status": "pending",
  "session_id": "uuid",
  "timestamp": "2026-03-17T14:30:45"
}
```

**调用链路**：
- `encode_message()` → `_encode_prospective()` → `GraphStore.create_node()` → `EncoderBuffer.write()`

---

### 6. `_encode_forget(message, evaluation, tenant_id, user_id, session_id) -> Dict[str, Any]`

**功能**：遗忘编码流程（抑制记忆）

**流程**：
```
1. 提取 target_entity
2. 查找目标节点（按名称或模糊匹配）
3. 如果节点不存在，返回 skipped
4. 抑制所有匹配节点：
   - status: "suppressed"
   - retrieval_strength: 0.0
   - properties._suppressed_at: 时间戳
   - properties._suppressed_reason: 原因
   - properties._suppressed_session: 会话 ID
5. 返回编码结果
```

**返回**：
```python
{
  "type": "forget",
  "target_entity": "张三",
  "nodes_suppressed": 2,
  "suppressed_ids": ["uuid1", "uuid2"],
  "session_id": "uuid",
  "timestamp": "2026-03-17T14:30:45"
}
```

**调用链路**：
- `encode_message()` → `_encode_forget()` → `GraphStore.find_nodes_by_name()` → `GraphStore.update_node()`

---

### 7. `generate_session_summary(conversation_history, tenant_id, user_id, session_id) -> Dict[str, Any]`

**功能**：生成结构化会话摘要

**参数**：
- `conversation_history` (List[Dict[str, Any]])：对话历史
- `tenant_id`, `user_id`, `session_id` (str)：标识符

**返回**：
```python
{
  "id": "uuid",
  "type": "session_summary",
  "session_id": "uuid",
  "tenant_id": "default",
  "user_id": "yugo",
  "topics": ["话题1", "话题2"],
  "key_conclusions": ["结论1"],
  "pending_points": ["未解决1"],
  "emotional_arc": "positive|negative|neutral|mixed",
  "summary_text": "2-3句话的摘要",
  "importance": 7.0,
  "timestamp": "2026-03-17T14:30:45",
  "archived": False
}
```

**流程**：
```
1. 格式化对话历史（最后 50 条消息）
2. 调用 LLM 生成摘要
3. 组装摘要单元
4. 写入缓冲区
5. 返回摘要单元
```

**调用链路**：
- `app.py` `_process_session_end()` → `Encoder.generate_session_summary()` → `call_llm_json()` → `EncoderBuffer.write()`

---

## 内部辅助方法

### `_is_semantic_duplicate(message, recent_units) -> bool`

**功能**：混合语义去重检查

**流程**：
```
1. 快速关键词重叠过滤：
   - 精确匹配 → 重复
   - 70%+ 重叠 → 重复
   - 40-70% 重叠 → 边界情况
2. 边界情况 LLM 判断：
   - 调用 _llm_similarity_check()
   - 返回是否重复
3. 其他情况 → 不重复
```

**调用链路**：
- `_encode_cognition()` → `_is_semantic_duplicate()` → `_tokenize_chinese()` → `_llm_similarity_check()`

---

### `_smart_resolve_entities(raw_entities, tenant_id, user_id, message_context) -> List[Dict[str, Any]]`

**功能**：LLM 驱动的智能实体解析

**流程**：
```
1. 对每个候选实体，查找图中相关实体：
   - 按名称搜索
   - 按模糊匹配搜索
   - 按标签搜索
2. 构建 LLM 提示词（候选实体 + 已有实体）
3. 调用 LLM 决策：
   - "create"：新实体
   - "merge"：合并到已有实体
   - "update"：更新已有实体
   - "skip"：不值得添加
4. 只保留非 "skip" 的实体
5. 返回过滤后的实体列表
```

**skip 规则**：
- 纯数字（"600大卡"、"90kg"、"5公里"）
- 具体食物（"苹果"、"牛肉面"）— 属于饮食日志
- 通用概念（"地球"、"太阳"）— LLM 已知
- 调试/测试临时信息
- 代词（"我"、"用户"）— 如果用户节点已存在

**调用链路**：
- `_encode_cognition()` → `_smart_resolve_entities()` → `GraphStore.find_nodes_by_name()` → `call_llm_json()`

---

### `_strict_dedup_check(entity_name, tenant_id, user_id) -> Optional[Node]`

**功能**：严格去重检查

**检查项**：
1. 精确名称匹配
2. 别名匹配
3. 子串匹配（如"海马体缓冲区"包含"海马体"）

**返回**：
- 如果找到已有节点，返回节点对象
- 否则返回 None

**调用链路**：
- `_resolve_entity()` → `_strict_dedup_check()` → `GraphStore.find_nodes_by_name()` → `GraphStore.find_nodes_by_alias()` → `GraphStore.find_active_nodes()`

---

### `_extract_raw(message, working_memory) -> Dict[str, Any]`

**功能**：LLM 粗提取实体和关系

**返回**：
```python
{
  "entities": [
    {"name": "实体名称", "tags": ["标签1"], "zone": "semantic", "summary": "一句话描述"}
  ],
  "relations": [
    {"from_name": "A", "to_name": "B", "type": "关系类型", "description": "关系描述"}
  ]
}
```

**提取规则**：
- 提取命名实体：人物、组织、地点、概念、事件、决策、计划
- 只提取与用户个人相关的实体
- 跳过通用常识（除非用户与之有个人联系）
- **代词解析**：将"我"、"用户"、"本人"替换为用户真实姓名
- **名称变体识别**：注意全名 vs 昵称、称谓+姓名
- **关系提取要全面**：明确关系 + 隐含关系

**调用链路**：
- `_encode_cognition()` → `_extract_raw()` → `call_llm_json()`

---

### `_resolve_entity(raw_entity, tenant_id, user_id) -> Dict[str, Any]`

**功能**：对单个实体执行完整的解析流程

**流程**：
```
1. 严格去重检查
2. Tag归属：查 tag 字典，确定实体应归入哪个 tag
3. 同类检索：按 tag 去图谱检索同类实体
4. LLM 判断：create/merge/update + 关系构建（一次调用）
5. 干扰检测：检查是否存在矛盾或状态更新
```

**返回**：
```python
{
  "action": "merge" | "update" | "create",
  "final_name": "实体名称",
  "resolved_tags": ["标签1", "标签2"],
  "existing_id": "uuid" | None,
  "aliases_to_add": ["别名1"],
  "summary_update": "更新后的摘要" | None,
  "properties_update": {},
  "new_relations": [
    {"from_name": "A", "to_name": "B", "type": "关系类型", "description": "关系描述"}
  ],
  "reason": "为什么选择这个 action"
}
```

**调用链路**：
- `_encode_cognition()` → `_resolve_entity()` → `_strict_dedup_check()` → `TagDict.find_similar()` → `GraphStore.find_active_nodes()` → `call_llm_json()` → `_check_interference()`

---

### `_check_interference(existing_id, new_entity, resolution, tenant_id, user_id) -> Optional[Dict[str, Any]]`

**功能**：检测新旧信息之间的干扰

**流程**：
```
1. 获取已有节点
2. 比较旧摘要和新摘要
3. 调用 LLM 判断关系：
   - "contradiction"：矛盾（如"在A工作" vs "在B工作"）
   - "state_update"：状态更新（如"加入公司" → "离开公司"）
   - "complement"：补充信息
   - "duplicate"：重复信息
4. 根据关系类型处理：
   - contradiction：标记冲突
   - state_update：标记旧关系为无效，降低检索强度
   - complement/duplicate：无操作
5. 返回干扰处理指令
```

**返回**：
```python
{
  "properties_update": {
    "_conflict_with": "uuid",
    "_conflict_old_summary": "旧摘要",
    "_conflict_new_summary": "新摘要",
    "_conflict_detected_at": "2026-03-17T14:30:45"
  },
  "relations_to_invalidate": ["WORKS_AT", "LOCATED_IN"]
}
```

**调用链路**：
- `_resolve_entity()` → `_check_interference()` → `GraphStore.get_node()` → `call_llm_json()` → `GraphStore.update_node()`

---

### `_compute_importance(evaluation) -> float`

**功能**：计算 0-10 重要性分数

**公式**：
```python
importance = task_relevance * 0.5 + emotional_intensity * 0.3 + novelty * 0.2
```

**调用链路**：
- `_encode_cognition()` → `_compute_importance()`

---

### `_extract_emotion(message) -> Dict[str, Any]`

**功能**：从消息中提取情绪标签

**返回**：
```python
{
  "type": "joy" | "sadness" | "anger" | "fear" | "surprise" | "neutral",
  "intensity": 0-10
}
```

**调用链路**：
- `_encode_reconsolidation()` → `_extract_emotion()` → `call_llm_json()`

---

## 系统提示词

### `_EXTRACT_SYSTEM`（粗提取）

**功能**：从消息中提取原始实体和关系

**关键规则**：
- 提取命名实体：人物、组织、地点、概念、事件、决策、计划
- 只提取与用户个人相关的实体
- **代词解析**：将"我"、"用户"、"本人"替换为用户真实姓名
- **名称变体识别**：注意全名 vs 昵称、称谓+姓名
- **关系提取要全面**：明确关系 + 隐含关系

---

### `_RESOLVE_ENTITY_SYSTEM`（实体解析）

**功能**：决定如何处理新提取的实体

**决策类型**：
1. **merge（合并）**：新实体与已有实体是同一个
2. **update（更新）**：新实体为已有实体添加了新信息
3. **create（创建）**：新实体是真正的新实体

**关键规则**：
- 对 "create" 保持保守，优先 "merge" 或 "update"
- **名称匹配规则**：子串、昵称、称谓差异 → 优先 "merge"
- **关系上下文**：共享相同关系/角色 → 优先 "merge"

---

### `_SUMMARY_SYSTEM`（会话摘要）

**功能**：将对话总结为简洁的结构化摘要

**返回格式**：
```json
{
  "topics": ["话题1", "话题2"],
  "key_conclusions": ["结论1"],
  "pending_points": ["未解决1"],
  "emotional_arc": "positive|negative|neutral|mixed",
  "summary_text": "2-3句话的摘要"
}
```

---

## 调用关系图

```
encoder.py
└── Encoder
    ├── encode_message()
    │   ├── _encode_cognition()
    │   │   ├── _is_semantic_duplicate()
    │   │   │   ├── _tokenize_chinese()
    │   │   │   └── _llm_similarity_check()
    │   │   ├── _extract_raw()
    │   │   ├── _smart_resolve_entities()
    │   │   ├── _resolve_entity()
    │   │   │   ├── _strict_dedup_check()
    │   │   │   └── _check_interference()
    │   │   └── _compute_importance()
    │   ├── _encode_log()
    │   ├── _encode_reconsolidation()
    │   │   └── _extract_emotion()
    │   ├── _encode_prospective()
    │   └── _encode_forget()
    └── generate_session_summary()
```

**被调用者**：
```
app.py
├── _process_after_response()
│   └── Encoder.encode_message()
└── _process_session_end()
    └── Encoder.generate_session_summary()
```

---

## 重要注意事项

1. **多类别编码**：支持 cognition、log、reconsolidation、prospective、forget 五种编码路径
2. **语义去重**：混合关键词和 LLM 判断，避免重复编码
3. **智能实体过滤**：LLM 驱动的 create/merge/update/skip 决策，防止图膨胀
4. **严格去重**：精确名称、别名、子串三重检查
5. **干扰检测**：检测矛盾和状态更新，标记冲突或降低检索强度
6. **前瞻记忆立即可用**：直接写入图数据库，绕过缓冲区/巩固
7. **遗忘机制**：通过抑制节点实现，不删除数据
8. **重固化支持**：记录纠正历史，增加版本号
9. **嵌入向量生成**：异步生成缓冲区单元的嵌入向量
10. **会话总结**：结构化摘要，包含话题、结论、待办、情绪弧线

---

## 优化历史

- **v2**：实体生命周期管理 — tag归属 + 去重 + 关系构建 合并为单次 LLM 调用
- **v3**：多类别编码 — 支持 cognition、log、reconsolidation、prospective、forget
- **2026-03-17**：提示词中文化，加强名称变体识别和关系提取规则
