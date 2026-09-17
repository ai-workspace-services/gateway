import unittest
from pathlib import Path

from gatewayctl.validation import ManifestError, load_yaml, validate_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "contracts" / "gateway.yaml"


class ContractTests(unittest.TestCase):
    def test_reference_manifest_is_valid(self):
        summary = validate_manifest(load_yaml(MANIFEST))
        self.assertEqual(summary["adapter"], "kong")
        self.assertEqual(summary["route_count"], 2)

    def test_direct_host_cannot_point_to_new_api(self):
        manifest = load_yaml(MANIFEST)
        manifest["routes"][0]["hosts"] = ["direct.ai.onwalk.net"]
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_sensitive_fields_are_rejected(self):
        manifest = load_yaml(MANIFEST)
        manifest["tenants"][0]["api_key"] = "must-not-exist"
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_old_vault_paths_are_rejected(self):
        manifest = load_yaml(MANIFEST)
        manifest["gateway"]["secret_ref"] = "vault://kv/uat/ai-aggregator/accounts/foo"
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_host_outside_environment_domains_is_rejected(self):
        manifest = load_yaml(MANIFEST)
        manifest["routes"][0]["hosts"] = ["ai.svc.plus"]
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
