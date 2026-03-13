# Brain Memory - 开发任务拆分

## 模块划分

### M1: 基础设施层（Storage）
- Neo4j图谱操作封装（CRUD节点/关系、查询、遍历）
- Tag字典管理（只增不改不删、标准化、语义匹配）
- 编码器缓冲区（持久化读写、按session/日期查询）
- 数据模型定义（Node、Relation、Tag）

### M2: 记忆引擎层（Engine）
- 感知器（Perceiver）：消息分类 noise/command/informative
- 评估器（Evaluator）：任务相关性+情感强度+新颖度评分
- 编码器（Encoder）：实体提取、关系构建、tag标准化、Session摘要
- 检索器（Retriever）：多路检索+LLM重构
- 巩固器（Consolidator）：去重、合并、模式发现、衰减
- 工作记忆（WorkingMemory）：Session级缓存管理

### M3: API层（Hooks）
- FastAPI服务框架
- 5个Hook端点实现
- 请求/响应模型定义

### 开发顺序
M1（基础设施）→ M2（引擎）→ M3（API）→ 集成测试
