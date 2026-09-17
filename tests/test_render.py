import json
import tempfile
import unittest
from pathlib import Path

from gatewayctl.render import render_manifest
from gatewayctl.validation import load_yaml, validate_manifest


ROOT = Path(__file__).resolve().parents[1]


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_yaml(ROOT / "contracts" / "gateway.yaml")
        validate_manifest(cls.manifest)

    def render(self, adapter):
        with tempfile.TemporaryDirectory(prefix="ai-gateway-test-") as directory:
            result = render_manifest(self.manifest, adapter, directory)
            files = {
                name: (Path(directory) / name).read_text(encoding="utf-8")
                for name in result["files"]
            }
        return result, files

    def test_caddy_is_scoped_to_ai_hosts(self):
        result, files = self.render("caddy")
        self.assertIn("ai.onwalk.net", files["Caddyfile.ai-gateway"])
        self.assertIn("direct.ai.onwalk.net", files["Caddyfile.ai-gateway"])
        self.assertIn("reverse_proxy 127.0.0.1:8000", files["Caddyfile.ai-gateway"])
        self.assertNotIn("remote_ip", files["Caddyfile.ai-gateway"])
        self.assertNotIn("accounts.svc.plus", files["Caddyfile.ai-gateway"])
        self.assertEqual(result["report"]["adapter"], "caddy")

    def test_caddy_targets_selected_apisix_adapter(self):
        manifest = {**self.manifest, "gateway": {**self.manifest["gateway"], "adapter": "apisix"}}
        validate_manifest(manifest)
        with tempfile.TemporaryDirectory(prefix="ai-gateway-test-") as directory:
            render_manifest(manifest, "caddy", directory)
            caddyfile = (Path(directory) / "Caddyfile.ai-gateway").read_text(encoding="utf-8")
        self.assertIn("reverse_proxy 127.0.0.1:9080", caddyfile)

    def test_kong_bundle_has_separate_new_api_and_litellm_routes(self):
        _, files = self.render("kong")
        self.assertIn("ai-new-api", files["kong.yaml"])
        self.assertIn("ai-litellm", files["kong.yaml"])
        self.assertIn("tenant:personal", files["kong.yaml"])
        self.assertNotIn("name: kong", files["kong.yaml"])

    def test_kong_bundle_declares_gateway_scheduling_capability(self):
        result, files = self.render("kong")
        self.assertIn('"scheduling"', files["capability-report.json"])
        self.assertIn("timeouts", result["report"]["scheduling"])

    def test_apisix_reports_non_equivalent_database_capability(self):
        result, files = self.render("apisix")
        report = json.loads(files["capability-report.json"])
        self.assertEqual(result["report"]["mode"], "standalone-file-driven")
        self.assertIn("postgresql-runtime-config", report["unsupported_or_external"])
        self.assertIn("apisix.yaml", files)
        self.assertIn("consumer-restriction", files["apisix.yaml"])

    def test_apisix_uses_contract_auth_mode(self):
        manifest = {**self.manifest, "routes": [dict(self.manifest["routes"][0], auth={"mode": "jwt"})]}
        validate_manifest(manifest)
        with tempfile.TemporaryDirectory(prefix="ai-gateway-test-") as directory:
            render_manifest(manifest, "apisix", directory)
            apisix = (Path(directory) / "apisix.yaml").read_text(encoding="utf-8")
        self.assertIn("jwt-auth", apisix)
        self.assertNotIn("key-auth:", apisix)
