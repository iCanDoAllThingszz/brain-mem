# 任务：图谱清洗（Consolidator） + 写入精细化（Encoder）

## 背景
代码在 `/tmp/bm-hygiene/`（分支 feat/graph-hygiene）。

图谱运行一段时间后会积累脏数据：重复实体（"赵禹"/"用户"/"我"）、流水账细节（"苹果"/"600大卡"）、过度抽象的概念节点、孤立节点。需要两方面优化：
1. Consolidator增加图谱清洗步骤（事后治理）
2. Encoder写入时更精细化（事前预防）

**⚠️ 核心原则：防止误杀！宁可留着脏数据，也不能删掉有价值的记忆。**

---

## 功能A：Consolidator图谱清洗

在 `server/engine/consolidator.py` 的巩固流程中增加 `_clean_graph` 步骤。

### Step 1: 用户实体合并（硬规则，不用LLM）
```python
USER_ALIASES = {"我", "用户", "用户本人", "本人"}  # 这些都是用户自己
PRIMARY_USER = "赵禹"  # 主用户节点名

async def _merge_user_aliases(self, tenant_id, user_id):
    """
    查找名称在USER_ALIASES中的节点，把它们的关系转移到PRIMARY_USER节点，然后删除。
    这是硬规则，不需要LLM判断。
    """
```

### Step 2: 相似实体检测（用LLM判断，防误杀）
```python
async def _detect_similar_entities(self, tenant_id, user_id):
    """
    1. 获取所有active节点
    2. 按tags分组，同组内两两比较name的相似度
    3. 对于name高度相似的节点对（编辑距离<3 或 一个是另一个的子串），
       调用LLM判断是否应该合并
    4. LLM返回：merge（合并）/ keep_both（保留两个）/ unsure（不确定，保留）
    5. 只有LLM明确说merge时才合并，unsure时保留（防误杀）
    """
```

LLM prompt:
```
以下两个记忆节点可能是重复的，请判断是否应该合并：

节点A: {name_a} | tags: {tags_a} | summary: {summary_a}
节点B: {name_b} | tags: {tags_b} | summary: {summary_b}

判断规则：
- 如果两者指的是同一个事物/概念/人 → merge（合并到更完整的那个）
- 如果两者虽然名称相似但含义不同 → keep_both
- 如果不确定 → unsure（宁可保留，不要误删）

返回JSON: {"decision": "merge|keep_both|unsure", "keep": "A或B（merge时保留哪个）", "reason": "..."}
```

### Step 3: 孤立节点处理
```python
async def _handle_orphan_nodes(self, tenant_id, user_id):
    """
    查找没有任何关系的节点。
    - 如果是提醒类（tags含"提醒"）→ 连接到用户节点
    - 如果importance < 3 且创建超过7天 → 标记dormant（不删除）
    - 其他 → 保留（可能是新创建的，还没来得及建立关系）
    """
```

### Step 4: 低价值节点降权
```python
async def _demote_low_value_nodes(self, tenant_id, user_id):
    """
    对以下类型的节点降低importance（不删除）：
    - 纯数值节点（name是数字或"XXX大卡"格式）→ importance降到1
    - 纯食物节点（tags含"食物"且不含"偏好"）→ importance降到1
    - 调试/技术细节节点（summary含"调试"/"排查"/"测试"）→ importance降到2
    
    降权后的节点会在下次衰减时自然进入dormant。
    """
```

### 集成到巩固流程
在consolidator的 `consolidate` 方法中，在现有步骤之后增加：
```python
# 图谱清洗（在所有写入完成后执行）
merged = await self._merge_user_aliases(tenant_id, user_id)
similar = await self._detect_similar_entities(tenant_id, user_id)
orphans = await self._handle_orphan_nodes(tenant_id, user_id)
demoted = await self._demote_low_value_nodes(tenant_id, user_id)
```

---

## 功能B：Encoder写入精细化

### 改动1: 硬编码用户别名表
在 `server/engine/encoder.py` 的实体提取prompt中，增加强制规则：

```
CRITICAL: The following words ALL refer to the same person "赵禹":
我, 用户, 用户本人, 本人, 禹哥
NEVER create separate entities for these. Always use "赵禹".
```

### 改动2: 实体类型黑名单
在encoder的 `_encode_cognition` 方法中，提取实体后过滤掉不该进图谱的类型：

```python
ENTITY_BLACKLIST_TAGS = {"食物", "数值", "数据", "调试"}
ENTITY_BLACKLIST_PATTERNS = [
    r"^\d+大卡$",      # 纯热量数值
    r"^\d+kg$",        # 纯体重数值
    r"^\d+公里$",      # 纯距离数值
]

def _filter_entities(self, entities):
    """过滤掉不该进图谱的实体"""
    filtered = []
    for e in entities:
        tags = set(e.get("tags", []))
        name = e.get("name", "")
        # 跳过黑名单tag
        if tags & ENTITY_BLACKLIST_TAGS:
            continue
        # 跳过纯数值
        if any(re.match(p, name) for p in ENTITY_BLACKLIST_PATTERNS):
            continue
        filtered.append(e)
    return filtered
```

### 改动3: 写入前强制图谱查重
在encoder写入buffer前，对每个实体强制检查图谱：

```python
async def _strict_dedup_check(self, entity_name, tenant_id, user_id):
    """
    严格去重：
    1. 精确匹配name
    2. 别名匹配
    3. 子串匹配（"海马体缓冲区" contains "海马体"）
    如果找到高度相似的已有节点，返回该节点（merge），否则返回None（create）
    """
```

---

## 修改文件清单
- `server/engine/consolidator.py` — 增加4个清洗方法
- `server/engine/encoder.py` — 用户别名表 + 实体黑名单 + 严格去重

## 约束
- **防误杀是第一优先级**：不确定时保留，不删除
- 清洗步骤的LLM调用控制在每次巩固最多5次（只对疑似重复的节点对调用）
- 不要修改 retriever.py、perceiver.py、app.py
- 保持向后兼容
- 用户别名表可以配置化（放在config或常量中）

## 测试
修改完成后commit。我会重启服务后发送测试消息验证。
