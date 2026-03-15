# Brain-Mem Benchmark Results
Run: 2026-03-15 12:19:37
Server: http://localhost:8100

| Dimension | Tests | Passed | Rate |
|:----------|------:|-------:|-----:|
| Selective Encoding | 4 | 3 | 75.0% |
| Vector Semantic Recall | 4 | 1 | 25.0% |
| Noise Filtering | 5 | 5 | 100.0% |
| Classification Routing | 6 | 2 | 33.3% |
| Reconsolidation | 1 | 1 | 100.0% |
| Prospective Memory | 2 | 2 | 100.0% |

**Overall: 14/22 (63.6%)**

## Detailed Results
### Selective Encoding
- ✅ "嗯嗯" → noise (correct)
- ❌ "我决定下周去上海面试" → no perceiver log found
- ✅ "帮我查天气" → command (correct)
- ✅ "中午吃了牛肉面600大卡" → log_diet (correct)

### Vector Semantic Recall
- ❌ "那个做AI的朋友" → no relevant recall (expected: 张三, 字节, 大模型)
- ❌ "ByteDance的人" → no relevant recall (expected: 张三, 字节)
- ❌ "体重管理的事" → no relevant recall (expected: 减肥, 90kg, 85kg, 体重)
- ✅ "节食计划" → recalled (matched: 减肥, kg)

### Noise Filtering
- ✅ All 5 noise messages filtered correctly

### Classification Routing
- ❌ "我决定跳槽" → no classification log found
- ❌ "午餐吃了沙拉300大卡" → no classification log found
- ❌ "今天跑了5公里" → no classification log found
- ❌ "面试聊了系统设计" → no classification log found
- ✅ "嗯嗯" → noise (correct)
- ✅ "帮我搜一下" → command (correct)

### Reconsolidation
- ✅ Reconsolidation successful - correction reflected

### Prospective Memory
- ✅ Positive trigger activated (context contains reminder)
- ✅ Negative trigger correct (no false activation)
