# server/engine/__init__.py 文档

## 文件整体功能说明

`server/engine/__init__.py` 是 `server.engine` 包的初始化文件，当前为空文件。

---

## 作用

作为Python包的标识文件，使 `server/engine` 目录成为一个可导入的Python包。虽然文件内容为空，但它的存在允许其他模块通过以下方式导入：

```python
from server.engine.retriever import Retriever
from server.engine.encoder import Encoder
from server.engine.consolidator import Consolidator
# 等等...
```

---

## 模块导出

当前文件为空，未显式导出任何内容。

---

## 包结构

`server/engine` 包包含以下核心引擎模块：

```
server/engine/
├── __init__.py              # 包初始化文件（本文件）
├── retriever.py             # 记忆检索器 - 从Neo4j检索相关记忆
├── encoder.py               # 记忆编码器 - 将输入编码为记忆节点
├── consolidator.py          # 记忆巩固器 - 合并和优化记忆
├── perceiver.py             # 感知器 - 处理输入感知
├── evaluator.py             # 评估器 - 评估记忆质量
├── working_memory.py        # 工作记忆 - 短期记忆缓存
├── embedding_client.py      # 向量嵌入客户端 - 生成文本向量
├── llm_client.py            # LLM客户端 - 调用大语言模型
├── log_writer.py            # 日志写入器 - 记录操作日志
└── prospective_checker.py   # 前瞻性检查器 - 检查未来事件
```

---

## 核心模块功能概览

### 1. retriever.py - 记忆检索器
**功能：** 从Neo4j知识图谱中检索相关记忆节点
- 支持语义搜索（向量相似度）
- 支持关键词搜索
- 支持图遍历（关系链路）
- 支持时间范围过滤
- 支持记忆区域过滤（semantic/episodic/procedural/emotional）

**调用链路：**
```
FastAPI路由 → Retriever.retrieve() → Neo4j查询 → Node.from_neo4j_props()
```

---

### 2. encoder.py - 记忆编码器
**功能：** 将用户输入编码为结构化的记忆节点
- 提取关键信息（名称、摘要、标签）
- 分类记忆区域（semantic/episodic/procedural/emotional）
- 生成向量嵌入
- 识别情感标签

**调用链路：**
```
用户输入 → Encoder.encode() → LLM分析 → EmbeddingClient.embed() → Node对象
```

---

### 3. consolidator.py - 记忆巩固器
**功能：** 合并重复记忆，优化知识图谱结构
- 检测相似节点
- 合并重复信息
- 更新关系链路
- 计算记忆衰减

**调用链路：**
```
定时任务 → Consolidator.consolidate() → 相似度计算 → 节点合并 → Neo4j更新
```

---

### 4. perceiver.py - 感知器
**功能：** 处理多模态输入感知
- 文本感知
- 图像感知（未来扩展）
- 音频感知（未来扩展）

**调用链路：**
```
输入数据 → Perceiver.perceive() → 模态识别 → 特征提取 → 编码器
```

---

### 5. evaluator.py - 评估器
**功能：** 评估记忆质量和重要性
- 计算记忆重要性分数
- 评估记忆置信度
- 识别需要巩固的记忆

**调用链路：**
```
记忆节点 → Evaluator.evaluate() → 多维度评分 → 更新importance字段
```

---

### 6. working_memory.py - 工作记忆
**功能：** 短期记忆缓存，提升检索性能
- 缓存最近访问的节点
- 缓存会话上下文
- 支持快速查找

**调用链路：**
```
检索请求 → WorkingMemory.get() → 缓存命中/未命中 → Retriever
```

---

### 7. embedding_client.py - 向量嵌入客户端
**功能：** 生成文本的向量表示
- 调用嵌入模型API
- 缓存向量结果
- 支持批量嵌入

**调用链路：**
```
文本输入 → EmbeddingClient.embed() → API调用 → 向量返回
```

---

### 8. llm_client.py - LLM客户端
**功能：** 调用大语言模型进行推理
- 信息提取
- 摘要生成
- 情感分析
- 关系推理

**调用链路：**
```
提示词 → LLMClient.generate() → API调用 → 结构化输出
```

---

### 9. log_writer.py - 日志写入器
**功能：** 记录系统操作日志
- 记录节点创建/更新/删除
- 记录关系创建/删除
- 记录检索请求
- 支持日志查询

**调用链路：**
```
操作事件 → LogWriter.write() → 日志存储
```

---

### 10. prospective_checker.py - 前瞻性检查器
**功能：** 检查未来事件和提醒
- 检查时间有效性（valid_until）
- 触发过期记忆清理
- 生成提醒通知

