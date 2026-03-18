# tag_dict.py - 标签字典管理

## 文件整体功能

`tag_dict.py` 实现了基于 JSON 文件的标签字典管理系统，提供标签的创建、查找、标准化、弃用等功能，支持语义相似度匹配（LLM 辅助）。

**核心职责：**
- 管理标签的规范化名称、别名、描述、使用计数
- 提供标签的精确匹配、模糊匹配、语义匹配
- 支持标签弃用和替换机制
- 预置 15 个核心标签
- 标签标准化（将候选标签映射到规范标签）
- 只增不删（append-only）的持久化策略

---

## 核心常量

### 预置核心标签

```python
_CORE_TAGS = [
    "人物", "组织", "地点", "项目", "概念",
    "事件", "决策", "计划", "技能", "情感",
    "健康", "财务", "技术", "教训", "作品",
]
```

**说明：**
- 系统初始化时自动创建这 15 个核心标签
- 覆盖常见的记忆分类维度
- 核心标签不可删除，只能弃用

---

### LLM 系统提示词

```python
_FIND_SIMILAR_SYSTEM = """
You are a tag taxonomy manager. Given a new tag and a list of existing tags, \
decide whether the new tag should be merged into an existing tag or kept as new.

Rules:
- If the new tag is semantically equivalent or a near-synonym of an existing tag, \
  return the existing tag name.
- If the new tag is a sub-concept that clearly belongs under an existing tag, \
  return the existing tag name.
- If the new tag is genuinely distinct and adds value, return null.

Return ONLY valid JSON: {"match": "<existing_tag_name>"} or {"match": null}
"""
```

**说明：**
- 用于 LLM 辅助的语义相似度匹配
- 返回格式：`{"match": "现有标签名"}` 或 `{"match": null}`

---

## 数据模型

### Tag 类

```python
class Tag(BaseModel):
    name: str  # 规范标签名（创建后不可变）
    aliases: List[str] = []  # 别名列表
    description: str = ""  # 人类可读的描述
    usage_count: int = 0  # 使用次数
    created_at: str  # 创建时间（ISO 格式）
    status: str = "active"  # 状态：active/deprecated
    preferred_replacement: Optional[str] = None  # 弃用后的替换标签
```

**字段说明：**
- `name`: 唯一标识，创建后不可修改
- `aliases`: 同义词列表，用于模糊匹配
- `description`: 标签含义说明
- `usage_count`: 统计标签使用频率
- `created_at`: 创建时间戳
- `status`: 
  - `"active"`: 活跃标签
  - `"deprecated"`: 已弃用标签
- `preferred_replacement`: 弃用标签的推荐替换（必须是活跃标签）

---

## 类：TagDict

### 作用
只增不删的标签字典，基于 JSON 文件持久化，支持标签的创建、查找、标准化、弃用。

### 初始化

```python
def __init__(self, path: str) -> None
```

**参数：**
- `path` (str): JSON 文件路径

**功能：**
1. 保存文件路径
2. 初始化内部标签字典 `_tags`
3. 调用 `_load()` 加载现有标签
4. 调用 `_ensure_core_tags()` 预置核心标签

**调用链路：**
- 被：服务启动时实例化
- 调用：`_load()`, `_ensure_core_tags()`

---

## 核心方法

### 1. get_tag() - 精确查找

```python
def get_tag(self, name: str) -> Optional[Tag]
```

**功能：**
根据标签名精确查找标签。

**参数：**
- `name` (str): 标签名

**返回值：**
- Tag 对象，如果不存在则返回 None

**调用链路：**
- 被：标签查询时调用
- 调用：无

**代码示例：**
```python
tag_dict = TagDict("/path/to/tags.json")
tag = tag_dict.get_tag("人物")
if tag:
    print(tag.usage_count)
```

---

### 2. find_similar() - 语义相似度匹配

```python
async def find_similar(self, name: str) -> Optional[Tag]
```

**功能：**
查找语义相似的标签，使用多层匹配策略。

**参数：**
- `name` (str): 候选标签名

**返回值：**
- 最匹配的 Tag 对象，如果没有相似标签则返回 None

**匹配策略（优先级从高到低）：**
1. **精确匹配**：`name` 完全相同
2. **不区分大小写匹配**：`name.lower()` 相同
3. **别名匹配**：`name` 在某个标签的 `aliases` 中
4. **子串包含**：`name` 包含在某个标签名中，或反之
5. **LLM 语义匹配**：调用 LLM 判断语义相似度

