# Brain Memory v3: 认知图谱 + 文件日志分层存储

## 设计理念

**核心原则：知识图谱存认知，文件系统存细节。**

当前问题：encoder把所有信息都往图谱里塞（"苹果"、"牛肉面"都成了实体），导致图谱被流水账污染。

正确做法：
- **图谱（Neo4j）**：存高层认知 — 目标、决策、状态变更、人际关系、里程碑
- **文件日志**：存细节流水 — 饮食记录、运动记录、面试反馈、交易记录
- **图谱节点指向文件**：通过 `log_path` 属性关联，需要细节时去文件里查

## 示例

用户说："早上我吃了一个苹果"

### ❌ 当前行为（v2）
```
创建实体: 苹果(create), 用户(create), 早餐水果习惯(create)
关系: 用户→苹果, 用户→早餐水果习惯
```

### ✅ 期望行为（v3）
```
1. 识别为"饮食记录"类信息
2. 更新图谱: 减肥计划.last_diet_log = "2026-03-14"
3. 写入文件: memory/logs/diet/2026-03-14.md 追加 "- 早餐: 苹果"
4. 图谱记录: 减肥计划.diet_log_path = "memory/logs/diet/"
```

## 信息分类体系

### Category 1: 认知型（写入图谱）
直接影响用户画像、目标、决策的信息。
- 决策："我决定下周开始学Rust" → 创建/更新学习计划实体
- 状态变更："我从美团离职了" → 更新职业状态
- 关系："刘凡是我同事" → 创建人际关系
- 里程碑："面试通过了" → 更新跳槽计划
- 偏好："我不喜欢吃辣" → 更新用户偏好（需多次确认）

### Category 2: 日志型（写入文件 + 更新图谱索引）
细节流水，有对应的跟踪目标。
- 饮食记录 → `memory/logs/diet/YYYY-MM-DD.md` + 更新"减肥计划"实体
- 运动记录 → `memory/logs/exercise/YYYY-MM-DD.md` + 更新"减肥计划"实体
- 面试反馈 → `memory/logs/interview/YYYY-MM-DD.md` + 更新"跳槽计划"实体
- 交易记录 → `memory/logs/trading/YYYY-MM-DD.md` + 更新"量化交易"实体
- 学习笔记 → `memory/logs/learning/YYYY-MM-DD.md` + 更新对应学习计划

### Category 3: 噪音型（丢弃）
- 社交填充："嗯嗯"、"好的"
- 纯指令："帮我查天气"
- 调试对话："检查一下日志"

## 架构改动

### 改动1: Perceiver 增加 category 字段

输出从：
```json
{"type": "informative", "rewrite": "..."}
```
变为：
```json
{
  "type": "informative",
  "category": "log_diet",  // 新增
  "rewrite": "赵禹早上吃了一个苹果",
  "target_entity": "减肥计划"  // 新增：应该更新哪个图谱实体
}
```

category 枚举值：
- `cognition` — 认知型，走原有encoder流程写入图谱
- `log_diet` — 饮食日志
- `log_exercise` — 运动日志
- `log_interview` — 面试日志
- `log_trading` — 交易日志
- `log_learning` — 学习日志
- `log_general` — 通用日志（无明确分类的日志型信息）

### 改动2: Encoder 增加日志写入分支

```python
async def encode_message(self, message, evaluation, ...):
    category = evaluation.get("category", "cognition")
    
    if category == "cognition":
        # 原有流程：实体提取 → resolve → 写入buffer
        return await self._encode_cognition(message, evaluation, ...)
    elif category.startswith("log_"):
        # 新流程：写入文件 + 更新图谱索引
        return await self._encode_log(message, evaluation, category, ...)
```

### 改动3: 新增 LogWriter 组件

```python
class LogWriter:
    """将日志型信息写入文件系统，并更新图谱索引。"""
    
    BASE_DIR = "/root/.openclaw/workspace/memory/logs"
    
    # category → 子目录映射
    CATEGORY_DIRS = {
        "log_diet": "diet",
        "log_exercise": "exercise",
        "log_interview": "interview",
        "log_trading": "trading",
        "log_learning": "learning",
        "log_general": "general",
    }
    
    async def write_log(self, category, message, target_entity, tenant_id, user_id):
        """
        1. 确定文件路径: BASE_DIR/{subdir}/{YYYY-MM-DD}.md
        2. Append一行到文件
        3. 更新图谱中target_entity的索引属性
        """
        
    async def _update_graph_index(self, entity_name, log_path, date):
        """更新图谱实体的 last_log_date 和 log_path 属性"""
```

### 改动4: Evaluator 传递 category

Evaluator需要把Perceiver的category透传给Encoder，不做修改。

## 文件格式

`memory/logs/diet/2026-03-14.md`:
```markdown
# 饮食记录 2026-03-14

- 08:30 早餐: 苹果
- 12:00 午餐: 牛肉面，约600大卡
- 19:00 晚餐: 沙拉+鸡胸肉，约400大卡

**当日合计**: ~1100大卡
```

每条记录格式: `- {时间} {餐次}: {内容}`
时间从消息的timestamp提取，如果没有就用当前时间。

## 修改文件清单

| 文件 | 改动 |
|------|------|
| `server/engine/perceiver.py` | 输出增加 category + target_entity 字段 |
| `server/engine/evaluator.py` | 透传 category + target_entity |
| `server/engine/encoder.py` | 增加 `_encode_log` 分支，调用 LogWriter |
| `server/engine/log_writer.py` | **新建** — 文件写入 + 图谱索引更新 |
| `server/app.py` | 无改动（接口不变） |
| `server/storage/graph.py` | 可能需要增加 update_node_properties 便捷方法 |

## 约束

- 不改变现有API接口（after-response的输入输出不变）
- cognition类信息走原有流程，不受影响
- 文件写入用append模式，不覆盖已有内容
- 图谱索引属性用 `properties` JSON字段存储（已有机制）
- 日志目录不存在时自动创建
- 时区统一用北京时间（UTC+8）

## 测试用例

| 输入 | 期望category | 期望行为 |
|------|-------------|---------|
| "早上我吃了一个苹果" | log_diet | 写入diet日志 + 更新减肥计划实体 |
| "我今天跑了5公里" | log_exercise | 写入exercise日志 + 更新减肥计划实体 |
| "腾讯二面过了" | log_interview | 写入interview日志 + 更新跳槽计划实体 |
| "我决定下周开始学Rust" | cognition | 原有流程，创建/更新学习计划实体 |
| "刘凡是我新同事" | cognition | 原有流程，创建人际关系 |
| "嗯嗯" | noise | 丢弃 |
| "帮我查天气" | command | 丢弃 |
| "今天比特币涨了5%" | log_trading | 写入trading日志 + 更新量化交易实体 |
