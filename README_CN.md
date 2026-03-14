<div align="center">

# 🧠 Brain-Mem

### 面向 AI Agent 的类脑记忆系统

*让你的 AI 拥有一颗会记忆、会遗忘、会做梦、会成长的大脑。*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)
[![Neo4j](https://img.shields.io/badge/Neo4j-4.x-008CC1.svg)](https://neo4j.com)
[![OpenClaw Plugin](https://img.shields.io/badge/OpenClaw-Plugin-orange.svg)](https://github.com/openclaw/openclaw)

[English](README.md) | **中文**

---

<img src="https://img.shields.io/badge/感知器-丘脑-ff6b6b?style=for-the-badge" />
<img src="https://img.shields.io/badge/评估器-前额叶-ffa502?style=for-the-badge" />
<img src="https://img.shields.io/badge/编码器-海马体-7bed9f?style=for-the-badge" />
<img src="https://img.shields.io/badge/检索器-多路召回-70a1ff?style=for-the-badge" />
<img src="https://img.shields.io/badge/巩固器-睡眠巩固-a29bfe?style=for-the-badge" />

</div>

---

## 💡 为什么需要 Brain-Mem？

大多数 AI Agent 都有"失忆症"——它们忘记你昨天说的话，无法跨对话关联信息，每次会话都像一张白纸。

Brain-Mem 通过赋予 Agent 一套**仿人脑记忆系统**来解决这个问题：

- 🎯 **选择性编码** — 只记住重要的，不是什么都记
- 😢 **情感驱动** — 情感强度影响记忆的编码优先级和召回排序
- 🌙 **睡眠巩固** — 每晚定时去重、发现模式、甚至"做梦"产生创造性洞察
- 📉 **自然遗忘** — 不重要的记忆随时间衰减，重要的持久保留
- 🔄 **记忆修正** — 用户纠正时自动更新（"其实那次面试挺好的"）
- ⏰ **前瞻性记忆** — "下次聊到X时提醒我Y"

## 🏗️ 系统架构

### 核心管线

```
                    ┌─────────────────────────────────────┐
                    │           工作记忆                    │
                    │   (用户画像、目标、情绪基线)           │
                    └──────────┬──────────────────────────┘
                               │ 为所有组件提供上下文
            ┌──────────────────┼──────────────────────┐
            ▼                  ▼                      ▼
     ┌────────────┐    ┌────────────┐         ┌────────────┐
     │  感知器     │───▶│  评估器     │         │  检索器     │
     │  (丘脑)    │    │ (前额叶)   │         │ (多路召回)  │
     └────────────┘    └─────┬──────┘         └─────┬──────┘
                             │                      │
                             ▼                      │
                       ┌────────────┐               │
                       │  编码器     │               │
                       │ (海马体)   │               │
                       └─────┬──────┘               │
                             │                      │
                             ▼                      │
                    ┌─────────────────┐             │
                    │   编码缓冲区    │◀────────────┘
                    │   (SQLite)     │  检索器也搜缓冲区
                    └────────┬────────┘
                             │ 每晚巩固
                             ▼
                    ┌─────────────────┐
                    │    巩固器       │
                    │  (睡眠巩固)     │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Neo4j 知识图谱  │◀──── 检索器查询
                    │  (长期记忆)      │
                    └─────────────────┘
```

### 设计哲学

| 原则 | 说明 |
|:-----|:-----|
| **增强，不替代** | 宿主 Agent 已有对话历史，我们只注入它没有的：跨会话记忆、长期模式、遗忘的上下文 |
| **图谱存认知，文件存细节** | 知识图谱存高层理解（决策、关系、里程碑），文件存流水账（饮食、运动、面试记录） |
| **单消息聚焦** | 只编码当前用户消息，不重复编码历史 |
| **情感驱动** | 情感强度影响编码优先级和召回排序，和人脑一样 |

### v3 分层存储

不是所有信息都该进知识图谱。Brain-Mem 把信息路由到正确的位置：

| 用户说的话 | 分类 | 存储位置 |
|:---|:---|:---|
| "我决定跳槽" | `cognition` | 📊 **图谱** — 实体 + 关系 |
| "中午吃了沙拉300大卡" | `log_diet` | 📄 **文件** + 图谱索引 |
| "跑了5公里" | `log_exercise` | 📄 **文件** + 图谱索引 |
| "腾讯二面聊了分布式" | `log_interview` | 📄 **文件** + 图谱索引 |
| "不对，面试其实很好" | `reconsolidation` | 🔄 **图谱更新**（修正已有节点） |
| "明天提醒我开会" | `prospective` | ⏰ **图谱**（触发器节点） |
| "忘掉这个人" | `forget` | 🚫 **图谱**（抑制节点） |
| "嗯嗯" | `noise` | 🗑️ 丢弃 |

## 🧬 8 大辅助机制

核心管线之外，Brain-Mem 实现了 8 种认知科学机制，让记忆"活"起来：

| # | 机制 | 灵感来源 | 作用 |
|:--|:-----|:---------|:-----|
| 1 | 🎭 **情感共鸣** | 情绪一致性记忆 | 难过时召回消极记忆共情 + 积极记忆鼓励 |
| 2 | 🔄 **记忆重构** | 提取时记忆可修改 | "其实面试挺好的" → 更新已存储的记忆 |
| 3 | ⏰ **前瞻性记忆** | 未来意图 | 时间触发（"明天提醒我"）+ 事件触发（"下次聊到X时"） |
| 4 | 🧹 **主动遗忘** | 记忆抑制 | "忘掉这个人" → 节点隐藏，永不召回 |
| 5 | 📅 **间隔重复** | Anki式复习 | 重要记忆快衰减时标记复习（1→3→7→21天→翻倍） |
| 6 | ⚔️ **干扰性遗忘** | 前摄/后摄干扰 | 新旧信息矛盾？旧关系标记结束，新关系创建 |
| 7 | 💡 **创造性重组** | REM睡眠做梦 | 随机组合记忆片段 → 偶尔产生有价值的洞察 |
| 8 | 🔍 **提取补偿** | 话到嘴边现象 | 搜不到？降低阈值、扩大遍历深度重试 |

## 📖 完整工作流示例：禹哥的一天

### 🌅 早上 9:00 — 新会话启动
```
工作记忆冷启动：
├── 目标：[减肥计划, 跳槽计划]
├── 间隔重复："不喜欢吃香菜" 需要复习
└── 前瞻性记忆："9:00 提醒交报告" → 触发！
```
> 🤖 "早上好！别忘了今天要交报告"

### 🥪 9:15 — 饮食记录
```
"早上吃了三明治，400大卡"
  → log_diet → 写入 diet/2026-03-14.md
  → 检索器召回："目标1600大卡/天"
```
> 🤖 "记上了！还剩1200大卡"

### 😢 10:30 — 情感事件
```
"腾讯二面挂了，好沮丧"
  → cognition, 情感=sadness(7/10), 高优先级编码
  → 情感共鸣激活：
     ├── 共情：召回过去的失败经历
     └── 鼓励：召回过去的成功经历
```
> 🤖 "上次XX也没过，但后来拿到了更好的offer"

### 🔄 11:00 — 记忆修正
```
"不对，其实面试感觉还行"
  → reconsolidation → 更新情感标签：sadness → neutral
  → 旧值保存在修正历史中
```

### 🥗 12:00 — 间隔重复成功
```
"推荐个晚餐"
  → 检索器找到："不喜欢吃香菜"（标记复习的记忆）
  → 成功召回！复习间隔延长到3天
```
> 🤖 "推荐几个清淡的，都没有香菜"

### ⏰ 14:00 — 设置未来提醒
```
"下次聊到字节时提醒我问进度"
  → prospective, 事件触发, trigger="字节", status=pending
```

### 🔔 15:00 — 事件触发
```
"字节那边有消息吗"
  → 前瞻性检查器：匹配到"字节"触发器！
```
> 🤖 "对了，你之前让我提醒你问字节面试进度"

### 🚫 16:00 — 主动遗忘
```
"忘掉魏小康"
  → forget → 节点标记 suppressed，检索时永不出现
```

### 🌙 凌晨 1:00 — 睡眠巩固
```
巩固器启动：
├── 去重：合并当天重复实体
├── 冲突解决：处理矛盾信息
├── 模式发现："面试频率在加速"
├── 创造性重组：随机组合 → "brain-memory可以做成开源产品" ✨
├── 间隔重复：标记快衰减的重要记忆
├── 全局衰减：所有节点自然老化
└── 归档缓冲区
```

## 📉 记忆衰减模型

基于艾宾浩斯遗忘曲线，增加生物学增强：

```
有效半衰期 = 基础半衰期 × (1 + 重要性/10) × 区域系数

区域系数：
  🎬 情景记忆 = 0.5   (事件容易忘)
  📚 语义记忆 = 2.0   (知识持久)
  🔧 程序记忆 = 3.0   (技能最持久)
  💛 情感记忆 = 1.0   (基线)

示例（基础半衰期 = 30天）：
  事件, 重要性=5:  30 × 1.5 × 0.5 =  22天
  知识, 重要性=5:  30 × 1.5 × 2.0 =  90天
  技能, 重要性=8:  30 × 1.8 × 3.0 = 162天
```

## 🛠️ 技术栈

| 组件 | 技术 |
|:-----|:-----|
| API 服务 | Python 3.11 · FastAPI · Uvicorn |
| 长期记忆 | Neo4j 4.x |
| 短期缓冲 | SQLite |
| 文件日志 | Markdown |
| LLM 后端 | 任何 OpenAI 兼容 API |
| 插件宿主 | OpenClaw Gateway (TypeScript) |
| 进程管理 | systemd |

## 📁 项目结构

```
brain-mem/
├── server/
│   ├── app.py                        # FastAPI + 路由
│   ├── engine/
│   │   ├── perceiver.py              # 🔴 丘脑 — 分类 & 改写
│   │   ├── evaluator.py              # 🟠 前额叶 — 评分 & 决策
│   │   ├── encoder.py                # 🟢 海马体 — 提取 & 编码
│   │   ├── retriever.py              # 🔵 多路召回 + 情感共鸣
│   │   ├── consolidator.py           # 🟣 睡眠巩固 + 创造性重组
│   │   ├── working_memory.py         # 会话上下文缓存
│   │   ├── log_writer.py             # v3 文件日志 + 图谱索引
│   │   ├── prospective_checker.py    # ⏰ 时间/事件触发检查
│   │   └── llm_client.py             # LLM API 客户端
│   ├── storage/
│   │   ├── graph.py                  # Neo4j 操作
│   │   ├── buffer.py                 # SQLite 缓冲区
│   │   └── tag_dict.py              # 标签体系
│   └── models/
│       ├── node.py                   # 记忆节点模型
│       └── relation.py               # 关系模型
├── docs/
│   └── V3-DESIGN.md                  # 架构设计文档
├── data/                             # 运行时数据（自动创建）
└── config.yaml
```

## 🚀 快速开始

```bash
# 1. 克隆 & 安装
git clone https://github.com/iCanDoAllThingszz/brain-mem.git
cd brain-mem
pip install -r requirements.txt

# 2. 启动 Neo4j
docker run -d --name neo4j-memory \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  neo4j:4.4

# 3. 配置
cp config.yaml.example config.yaml
# 编辑 config.yaml，填入 Neo4j 密码和 LLM API Key

# 4. 运行
python -m uvicorn server.app:app --host 0.0.0.0 --port 8100

# 5. 设置每晚巩固定时任务
echo "30 17 * * * curl -s -X POST http://localhost:8100/hooks/consolidate \
  -H 'Content-Type: application/json' \
  -d '{\"tenant_id\":\"default\",\"user_id\":\"your-user\"}'" | crontab -
```

## 📡 API 接口

| 方法 | 端点 | 说明 |
|:-----|:-----|:-----|
| `GET` | `/health` | 健康检查 |
| `GET` | `/logs?n=30` | 活动日志 |
| `POST` | `/hooks/session-start` | 加载工作记忆 |
| `POST` | `/hooks/before-query` | 检索记忆 |
| `POST` | `/hooks/after-response` | 编码用户消息 |
| `POST` | `/hooks/session-end` | 会话清理 |
| `POST` | `/hooks/consolidate` | 触发巩固 |
| `POST` | `/hooks/check-prospective` | 检查前瞻性触发器 |

## 📄 许可证

MIT

---

<div align="center">

由 **酪酪 & 禹哥** 用 🧠 构建

*"记忆不是过去的录像，而是现在的重构。" — Daniel Schacter*

</div>