**关键逻辑：**
```python
# 1. 精确匹配
if name in self._tags:
    return self._tags[name]

# 2. 不区分大小写
lower = name.lower()
for tag in self._tags.values():
    if tag.name.lower() == lower:
        return tag

# 3. 别名匹配
for tag in self._tags.values():
    if any(a.lower() == lower for a in tag.aliases):
        return tag

# 4. 子串包含
for tag in self._tags.values():
    if lower in tag.name.lower() or tag.name.lower() in lower:
        return tag

# 5. LLM 语义匹配
active_tags = [t.name for t in self._tags.values() if t.status == "active"]
result = await call_llm_json(_FIND_SIMILAR_SYSTEM, user_prompt, temperature=0.1)
match_name = result.get("match")
if match_name and match_name in self._tags:
    return self._tags[match_name]

return None
```

**调用链路：**
- 被：`standardize()` 调用
- 调用：`call_llm_json()`（来自 `llm_client.py`）

**代码示例：**
```python
tag_dict = TagDict("/path/to/tags.json")
similar = await tag_dict.find_similar("人")
if similar:
    print(f"'{similar.name}' 与 '人' 相似")
```

---

### 3. add_tag() - 添加标签

```python
def add_tag(self, name: str, description: str = "") -> Tag
```

**功能：**
添加新标签，如果已存在则返回现有标签。

**参数：**
- `name` (str): 标签名
- `description` (str): 标签描述（可选）

**返回值：**
- Tag 对象（新创建或已存在）

**关键逻辑：**
1. 检查标签是否已存在
2. 如果存在，返回现有标签
3. 如果不存在，创建新标签并保存到文件

**调用链路：**
- 被：`standardize()` 调用
- 调用：`_save()`

**代码示例：**
```python
tag_dict = TagDict("/path/to/tags.json")
tag = tag_dict.add_tag("新标签", "这是一个新标签")
print(tag.name)  # 输出：新标签
```

---

### 4. deprecate_tag() - 弃用标签

```python
def deprecate_tag(self, name: str, replacement: str) -> None
```

**功能：**
将标签标记为弃用，并指定替换标签。

**参数：**
- `name` (str): 要弃用的标签名
- `replacement` (str): 替换标签名（必须已存在且为活跃状态）

**异常：**
- `KeyError`: 标签不存在
- `ValueError`: 替换标签不存在

**关键逻辑：**
1. 验证两个标签都存在
2. 将 `name` 标签的 `status` 设为 `"deprecated"`
3. 设置 `preferred_replacement` 为 `replacement`
4. 保存到文件

**调用链路：**
- 被：标签管理时调用
- 调用：`_save()`

**代码示例：**
```python
tag_dict = TagDict("/path/to/tags.json")
tag_dict.deprecate_tag("旧标签", "新标签")
```

---

### 5. standardize() - 标准化标签列表

```python
async def standardize(self, candidate_tags: List[str]) -> List[str]
```

**功能：**
将候选标签列表标准化为规范标签列表（异步，可能调用 LLM）。

**参数：**
- `candidate_tags` (List[str]): 候选标签列表

**返回值：**
- 规范标签名列表

**标准化规则：**
1. **精确匹配活跃标签**：直接使用
2. **匹配弃用标签**：替换为 `preferred_replacement`
3. **找到相似标签**：使用相似标签（包括 LLM 匹配）
4. **无匹配**：添加为新标签

**关键逻辑：**
```python
result: List[str] = []
for candidate in candidate_tags:
    existing = self.get_tag(candidate)
    if existing:
        # 精确匹配
        if existing.status == "deprecated" and existing.preferred_replacement:
            result.append(existing.preferred_replacement)
        else:
            result.append(existing.name)
        self.increment_usage(result[-1])
        continue
    
    # 查找相似标签
    similar = await self.find_similar(candidate)
    if similar:
        canonical = (
            similar.preferred_replacement
            if similar.status == "deprecated" and similar.preferred_replacement
            else similar.name
        )
        result.append(canonical)
        self.increment_usage(canonical)
    else:
        # 添加新标签
        new_tag = self.add_tag(candidate)
        result.append(new_tag.name)
        self.increment_usage(new_tag.name)

return result
```

**调用链路：**
- 被：实体识别后调用
- 调用：`get_tag()`, `find_similar()`, `add_tag()`, `increment_usage()`

