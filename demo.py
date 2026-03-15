#!/usr/bin/env python3
"""
Brain Memory Service Demo

Demonstrates the core workflow:
1. Health check
2. Session start
3. Encode different types of messages
4. Retrieve memories
5. Display results
"""

import argparse
import asyncio
import time
import uuid
import httpx


async def main():
    parser = argparse.ArgumentParser(description="Brain Memory Service Demo")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8100",
        help="Base URL of the brain-mem service (default: http://localhost:8100)"
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    tenant_id = "demo-tenant"
    user_id = "demo-user"
    session_id = str(uuid.uuid4())

    print(f"🧠 Brain Memory Service Demo")
    print(f"📍 Service URL: {base_url}")
    print(f"👤 User: {tenant_id}/{user_id}")
    print(f"🔑 Session: {session_id}\n")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Health check
        print("1️⃣  Health Check...")
        try:
            resp = await client.get(f"{base_url}/health")
            resp.raise_for_status()
            health = resp.json()
            print(f"   ✅ Service is healthy: {health}\n")
        except Exception as e:
            print(f"   ❌ Health check failed: {e}")
            print("   Make sure the service is running at", base_url)
            return

        # 2. Session start
        print("2️⃣  Starting Session...")
        try:
            resp = await client.post(
                f"{base_url}/hooks/session-start",
                json={
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "user_profile": {"name": "Demo User", "role": "developer"},
                    "agent_context": {"task": "demo workflow"}
                }
            )
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 0:
                data = result.get("data", {})
                context = data.get("context", "")
                reminders = data.get("pending_reminders", [])
                print(f"   ✅ Session started")
                if context:
                    print(f"   📝 Context: {context[:200]}...")
                if reminders:
                    print(f"   ⏰ Reminders: {reminders}")
                print()
            else:
                print(f"   ⚠️  Session start returned: {result}\n")
        except Exception as e:
            print(f"   ❌ Session start failed: {e}\n")

        # 3. Encode different types of messages
        messages = [
            "I'm working on a Python project called brain-memory that implements a memory system for AI agents.",
            "The project uses Neo4j for graph storage and FastAPI for the REST API.",
            "I learned that vector embeddings are crucial for semantic search in memory retrieval.",
            "Remind me to review the consolidation logic next week.",
        ]

        print("3️⃣  Encoding Messages...")
        for i, msg in enumerate(messages, 1):
            print(f"   [{i}/{len(messages)}] {msg[:60]}...")
            try:
                resp = await client.post(
                    f"{base_url}/hooks/after-response",
                    json={
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "session_id": session_id,
                        "user_message": msg,
                        "assistant_response": "Understood."
                    }
                )
                resp.raise_for_status()
                result = resp.json()
                if result.get("code") == 0:
                    print(f"       ✅ Accepted for encoding")
                else:
                    print(f"       ⚠️  Response: {result}")
            except Exception as e:
                print(f"       ❌ Failed: {e}")

            # Wait between messages to allow processing
            if i < len(messages):
                await asyncio.sleep(5)
        print()

        # 4. Retrieve memories
        print("4️⃣  Retrieving Memories...")
        queries = [
            "What am I working on?",
            "Tell me about the technology stack",
        ]

        for query in queries:
            print(f"   🔍 Query: {query}")
            try:
                resp = await client.post(
                    f"{base_url}/hooks/before-query",
                    json={
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "session_id": session_id,
                        "query": query,
                        "recent_messages": []
                    }
                )
                resp.raise_for_status()
                result = resp.json()
                if result.get("code") == 0:
                    data = result.get("data", {})
                    context = data.get("context", "")
                    if context:
                        print(f"   📚 Retrieved context:")
                        print(f"      {context[:300]}...")
                    else:
                        print(f"   📭 No relevant memories found yet")
                else:
                    print(f"   ⚠️  Response: {result}")
            except Exception as e:
                print(f"   ❌ Failed: {e}")
            print()

        # 5. Session end
        print("5️⃣  Ending Session...")
        try:
            resp = await client.post(
                f"{base_url}/hooks/session-end",
                json={
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "conversation_history": [
                        {"role": "user", "content": msg}
                        for msg in messages
                    ]
                }
            )
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 0:
                print(f"   ✅ Session ended successfully\n")
            else:
                print(f"   ⚠️  Response: {result}\n")
        except Exception as e:
            print(f"   ❌ Failed: {e}\n")

        print("✨ Demo completed!")
        print("\n💡 Next steps:")
        print(f"   - View activity logs: curl {base_url}/logs")
        print(f"   - Trigger consolidation: curl -X POST {base_url}/hooks/consolidate -H 'Content-Type: application/json' -d '{{\"tenant_id\":\"{tenant_id}\",\"user_id\":\"{user_id}\"}}'")


if __name__ == "__main__":
    asyncio.run(main())
