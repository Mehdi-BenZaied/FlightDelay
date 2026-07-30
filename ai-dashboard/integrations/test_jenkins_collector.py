from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("jenkins_collector.py")
SPEC = importlib.util.spec_from_file_location("jenkins_collector", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
collector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)


class CollectorContractTest(unittest.TestCase):
    def test_finds_archived_analysis(self) -> None:
        build = {
            "artifacts": [
                {
                    "fileName": "ai-failure-analysis.json",
                    "relativePath": "ai-failure-analysis.json",
                }
            ]
        }
        self.assertEqual(
            collector.find_artifact(build, "ai-failure-analysis.json"),
            "ai-failure-analysis.json",
        )

    def test_builds_dashboard_envelope(self) -> None:
        build = {
            "number": 24,
            "url": "http://jenkins/job/FlightDelay/job/main/24/",
            "result": "FAILURE",
            "timestamp": 1785400000000,
            "duration": 125000,
            "artifacts": [],
            "actions": [
                {
                    "parameters": [
                        {"name": "SOURCE_BRANCH", "value": "main"},
                        {
                            "name": "OLLAMA_MODEL",
                            "value": "qwen2.5-coder:3b-instruct",
                        },
                    ],
                    "lastBuiltRevision": {"SHA1": "0123456789abcdef"},
                }
            ],
        }
        analysis = {
            "analysis_status": "probable",
            "summary": "Redis refused the backend connection.",
        }

        payload = collector.create_ingest_payload(build, analysis)

        self.assertEqual(payload["jenkins"]["build_number"], 24)
        self.assertEqual(payload["jenkins"]["branch"], "main")
        self.assertEqual(payload["jenkins"]["commit_sha"], "0123456789ab")
        self.assertEqual(
            payload["jenkins"]["model"], "qwen2.5-coder:3b-instruct"
        )
        self.assertIs(payload["analysis"], analysis)


if __name__ == "__main__":
    unittest.main()