**代码示例：**
```python
tag_dict = TagDict("/path/to/tags.json")
candidates = ["人", "公司", "新概念"]
standardized = await tag_dict.standardize(candidates)
print(standardized)  # 输出：["人物", "组织", "新概念"]
```

---

### 6. get_all_active() - 获取所有活跃标签

```python
def get_all_active(self) -> List[Tag]
```

**功能：**
返回所有状态为 `"active"` 的标签。

**返回值：**
- Tag 对象列表

**调用链路：**
- 被：标签列表展示时调用
- 调用：无

**代码示例：**
```python
tag_dict = TagDict("/path/to/tags.json")
active_tags = tag_dict.get_all_active()
for tag in active_tags:
    print(f"{tag.name}: {tag.usage_count} 次使用")
```

---

### 7. increment_usage() - 增加使用计数

```python
def increment_usage(self, tag_name: str) -> None
```

**功能：**
增加标签的使用计数（静默忽略不存在的标签）。

**参数：**
- `tag_name` (str): 标签名

**调用链路：**
- 被：`standardize()` 调用
- 调用：`_save()`

**代码示例：**
```python
tag_dict = TagDict("/path/to/tags.json")
tag_dict.increment_usage("人物")
```

---

## 内部辅助方法

### 8. _load() - 加载标签

```python
def _load(self) -> None
```

**功能：**
从 JSON 文件加载标签，如果文件不存在则创建空文件。

**关键逻辑：**
1. 检查文件是否存在
2. 如果不存在，创建目录和空文件
3. 如果存在，解析 JSON 并反序列化为 Tag 对象
4. 异常处理：解析失败时初始化为空字典

**调用链路：**
- 被：`__init__()` 调用
- 调用：`_save()`

---

### 9. _save() - 保存标签

```python
def _save(self) -> None
```

**功能：**
将当前标签字典持久化到 JSON 文件。

**关键逻辑：**
1. 创建目录（如果不存在）
2. 将 `_tags` 字典序列化为 JSON
3. 写入文件（`ensure_ascii=False` 支持中文，`indent=2` 格式化）

**调用链路：**
- 被：`add_tag()`, `deprecate_tag()`, `increment_usage()` 调用
- 调用：`json.dump()`

---

### 10. _ensure_core_tags() - 预置核心标签

```python
def _ensure_core_tags(self) -> None
```

**功能：**
确保 15 个核心标签存在，如果不存在则创建。

**关键逻辑：**
1. 遍历 `_CORE_TAGS` 列表
2. 检查每个标签是否存在
3. 如果不存在，创建标签（描述为 "core tag"）
4. 如果有新标签创建，保存到文件

**调用链路：**
- 被：`__init__()` 调用
- 调用：`_save()`

---

## 调用链路总览

```
服务启动
  → TagDict.__init__()
    → _load()
      → json.load()
    → _ensure_core_tags()
      → _save()
        → json.dump()

实体识别
  → standardize()
    → get_tag()
    → find_similar()
      → call_llm_json()
    → add_tag()
      → _save()
    → increment_usage()
      → _save()

标签管理
  → add_tag()
    → _save()
  → deprecate_tag()
    → _save()
  → get_all_active()
```

---

## 重要注意事项

1. **只增不删**：
   - 标签永远不会被删除或重命名
   - 弃用标签通过 `status="deprecated"` 标记
   - 保证历史数据的一致性

2. **标准化流程**：
   - 优先使用精确匹配
   - 其次使用模糊匹配（别名、子串）
   - 最后使用 LLM 语义匹配
   - 无匹配时自动创建新标签

3. **弃用机制**：
   - 弃用标签必须指定替换标签
   - 替换标签必须是活跃状态
   - 标准化时自动替换为新标签

4. **LLM 调用**：
   - 仅在前 4 种匹配策略失败时调用
   - 使用低温度（0.1）确保稳定性
   - 异常时静默失败，返回 None

5. **使用计数**：
   - 每次标准化时自动增加计数
   - 用于统计标签热度
   - 可用于标签推荐和清理

6. **核心标签**：
   - 15 个核心标签自动创建
   - 不可删除，只能弃用
   - 覆盖常见记忆分类

7. **文件格式**：
   - JSON 格式，支持中文（`ensure_ascii=False`）
   - 格式化输出（`indent=2`）
   - 便于人工查看和编辑

---

## 使用示例

### 示例 1：初始化标签字典