**调用链路：**
```
定时任务 → ProspectiveChecker.check() → 过期检测 → 通知/清理
```

---

## 调用关系图

```
server/engine/
│
├── FastAPI路由 (app.py)
│   ├── → Retriever.retrieve()
│   ├── → Encoder.encode()
│   └── → WorkingMemory.get()
│
├── Encoder
│   ├── → LLMClient.generate()
│   ├── → EmbeddingClient.embed()
│   └── → Evaluator.evaluate()
│
├── Retriever
│   ├── → WorkingMemory.get()
│   ├── → EmbeddingClient.embed()
│   └── → Node.from_neo4j_props()
│
├── Consolidator
│   ├── → Retriever.retrieve()
│   ├── → EmbeddingClient.embed()
│   └── → LogWriter.write()
│
└── 定时任务
    ├── → Consolidator.consolidate()
    └── → ProspectiveChecker.check()
```

---

## 潜在用途（未来扩展）

虽然当前为空，但 `__init__.py` 可以用于：

### 1. 统一导出接口
```python
"""
Brain Memory Engine Package
Core memory processing engines for the brain-memory system.
"""

from server.engine.retriever import Retriever
from server.engine.encoder import Encoder
from server.engine.consolidator import Consolidator
from server.engine.evaluator import Evaluator
from server.engine.working_memory import WorkingMemory
from server.engine.embedding_client import EmbeddingClient
from server.engine.llm_client import LLMClient

__all__ = [
    "Retriever",
    "Encoder",
    "Consolidator",
    "Evaluator",
    "WorkingMemory",
    "EmbeddingClient",
    "LLMClient",
]
```

这样外部可以直接：
```python
from server.engine import Retriever, Encoder, Consolidator
```

### 2. 引擎工厂模式
```python
class EngineFactory:
    """引擎工厂，统一管理引擎实例"""
    
    _retriever = None
    _encoder = None
    _consolidator = None
    
    @classmethod
    def get_retriever(cls):
        if cls._retriever is None:
            cls._retriever = Retriever()
        return cls._retriever
    
    @classmethod
    def get_encoder(cls):
        if cls._encoder is None:
            cls._encoder = Encoder()
        return cls._encoder
```

### 3. 引擎配置
```python
# 引擎级别的配置
ENGINE_CONFIG = {
    "retriever": {
        "max_results": 10,
        "similarity_threshold": 0.7,
    },
    "encoder": {
        "model": "text-embedding-ada-002",
        "max_tokens": 8192,
    },
    "consolidator": {
        "merge_threshold": 0.9,
        "run_interval": 3600,  # 1小时
    },
}
```

---

## 注意事项

1. **模块依赖**: engine包中的模块相互依赖，需注意避免循环导入
2. **单例模式**: 某些引擎（如Retriever, EmbeddingClient）适合使用单例模式
3. **异步支持**: 考虑使用异步版本的引擎方法以提升性能
4. **错误处理**: 引擎方法应统一错误处理机制

---

## 建议

考虑在此文件中添加统一导出和工厂模式：

```python
"""
Brain Memory Engine Package
Core memory processing engines.
"""

from server.engine.retriever import Retriever
from server.engine.encoder import Encoder
from server.engine.consolidator import Consolidator
from server.engine.evaluator import Evaluator
from server.engine.working_memory import WorkingMemory
from server.engine.embedding_client import EmbeddingClient
from server.engine.llm_client import LLMClient
from server.engine.log_writer import LogWriter
from server.engine.perceiver import Perceiver
from server.engine.prospective_checker import ProspectiveChecker

__version__ = "1.0.0"
__all__ = [
    "Retriever",
    "Encoder",
    "Consolidator",
    "Evaluator",
    "WorkingMemory",
    "EmbeddingClient",
    "LLMClient",
    "LogWriter",
    "Perceiver",
    "ProspectiveChecker",
]

# 单例实例（可选）
_retriever_instance = None
_encoder_instance = None

def get_retriever():
    """获取Retriever单例"""
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = Retriever()
    return _retriever_instance

def get_encoder():
    """获取Encoder单例"""
    global _encoder_instance
    if _encoder_instance is None:
        _encoder_instance = Encoder()
    return _encoder_instance
```

这样可以简化导入和实例管理：
```python
# 简化前
from server.engine.retriever import Retriever
from server.engine.encoder import Encoder
retriever = Retriever()
encoder = Encoder()

# 简化后
from server.engine import get_retriever, get_encoder
retriever = get_retriever()
encoder = get_encoder()
```

---

## 相关文件

- `server/__init__.py` - server包初始化文件
- `server/models/__init__.py` - models子包初始化文件
- `server/app.py` - FastAPI应用主入口，调用engine模块
