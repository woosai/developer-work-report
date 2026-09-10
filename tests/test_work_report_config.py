import copy
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from developer_work_report_config import render, validate_config


class OperationalArtifactConfigTest(unittest.TestCase):
    def config(self):
        return {
            "version": 1,
            "timezone": "Asia/Seoul",
            "execution": {"environment": "local", "project_path": "/tmp", "project_id": "project"},
            "git": {"author_emails": ["developer@example.com"]},
            "automations": {
                "collection": {"id": "collection", "name": "Collection", "enabled": True, "weekdays": ["MO"], "time": "18:00", "skip_public_holidays": True},
                "recovery": {"id": "recovery", "name": "Recovery", "enabled": True, "weekdays": ["MO"], "time": "09:00", "skip_public_holidays": True},
            },
            "sources": [{"name": "project", "path": "/tmp", "enabled": True, "collect": ["code"], "from": None, "until": None}],
            "session_sources": [],
            "destinations": [
                {"name": "primary", "provider": "google_drive", "folder_url": "https://drive.google.com/drive/folders/primary", "enabled": True},
                {"name": "mirror", "provider": "google_drive", "folder_url": "https://drive.google.com/drive/folders/mirror", "enabled": True},
            ],
            "operational_artifacts": {"google_drive_verification": {"destination": "mirror", "filename_prefix": "google-drive-", "range_date": "completion_date"}},
            "privacy": {"mask_prompts": True, "mask_home_user": True, "exclude_secrets": True, "withhold_on_uncertainty": True},
        }

    def test_operational_artifact_rule_is_rendered_for_both_automations(self):
        rendered = render(self.config(), Path("/tmp/config.json"))
        for prompt in (rendered["collection"]["prompt"], rendered["recovery"]["prompt"]):
            self.assertIn("Google Drive verification/recovery operational artifacts", prompt)
            self.assertIn("`mirror` destination", prompt)
            self.assertIn("`google-drive-`", prompt)
            self.assertIn("project-root copy", prompt)

    def test_operational_artifact_destination_must_exist(self):
        config = copy.deepcopy(self.config())
        config["operational_artifacts"]["google_drive_verification"]["destination"] = "missing"
        errors, _ = validate_config(config, check_paths=False)
        self.assertIn(
            "operational_artifacts.google_drive_verification.destination must name a configured destination",
            errors,
        )


if __name__ == "__main__":
    unittest.main()