```python
from server.storage.tag_dict import TagDict

# 初始化（自动加载或创建文件）
tag_dict = TagDict("/path/to/tags.json")

# 查看核心标签
active_tags = tag_dict.get_all_active()
print(f"活跃标签数量：{len(active_tags)}")
```

---

### 示例 2：标准化标签

```python
from server.storage.tag_dict import TagDict

tag_dict = TagDict("/path/to/tags.json")

# 候选标签（可能不规范）
candidates = ["人", "公司", "新技术", "减肥"]

# 标准化
standardized = await tag_dict.standardize(candidates)
print(standardized)
# 可能输出：["人物", "组织", "技术", "健康"]
```

---

### 示例 3：添加和弃用标签

```python
from server.storage.tag_dict import TagDict

tag_dict = TagDict("/path/to/tags.json")

# 添加新标签
tag_dict.add_tag("旧标签", "这是一个旧标签")

# 添加替换标签
tag_dict.add_tag("新标签", "这是一个新标签")

# 弃用旧标签
tag_dict.deprecate_tag("旧标签", "新标签")

# 标准化时自动替换
result = await tag_dict.standardize(["旧标签"])
print(result)  # 输出：["新标签"]
```

---

### 示例 4：查找相似标签

```python
from server.storage.tag_dict import TagDict

tag_dict = TagDict("/path/to/tags.json")

# 查找相似标签
similar = await tag_dict.find_similar("人")
if similar:
    print(f"找到相似标签：{similar.name}")
else:
    print("没有找到相似标签")
```

---

### 示例 5：统计标签使用

```python
from server.storage.tag_dict import TagDict

tag_dict = TagDict("/path/to/tags.json")

# 获取所有活跃标签
active_tags = tag_dict.get_all_active()

# 按使用次数排序
sorted_tags = sorted(active_tags, key=lambda t: t.usage_count, reverse=True)

# 打印热门标签
print("热门标签 TOP 10：")
for tag in sorted_tags[:10]:
    print(f"{tag.name}: {tag.usage_count} 次")
```

---

## JSON 文件格式

### 示例文件

```json
{
  "人物": {
    "name": "人物",
    "aliases": ["人", "角色"],
    "description": "core tag",
    "usage_count": 42,
    "created_at": "2024-01-01T00:00:00",
    "status": "active",
    "preferred_replacement": null
  },
  "组织": {
    "name": "组织",
    "aliases": ["公司", "机构"],
    "description": "core tag",
    "usage_count": 28,
    "created_at": "2024-01-01T00:00:00",
    "status": "active",
    "preferred_replacement": null
  },
  "旧标签": {
    "name": "旧标签",
    "aliases": [],
    "description": "这是一个旧标签",
    "usage_count": 5,
    "created_at": "2024-01-15T10:30:00",
    "status": "deprecated",
    "preferred_replacement": "新标签"
  }
}
```

---

## 性能优化建议

1. **缓存活跃标签列表**：
   - `get_all_active()` 结果可缓存
   - 标签变更时清除缓存

2. **批量标准化**：
   - 一次性标准化多个标签
   - 减少 LLM 调用次数

3. **LLM 调用优化**：
   - 设置超时时间
   - 添加重试机制
   - 缓存 LLM 匹配结果

4. **文件 I/O 优化**：
   - 批量操作时延迟保存
   - 使用异步文件 I/O

5. **标签清理**：
   - 定期清理低使用率标签
   - 合并相似标签

---

## 常见问题

### Q1: 为什么不直接删除标签？

**A:** 
- 保证历史数据一致性
- 避免破坏已有节点的标签引用
- 弃用机制提供平滑过渡

### Q2: LLM 匹配失败怎么办？

**A:**
- 静默失败，返回 None
- 自动创建新标签
- 不影响系统运行

### Q3: 如何避免标签爆炸？

**A:**
1. 使用 LLM 语义匹配合并相似标签
2. 定期审查低使用率标签
3. 手动弃用冗余标签

### Q4: 标签标准化的性能如何？

**A:**
- 精确匹配：O(1)
- 模糊匹配：O(n)，n 为标签数量
- LLM 匹配：网络延迟（约 1-3 秒）
- 建议批量处理以分摊 LLM 调用成本

### Q5: 如何备份标签字典？

**A:**
- JSON 文件可直接复制备份
- 建议定期备份到版本控制系统
- 支持手动编辑（注意 JSON 格式）
