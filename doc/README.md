# Brain Memory 项目文档

本目录包含 Brain Memory 项目所有 Python 文件的详细中文文档。

## 📚 文档索引

### 核心应用层
- [app.md](app.md) - Brain Memory Service 主应用（HTTP API、后台任务、生命周期管理）
- [activity_log.md](activity_log.md) - 活动日志记录器（结构化日志、自动轮转）

### 引擎层（Engine）
记忆处理的核心引擎，按照记忆流水线顺序：

1. [perceiver.md](perceiver.md) - 感知器（消息分类、重写、类别识别）
2. [evaluator.md](evaluator.md) - 评估器（三维度评分、编码决策）
3. [encoder.md](encoder.md) - 编码器（记忆编码、实体生命周期管理）
4. [consolidator.md](consolidator.md) - 巩固器（短期→长期记忆转移、10阶段巩固）
5. [retriever.md](retriever.md) - 检索器（5路径检索、综合评分）
6. [working_memory.md](working_memory.md) - 工作记忆（会话级上下文缓存）
7. [prospective_checker.md](prospective_checker.md) - 前瞻性记忆检查器（提醒触发）
8. [log_writer.md](log_writer.md) - 日志写入器（文件系统日志、图谱索引）

### 客户端层
- [llm_client.md](llm_client.md) - LLM 客户端（统一调用接口、响应解析）
- [embedding_client.md](embedding_client.md) - 嵌入向量客户端（MiniMax API、LRU缓存）

### 存储层（Storage）
- [buffer.md](buffer.md) - 短期记忆缓冲区（SQLite、CRUD操作）
- [graph.md](graph.md) - Neo4j 图存储层（节点/关系操作、记忆衰减、向量检索）
- [tag_dict.md](tag_dict.md) - 标签字典管理（标签标准化、语义匹配）

### 数据模型层（Models）
- [node.md](node.md) - Node 类（记忆节点模型、记忆区域、衰减机制）
- [relation.md](relation.md) - Relation 类（关系模型、时间有效性、置信度）

### 模块初始化
- [server__init__.md](server__init__.md) - server 包初始化
- [engine__init__.md](engine__init__.md) - engine 包初始化（引擎模块概览）
- [models__init__.md](models__init__.md) - models 包初始化（数据模型概览）

## 🔄 记忆处理流程

```
用户消息
    ↓
Perceiver（感知）→ 分类、重写
    ↓
Evaluator（评估）→ 评分、决策
    ↓
Encoder（编码）→ 结构化、实体提取
    ↓
Buffer（缓冲）→ 短期存储
    ↓
Consolidator（巩固）→ 转移到图谱
    ↓
Graph（图谱）→ 长期存储
    ↓
Retriever（检索）→ 召回记忆
```

## 📖 阅读建议

### 新手入门
1. 先读 [app.md](app.md) 了解整体架构
2. 按流程顺序读引擎层文档（perceiver → evaluator → encoder → consolidator → retriever）
3. 再读存储层（buffer.md、graph.md）
4. 最后读数据模型（node.md、relation.md）

### 深入理解
- **记忆编码机制**：encoder.md + consolidator.md
- **记忆检索机制**：retriever.md + graph.md
- **记忆衰减机制**：node.md + graph.md
- **实体生命周期**：encoder.md + consolidator.md

### 问题排查
- **API 问题**：app.md
- **记忆丢失**：buffer.md + consolidator.md
- **检索不准**：retriever.md + embedding_client.md
- **性能问题**：graph.md + buffer.md

## 📝 文档特点

✅ **中文撰写** - 所有内容使用中文，清晰易懂  
✅ **详细完整** - 包含类、方法、参数、返回值、逻辑说明  
✅ **代码示例** - 关键部分提供实际代码示例  
✅ **调用关系** - 使用 `→` 标注调用链路  
✅ **重要逻辑** - 突出核心设计和注意事项  

## 🔧 维护说明

- 代码更新后，请同步更新对应的文档
- 新增文件时，请按照现有格式创建文档
- 文档格式：文件名.md（例如：app.md）

---

**生成时间：** 2026-03-18  
**文档数量：** 20个文件  
**总字数：** ~15万字
