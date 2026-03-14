#!/usr/bin/env python3
"""
Simple test script for prospective memory feature.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.engine.perceiver import Perceiver
from server.engine.encoder import Encoder
from server.storage.graph import GraphStore
from server.storage.tag_dict import TagDict
from server.storage.buffer import EncoderBuffer


async def test_perceiver():
    """Test perceiver classification of prospective messages."""
    print("=" * 60)
    print("Testing Perceiver - Prospective Memory Classification")
    print("=" * 60)

    perceiver = Perceiver()

    test_cases = [
        "明天早上9点提醒我交报告",
        "下次聊到减肥时提醒我记录饮食",
        "如果BTC跌破6万提醒我",
    ]

    for msg in test_cases:
        print(f"\nMessage: {msg}")
        result = await perceiver.classify(msg, working_memory={
            "raw": {"user_profile": {"name": "赵禹"}},
            "context": "用户正在规划日程",
        })
        print(f"Type: {result.get('type')}")
        print(f"Category: {result.get('category')}")
        print(f"Trigger Type: {result.get('trigger_type')}")
        print(f"Trigger Value: {result.get('trigger_value')}")
        print(f"Action: {result.get('action')}")
        print(f"Reason: {result.get('reason')}")


async def test_encoder():
    """Test encoder creation of prospective memory nodes."""
    print("\n" + "=" * 60)
    print("Testing Encoder - Prospective Memory Creation")
    print("=" * 60)

    # Initialize components (using test config)
    graph = GraphStore(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="laolao2026"
    )
    await graph.connect()

    tag_dict = TagDict(path="./data/tag_dict.json")
    buffer = EncoderBuffer(db_path="./data/buffer.db")
    encoder = Encoder(graph, tag_dict, buffer)

    # Test prospective encoding
    evaluation = {
        "category": "prospective",
        "trigger_type": "time",
        "trigger_value": "2026-03-15T09:00:00+08:00",
        "action": "提醒交报告",
        "encode_decision": True,
        "encode_priority": "high",
    }

    result = await encoder.encode_message(
        message="明天早上9点提醒我交报告",
        evaluation=evaluation,
        tenant_id="test_tenant",
        user_id="test_user",
        session_id="test_session",
        working_memory=None,
    )

    print(f"\nResult: {result}")
    print(f"Node ID: {result.get('node_id')}")
    print(f"Status: {result.get('status')}")

    await graph.close()


async def main():
    """Run all tests."""
    try:
        await test_perceiver()
        # Uncomment to test encoder (requires Neo4j connection)
        # await test_encoder()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
