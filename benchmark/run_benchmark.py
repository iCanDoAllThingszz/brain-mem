#!/usr/bin/env python3
"""
Brain-Mem Benchmark Framework
Validates memory features using mock test data.
"""

import argparse
import time
import httpx
from datetime import datetime
from typing import List, Dict, Any, Tuple


class BenchmarkRunner:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=60.0)  # Increased timeout
        self.results: List[Dict[str, Any]] = []

    def _generate_tenant_id(self, prefix: str) -> str:
        """Generate unique tenant ID for test isolation."""
        timestamp = int(time.time() * 1000)
        return f"bench-{prefix}-{timestamp}"

    def _encode_message(self, tenant_id: str, message: str, sleep_after: float = 6.0) -> Dict[str, Any]:
        """Encode a message via /hooks/after-response."""
        payload = {
            "tenant_id": tenant_id,
            "user_id": "bench_user",
            "session_id": f"session-{tenant_id}",
            "user_message": message,
            "assistant_response": "收到"
        }
        resp = self.client.post(f"{self.base_url}/hooks/after-response", json=payload)
        resp.raise_for_status()

        # Wait for background processing to complete
        if sleep_after > 0:
            time.sleep(sleep_after)

        return resp.json()

    def _wait_for_perceiver_log(self, message: str, max_wait: float = 10.0) -> Dict[str, Any]:
        """Wait for perceiver log to appear for a specific message."""
        start_time = time.time()
        while time.time() - start_time < max_wait:
            logs = self._get_logs(n=30)  # Increased from 10
            for log in reversed(logs):  # Check most recent first
                if log.get("type") == "perceiver" and message[:20] in log.get("summary", ""):
                    return log
            time.sleep(0.5)
        return None

    def _retrieve_memories(self, tenant_id: str, query: str) -> Dict[str, Any]:
        """Retrieve memories via /hooks/before-query."""
        payload = {
            "tenant_id": tenant_id,
            "user_id": "bench_user",
            "session_id": f"session-{tenant_id}",
            "query": query
        }
        try:
            resp = self.client.post(f"{self.base_url}/hooks/before-query", json=payload)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Warning: Retrieval failed for query '{query[:30]}...': {e}")
            return {"data": {"context": ""}}

    def _get_logs(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get recent activity logs via API and parse them."""
        import re

        try:
            resp = self.client.get(f"{self.base_url}/logs", params={"n": n})
            resp.raise_for_status()
            logs_text = resp.json().get("logs", "")

            # Parse the formatted log lines
            entries = []
            for line in logs_text.split("\n"):
                if not line.strip():
                    continue

                # Parse format: [timestamp] type: summary | key=value, ...
                match = re.match(r'\[([^\]]+)\] (\w+): ([^|]+)(?:\| (.+))?', line)
                if match:
                    timestamp, log_type, summary, details_str = match.groups()

                    entry = {
                        "time": timestamp,
                        "type": log_type,
                        "summary": summary.strip(),
                        "details": {}
                    }

                    # Parse details
                    if details_str:
                        for part in details_str.split(", "):
                            if "=" in part:
                                key, value = part.split("=", 1)
                                entry["details"][key.strip()] = value.strip()

                    entries.append(entry)

            return entries
        except Exception as e:
            print(f"Warning: Failed to get logs: {e}")
            return []

    def _check_prospective(self, tenant_id: str, context: str) -> Dict[str, Any]:
        """Check prospective memory triggers via /hooks/before-query."""
        return self._retrieve_memories(tenant_id, context)

    def test_selective_encoding(self) -> Tuple[int, int, List[str]]:
        """Test 1: Selective Encoding - classify and decide encoding."""
        print("\n=== Test 1: Selective Encoding ===")
        tenant_id = self._generate_tenant_id("encode")

        test_cases = [
            ("嗯嗯", "noise", False),
            ("我决定下周去上海面试", "cognition", True),
            ("帮我查天气", "command", False),
            ("中午吃了牛肉面600大卡", "log_diet", True),
        ]

        passed = 0
        total = len(test_cases)
        details = []

        for message, expected_type, should_encode in test_cases:
            self._encode_message(tenant_id, message, sleep_after=1.0)  # Small delay

            # Wait for perceiver log to appear
            perceiver_log = self._wait_for_perceiver_log(message)

            if perceiver_log:
                actual_type = perceiver_log.get("details", {}).get("type")
                actual_category = perceiver_log.get("details", {}).get("category", "")

                # For informative messages, check category
                if actual_type == "informative":
                    type_match = actual_category == expected_type
                else:
                    type_match = actual_type == expected_type

                if type_match:
                    passed += 1
                    details.append(f"✅ \"{message}\" → {expected_type} (correct)")
                else:
                    details.append(f"❌ \"{message}\" → expected {expected_type}, got {actual_type}/{actual_category}")
            else:
                details.append(f"❌ \"{message}\" → no perceiver log found")

        self.results.append({
            "dimension": "Selective Encoding",
            "passed": passed,
            "total": total,
            "details": details
        })

        return passed, total, details

    def test_vector_semantic_recall(self) -> Tuple[int, int, List[str]]:
        """Test 2: Vector Semantic Recall - retrieve by semantic similarity."""
        print("\n=== Test 2: Vector Semantic Recall ===")
        tenant_id = self._generate_tenant_id("vector")

        # Encode base memories
        print("Encoding base memories...")
        self._encode_message(tenant_id, "张三在字节跳动做大模型研发")
        self._encode_message(tenant_id, "我的减肥目标是从90kg减到85kg")

        # Wait longer for consolidation and embedding generation
        print("Waiting for consolidation...")
        time.sleep(10)

        test_cases = [
            ("那个做AI的朋友", ["张三", "字节", "大模型"]),
            ("ByteDance的人", ["张三", "字节"]),
            ("体重管理的事", ["减肥", "90kg", "85kg", "体重"]),
            ("节食计划", ["减肥", "kg"]),
        ]

        passed = 0
        total = len(test_cases)
        details = []

        for query, expected_keywords in test_cases:
            result = self._retrieve_memories(tenant_id, query)
            context = result.get("data", {}).get("context", "")

            # Check if any expected keyword is in context
            found = any(kw in context for kw in expected_keywords)

            if found:
                passed += 1
                matched = [kw for kw in expected_keywords if kw in context]
                details.append(f"✅ \"{query}\" → recalled (matched: {', '.join(matched)})")
            else:
                details.append(f"❌ \"{query}\" → no relevant recall (expected: {', '.join(expected_keywords)})")

        self.results.append({
            "dimension": "Vector Semantic Recall",
            "passed": passed,
            "total": total,
            "details": details
        })

        return passed, total, details

    def test_noise_filtering(self) -> Tuple[int, int, List[str]]:
        """Test 3: Noise Filtering - filter out noise messages."""
        print("\n=== Test 3: Noise Filtering ===")
        tenant_id = self._generate_tenant_id("noise")

        noise_messages = ["嗯", "好的", "ok", "哈哈", "。。。"]

        # Encode noise messages
        print("Encoding noise messages...")
        for msg in noise_messages:
            self._encode_message(tenant_id, msg, sleep_after=3.0)

        # Try to retrieve with various queries
        queries = ["最近的事情", "我们聊了什么", "帮我回忆一下"]

        filtered_count = 0
        total = len(noise_messages)
        details = []

        for query in queries:
            result = self._retrieve_memories(tenant_id, query)
            context = result.get("data", {}).get("context", "")

            # Check if noise messages appear in context
            noise_found = [msg for msg in noise_messages if msg in context]

            if not noise_found:
                filtered_count += 1

        # If none of the queries returned noise, all noise was filtered
        if filtered_count == len(queries):
            passed = total
            details.append(f"✅ All {total} noise messages filtered correctly")
        else:
            passed = 0
            details.append(f"❌ Noise messages leaked into retrieval")

        self.results.append({
            "dimension": "Noise Filtering",
            "passed": passed,
            "total": total,
            "details": details
        })

        return passed, total, details

    def test_classification_routing(self) -> Tuple[int, int, List[str]]:
        """Test 4: Classification Routing - route to correct categories."""
        print("\n=== Test 4: Classification Routing ===")
        tenant_id = self._generate_tenant_id("classify")

        test_cases = [
            ("我决定跳槽", "cognition"),
            ("午餐吃了沙拉300大卡", "log_diet"),
            ("今天跑了5公里", "log_exercise"),
            ("面试聊了系统设计", "log_interview"),
            ("嗯嗯", "noise"),
            ("帮我搜一下", "command"),
        ]

        passed = 0
        total = len(test_cases)
        details = []

        for message, expected_category in test_cases:
            self._encode_message(tenant_id, message, sleep_after=1.0)  # Small delay

            # Wait for perceiver log to appear
            perceiver_log = self._wait_for_perceiver_log(message)

            if perceiver_log:
                msg_type = perceiver_log.get("details", {}).get("type")
                category = perceiver_log.get("details", {}).get("category", "")

                # For noise/command, check type; for others, check category
                if expected_category in ["noise", "command"]:
                    actual = msg_type
                else:
                    actual = category

                if actual == expected_category:
                    passed += 1
                    details.append(f"✅ \"{message}\" → {expected_category} (correct)")
                else:
                    details.append(f"❌ \"{message}\" → expected {expected_category}, got {actual}")
            else:
                details.append(f"❌ \"{message}\" → no classification log found")

        self.results.append({
            "dimension": "Classification Routing",
            "passed": passed,
            "total": total,
            "details": details
        })

        return passed, total, details

    def test_reconsolidation(self) -> Tuple[int, int, List[str]]:
        """Test 5: Reconsolidation - update conflicting memories."""
        print("\n=== Test 5: Reconsolidation ===")
        tenant_id = self._generate_tenant_id("recon")

        # Encode initial memory
        print("Encoding initial memory...")
        self._encode_message(tenant_id, "腾讯面试挂了")

        # Encode correction
        print("Encoding correction...")
        self._encode_message(tenant_id, "不对，腾讯面试其实过了")

        # Wait for processing
        time.sleep(2)

        # Retrieve and check
        result = self._retrieve_memories(tenant_id, "腾讯面试结果")
        context = result.get("data", {}).get("context", "")

        passed = 0
        total = 1
        details = []

        # Check if correction is reflected
        if "过了" in context or "通过" in context:
            passed = 1
            details.append(f"✅ Reconsolidation successful - correction reflected")
        else:
            details.append(f"❌ Reconsolidation failed - correction not found in context")

        self.results.append({
            "dimension": "Reconsolidation",
            "passed": passed,
            "total": total,
            "details": details
        })

        return passed, total, details

    def test_prospective_memory(self) -> Tuple[int, int, List[str]]:
        """Test 6: Prospective Memory - trigger reminders based on context."""
        print("\n=== Test 6: Prospective Memory ===")
        tenant_id = self._generate_tenant_id("prospect")

        # Encode prospective memory
        print("Encoding prospective memory...")
        self._encode_message(tenant_id, "下次聊到字节时提醒我问面试进度")

        # Wait for processing
        time.sleep(2)

        # Test positive trigger
        result_positive = self._check_prospective(tenant_id, "字节跳动那边怎么样了")
        context_positive = result_positive.get("data", {}).get("context", "")

        # Test negative trigger
        result_negative = self._check_prospective(tenant_id, "今天天气真好")
        context_negative = result_negative.get("data", {}).get("context", "")

        passed = 0
        total = 2
        details = []

        # Check positive trigger
        if "提醒" in context_positive or "面试进度" in context_positive:
            passed += 1
            details.append(f"✅ Positive trigger activated (context contains reminder)")
        else:
            details.append(f"❌ Positive trigger failed (no reminder in context)")

        # Check negative trigger
        if "提醒" not in context_negative and "面试进度" not in context_negative:
            passed += 1
            details.append(f"✅ Negative trigger correct (no false activation)")
        else:
            details.append(f"❌ Negative trigger failed (false activation)")

        self.results.append({
            "dimension": "Prospective Memory",
            "passed": passed,
            "total": total,
            "details": details
        })

        return passed, total, details

    def generate_report(self, output_path: str):
        """Generate markdown report."""
        total_passed = sum(r["passed"] for r in self.results)
        total_tests = sum(r["total"] for r in self.results)
        overall_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0

        lines = [
            "# Brain-Mem Benchmark Results",
            f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Server: {self.base_url}",
            "",
            "| Dimension | Tests | Passed | Rate |",
            "|:----------|------:|-------:|-----:|",
        ]

        for result in self.results:
            dimension = result["dimension"]
            total = result["total"]
            passed = result["passed"]
            rate = (passed / total * 100) if total > 0 else 0
            lines.append(f"| {dimension} | {total} | {passed} | {rate:.1f}% |")

        lines.extend([
            "",
            f"**Overall: {total_passed}/{total_tests} ({overall_rate:.1f}%)**",
            "",
            "## Detailed Results",
        ])

        for result in self.results:
            lines.append(f"### {result['dimension']}")
            for detail in result["details"]:
                lines.append(f"- {detail}")
            lines.append("")

        report = "\n".join(lines)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"\n✅ Report generated: {output_path}")
        print(f"\nOverall: {total_passed}/{total_tests} ({overall_rate:.1f}%)")

    def run_all(self):
        """Run all benchmark tests."""
        print(f"Starting benchmark against {self.base_url}")
        print("=" * 60)

        try:
            self.test_selective_encoding()
            self.test_vector_semantic_recall()
            self.test_noise_filtering()
            self.test_classification_routing()
            self.test_reconsolidation()
            self.test_prospective_memory()
        except Exception as e:
            print(f"\n❌ Benchmark failed: {e}")
            raise
        finally:
            self.client.close()


def main():
    parser = argparse.ArgumentParser(description="Brain-Mem Benchmark Framework")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8100",
        help="Base URL of brain-mem service (default: http://localhost:8100)"
    )
    parser.add_argument(
        "--output",
        default="benchmark/RESULTS.md",
        help="Output path for results (default: benchmark/RESULTS.md)"
    )

    args = parser.parse_args()

    runner = BenchmarkRunner(args.base_url)
    runner.run_all()
    runner.generate_report(args.output)


if __name__ == "__main__":
    main()
