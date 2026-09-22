import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.lineage.build_dashboard import build_dashboard
from tools.lineage.inspect_workbook import inspect_workbook
from tools.lineage.sanitize_telemetry import (
    confidential_findings,
    iter_secret_matches,
    sanitize_run,
)


class LineageArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source-run"
        self.output = self.root / "telemetry" / "run-2"
        self.repo = self.root / "repo"
        self.workbook = (
            self.repo
            / "docs"
            / "lineage"
            / "model-storage-checker-lineage-run-2.xlsx"
        )
        self._initialize_repo()
        self._write_source_run()
        self._write_publication_metadata()
        self._write_test_workbook()

    def test_sanitizer_redacts_confidential_structure_and_keeps_evidence(
        self,
    ) -> None:
        summary = sanitize_run(
            source_root=self.source,
            output_root=self.output,
            repo_root=self.repo,
            package_branch="package-layer",
        )

        sanitized_records = [
            json.loads(line)
            for line in (
                self.output / "otel" / "orchestrator.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        serialized = json.dumps(sanitized_records, sort_keys=True)

        self.assertNotIn("hidden system value", serialized)
        self.assertNotIn("hidden developer value", serialized)
        self.assertNotIn("confidential tool schema", serialized)
        self.assertNotIn("/private/runtime-policy", serialized)
        self.assertNotIn(self.github_token, serialized)
        self.assertIn("ordinary user instructions remain public", serialized)
        self.assertIn("assistant response remains public", serialized)
        self.assertIn("echo retained", serialized)
        self.assertIn("tool result remains public", serialized)
        self.assertFalse(confidential_findings(sanitized_records))
        self.assertFalse(list(iter_secret_matches(serialized)))

        prompt_source = (self.source / "prompts" / "orchestrator.md").read_bytes()
        prompt_copy = (self.output / "prompts" / "orchestrator.md").read_bytes()
        self.assertEqual(prompt_source, prompt_copy)

        report = json.loads(
            (self.output / "redaction-report.json").read_text(
                encoding="utf-8"
            )
        )
        categories = report["summary"]["by_category"]
        self.assertGreater(categories["system_instructions"], 0)
        self.assertGreater(categories["system_message"], 0)
        self.assertGreater(categories["developer_message"], 0)
        self.assertGreater(categories["tool_definitions"], 0)
        self.assertGreater(categories["sandbox_policy"], 0)
        self.assertGreater(categories["credential_field"], 0)
        self.assertTrue(
            all(
                "original_sha256" in entry
                and "replacement_marker" in entry
                and "json_path" in entry
                for entry in report["entries"]
            )
        )

        validation = summary["validation"]
        self.assertEqual(validation["confidential_structural_findings"], 0)
        self.assertEqual(validation["secret_scan"]["total_matches"], 0)
        self.assertTrue(
            validation["preservation"]["user_messages"]["exact_match"]
        )
        self.assertTrue(
            validation["preservation"]["assistant_messages"]["exact_match"]
        )
        self.assertTrue(
            validation["preservation"]["tool_call_results"]["exact_match"]
        )

        manifest = json.loads(
            (self.output / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertIsNone(manifest["pull_request"])
        self.assertIsNone(manifest["release"])
        self.assertEqual(
            manifest["children"][0]["pull_request"]["number"], 1
        )
        self.assertEqual(
            manifest["children"][0]["pull_request"]["head_sha"],
            self.commit_sha,
        )
        self.assertNotIn("launcher", manifest)
        self.assertNotIn("run_directory", manifest)
        self.assertNotIn("error", manifest["children"][0])
        self.assertNotIn(
            "recovery", manifest["children"][0]["verification"]
        )

    def test_dashboard_uses_only_sanitized_evidence_and_git_metadata(
        self,
    ) -> None:
        sanitize_run(
            source_root=self.source,
            output_root=self.output,
            repo_root=self.repo,
            package_branch="package-layer",
        )
        workbook_report = inspect_workbook(
            self.workbook,
            reported_path=(
                "docs/lineage/model-storage-checker-lineage-run-2.xlsx"
            ),
        )
        workbook_report_path = (
            self.output / "validation" / "workbook-safety.json"
        )
        workbook_report_path.write_text(
            json.dumps(workbook_report), encoding="utf-8"
        )
        dashboard_path = self.repo / "docs" / "lineage" / "data.json"

        data = build_dashboard(
            telemetry_root=self.output,
            output_path=dashboard_path,
            repo_root=self.repo,
        )

        serialized = json.dumps(data, sort_keys=True)
        kinds = {item["kind"] for item in data["nodes"]}
        self.assertIn("prompt", kinds)
        self.assertIn("session", kinds)
        self.assertIn("process", kinds)
        self.assertIn("trace-group", kinds)
        self.assertIn("model-group", kinds)
        self.assertIn("tool-group", kinds)
        self.assertIn("commit", kinds)
        self.assertIn("branch", kinds)
        self.assertIn("pull-request", kinds)
        self.assertIn("release", kinds)
        self.assertIn("ordinary user instructions remain public", serialized)
        self.assertIn("assistant response remains public", serialized)
        self.assertIn("echo retained", serialized)
        self.assertIn("tool result remains public", serialized)
        self.assertNotIn("hidden system value", serialized)
        self.assertNotIn("confidential tool schema", serialized)
        self.assertNotIn(self.github_token, serialized)
        self.assertIn("host-driven", serialized.casefold())
        self.assertIn("w3c", serialized.casefold())
        layer_pr = next(
            item
            for item in data["nodes"]
            if item["kind"] == "pull-request" and item["layer"] == 1
        )
        self.assertEqual(layer_pr["label"], "PR #1")
        self.assertEqual(layer_pr["status"], "live")
        self.assertIsNone(data["details"]["release"]["metadata"])
        self.assertTrue(dashboard_path.is_file())
        integrity = json.loads(
            (self.output / "artifact-integrity.json").read_text(
                encoding="utf-8"
            )
        )
        external_paths = {
            item["path"] for item in integrity["external_generated_files"]
        }
        self.assertEqual(
            external_paths,
            {
                "docs/lineage/data.json",
                "docs/lineage/model-storage-checker-lineage-run-2.xlsx",
            },
        )
        self.assertTrue(
            any(
                item["path"] == "publication-metadata.json"
                for item in integrity["files"]
            )
        )
        self.assertTrue(
            any(
                item["path"] == "validation/workbook-safety.json"
                for item in integrity["files"]
            )
        )

    def test_workbook_inspection_rejects_external_formula_references(
        self,
    ) -> None:
        unsafe_workbook = self.root / "unsafe.xlsx"
        self._write_test_workbook(
            path=unsafe_workbook,
            formula="[outside.xlsx]Sheet1!A1",
        )

        report = inspect_workbook(
            unsafe_workbook,
            reported_path="unsafe.xlsx",
        )

        self.assertFalse(report["safe"])
        self.assertEqual(report["features"]["formula_count"], 1)
        self.assertEqual(
            len(report["findings"]["external_formula_references"]), 1
        )

    def test_publication_metadata_must_match_verified_commit_lineage(
        self,
    ) -> None:
        metadata_path = self.output / "publication-metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["pull_requests"]["layer-one"]["head_sha"] = "0" * 40
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "does not match"):
            sanitize_run(
                source_root=self.source,
                output_root=self.output,
                repo_root=self.repo,
                package_branch="package-layer",
            )

    def _initialize_repo(self) -> None:
        self.repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.name", "Test User"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "config",
                "user.email",
                "test@example.com",
            ],
            check=True,
        )
        (self.repo / "fixture.txt").write_text("fixture\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.repo), "add", "fixture.txt"], check=True
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "commit",
                "-q",
                "-m",
                "feat: synthetic layer\n\n"
                "Copilot-Session-ID: child-session\n"
                "Co-authored-by: Copilot App "
                "<223556219+Copilot@users.noreply.github.com>",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "branch", "layer-one"], check=True
        )
        self.commit_sha = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.parent_sha = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD^"],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.tree_sha = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD^{tree}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def _write_source_run(self) -> None:
        for directory in ("raw", "prompts", "usage", "validation"):
            (self.source / directory).mkdir(parents=True, exist_ok=True)
        (self.source / "prompts" / "orchestrator.md").write_text(
            "ordinary origin prompt\n", encoding="utf-8"
        )
        (self.source / "prompts" / "layer-1.md").write_text(
            "ordinary delegated prompt\n", encoding="utf-8"
        )

        self.github_token = "gh" + "p_" + ("a" * 36)
        input_messages = [
            {"role": "system", "content": "hidden system value"},
            {"role": "developer", "content": "hidden developer value"},
            {
                "role": "user",
                "content": "ordinary user instructions remain public",
            },
            {"role": "tool", "content": "tool result remains public"},
        ]
        output_messages = [
            {
                "role": "assistant",
                "parts": [
                    {
                        "type": "tool_call",
                        "name": "bash",
                        "arguments": {"command": "echo retained"},
                    }
                ],
                "content": "assistant response remains public",
            }
        ]
        record = {
            "type": "span",
            "traceId": "1" * 32,
            "spanId": "2" * 16,
            "name": "chat test-model",
            "kind": 3,
            "startTime": [1, 0],
            "endTime": [2, 0],
            "status": {"code": 1},
            "events": [],
            "instrumentationScope": {"name": "fixture", "version": "1"},
            "resource": {
                "attributes": {
                    "service.name": "copilot-client",
                    "poc.session_id": "parent-session",
                    "poc.role": "parent",
                    "poc.invocation": "orchestrator",
                },
                "schemaUrl": "",
            },
            "attributes": {
                "gen_ai.input.messages": json.dumps(input_messages),
                "gen_ai.output.messages": json.dumps(output_messages),
                "gen_ai.system_instructions": json.dumps(
                    [{"type": "text", "content": "hidden system value"}]
                ),
                "gen_ai.tool.definitions": json.dumps(
                    [
                        {
                            "name": "bash",
                            "description": "confidential tool schema",
                            "parameters": {"type": "object"},
                        }
                    ]
                ),
                "gen_ai.request.model": "test-model",
                "gen_ai.response.model": "test-model",
                "gen_ai.tool.name": "bash",
                "gen_ai.tool.type": "function",
                "gen_ai.tool.call.id": "call-1",
                "gen_ai.tool.call.arguments": json.dumps(
                    {
                        "command": "echo retained",
                        "authorization": self.github_token,
                    }
                ),
                "gen_ai.tool.call.result": json.dumps(
                    {"stdout": "tool result remains public"}
                ),
                "nested_request": json.dumps(
                    {
                        "request": {
                            "tools": [
                                {
                                    "name": "hidden",
                                    "description": "confidential tool schema",
                                }
                            ]
                        },
                        "public": "retained",
                    }
                ),
                "github.copilot.sandbox.policy.readonly_paths": [
                    "/private/runtime-policy"
                ],
            },
        }
        capture_names = [
            "orchestrator",
            "layer-1",
            "layer-1-resume",
            "layer-2",
            "layer-3",
            "layer-4",
            "layer-5",
            "05-reporting-resume-attempt-2",
            "05-reporting-resume-attempt-3",
            "05-reporting-resume-attempt-4",
        ]
        for name in capture_names:
            capture = json.loads(json.dumps(record))
            if name != "orchestrator":
                capture["resource"]["attributes"].update(
                    {
                        "poc.session_id": "child-session",
                        "poc.parent_session_id": "parent-session",
                        "poc.role": "child",
                        "poc.layer": 1,
                        "poc.invocation": name,
                    }
                )
            (self.source / "raw" / f"{name}.jsonl").write_text(
                json.dumps(capture) + "\n", encoding="utf-8"
            )

        audit_records = [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "event": "process_started",
                "role": "parent",
                "session_id": "parent-session",
                "parent_session_id": None,
                "layer": None,
                "cwd": str(self.repo),
                "worktree": str(self.repo),
                "environment_variable_names": ["SAFE_NAME"],
                "secret_environment_variable_names": ["TOKEN_NAME"],
                "sanitized_argv": ["copilot", "--autopilot"],
                "artifact_paths": {
                    "prompt": str(
                        self.source / "prompts" / "orchestrator.md"
                    ),
                    "telemetry": str(
                        self.source / "raw" / "orchestrator.jsonl"
                    ),
                },
            },
            {
                "timestamp": "2026-01-01T00:00:01Z",
                "event": "process_completed",
                "role": "child",
                "session_id": "child-session",
                "parent_session_id": "parent-session",
                "layer": 1,
                "exit_code": 0,
            },
        ]
        (self.source / "driver-audit.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in audit_records),
            encoding="utf-8",
        )
        (self.source / "usage" / "orchestrator.json").write_text(
            json.dumps(
                {
                    "totalUserRequests": 1,
                    "totalPremiumRequestCost": 1,
                    "totalNanoAiu": 1,
                    "totalApiDurationMs": 1,
                    "tokenDetails": {
                        "input": {"tokenCount": 10},
                        "output": {"tokenCount": 5},
                    },
                    "currentModel": "test-model",
                    "codeChanges": {},
                    "modelMetrics": {},
                }
            ),
            encoding="utf-8",
        )
        (self.source / "usage" / "layer-1.json").write_text(
            (self.source / "usage" / "orchestrator.json").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        (self.source / "validation" / "final-validation.json").write_text(
            json.dumps(
                {
                    "status": "passed",
                    "logical_sessions": 2,
                    "process_capture_files": 10,
                    "otel_records": 10,
                    "otel_spans": 10,
                    "driver_audit_records": 2,
                    "final_tests": {
                        "python": "3.11",
                        "tests_run": 1,
                        "passed": True,
                        "log": str(
                            self.source / "logs" / "final-tests.log"
                        ),
                    },
                }
            ),
            encoding="utf-8",
        )
        (self.source / "validation" / "run-failure.json").write_text(
            json.dumps({"error": "stale failure"}), encoding="utf-8"
        )

        manifest = {
            "schema_version": 1,
            "poc": {"name": "synthetic lineage", "run": 2},
            "created_at": "2026-01-01T00:00:00Z",
            "status": "completed",
            "repository": {
                "full_name": "example/repo",
                "origin_main_sha": self.commit_sha,
                "production_dependencies": "Python standard library only",
            },
            "run_directory": str(self.source),
            "worktree_root": str(self.repo),
            "host_app_session_id": "host-session",
            "orchestration": {
                "mode": "host-driven",
                "process_nesting": False,
                "linkage": "logical session identifiers",
                "description": "Host-driven logical lineage.",
                "limitation": "No W3C propagation.",
            },
            "launcher": {
                "capture_message_content": True,
                "flags": ["--autopilot"],
            },
            "preflight_evidence": {
                "nested_smoke_attempts": [
                    {
                        "directory": str(self.source),
                        "result": "failed",
                        "limitation": "host-driven",
                    }
                ]
            },
            "parent": {
                "role": "orchestrator",
                "session_id": "parent-session",
                "status": "verified",
                "prompt_path": str(
                    self.source / "prompts" / "orchestrator.md"
                ),
                "telemetry_path": str(
                    self.source / "raw" / "orchestrator.jsonl"
                ),
                "usage_path": str(
                    self.source / "usage" / "orchestrator.json"
                ),
                "started_at": "2026-01-01T00:00:00Z",
                "ended_at": "2026-01-01T00:00:01Z",
                "exit_code": 0,
                "verification": {"passed": True, "otel_records": 1},
            },
            "children": [
                {
                    "layer": 1,
                    "layer_name": "Synthetic layer",
                    "session_id": "child-session",
                    "parent_session_id": "parent-session",
                    "branch": "layer-one",
                    "base_branch": "main",
                    "worktree": str(self.repo),
                    "commit_subject": "feat: synthetic layer",
                    "status": "verified",
                    "prompt_path": str(
                        self.source / "prompts" / "layer-1.md"
                    ),
                    "telemetry_path": str(
                        self.source / "raw" / "layer-1.jsonl"
                    ),
                    "usage_path": str(
                        self.source / "usage" / "layer-1.json"
                    ),
                    "started_at": "2026-01-01T00:00:00Z",
                    "ended_at": "2026-01-01T00:00:01Z",
                    "process_exit_code": 0,
                    "commit_sha": self.commit_sha,
                    "parent_sha": self.parent_sha,
                    "tree_sha": self.tree_sha,
                    "error": "stale intermediate error",
                    "tests": [
                        {
                            "argv": ["python", "-m", "unittest"],
                            "exit_code": 0,
                            "log": str(
                                self.source / "logs" / "layer-1.log"
                            ),
                        }
                    ],
                    "process_invocations": [
                        {
                            "kind": "initial",
                            "exit_code": 0,
                            "telemetry_path": str(
                                self.source / "raw" / "layer-1.jsonl"
                            ),
                            "usage_path": str(
                                self.source / "usage" / "layer-1.json"
                            ),
                        }
                    ],
                    "verification": {
                        "passed": True,
                        "tests_passed": True,
                        "error": "stale verification error",
                        "recovery": "stale recovery note",
                    },
                }
            ],
            "validation": {
                "logical_sessions": 2,
                "process_capture_files": 10,
                "otel_records": 10,
                "otel_spans": 10,
                "output_json_records": 0,
                "driver_audit_records": 2,
                "captures": [],
                "final_tests": {
                    "python": "3.11",
                    "tests_run": 1,
                    "passed": True,
                },
            },
        }
        (self.source / "run-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def _write_publication_metadata(self) -> None:
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / "publication-metadata.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pull_requests": {
                        "layer-one": {
                            "number": 1,
                            "url": "https://github.com/example/repo/pull/1",
                            "state": "open",
                            "draft": False,
                            "base": "main",
                            "head_sha": self.commit_sha,
                        }
                    },
                    "release": None,
                }
            ),
            encoding="utf-8",
        )

    def _write_test_workbook(
        self,
        *,
        path: Path | None = None,
        formula: str | None = None,
    ) -> None:
        workbook = path or (
            self.workbook
        )
        workbook.parent.mkdir(parents=True, exist_ok=True)
        formula_xml = (
            f'<row r="1"><c r="A1"><f>{formula}</f></c></row>'
            if formula is not None
            else ""
        )
        entries = {
            "[Content_Types].xml": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                "</Types>"
            ),
            "_rels/.rels": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                "</Relationships>"
            ),
            "xl/workbook.xml": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Summary" sheetId="1" r:id="rId1"/></sheets>'
                "</workbook>"
            ),
            "xl/_rels/workbook.xml.rels": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                "</Relationships>"
            ),
            "xl/worksheets/sheet1.xml": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"<sheetData>{formula_xml}</sheetData>"
                "</worksheet>"
            ),
        }
        with zipfile.ZipFile(
            workbook, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for name, content in entries.items():
                archive.writestr(name, content)


if __name__ == "__main__":
    unittest.main()
