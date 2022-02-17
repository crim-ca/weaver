import json
import os
import tempfile

import pytest

from tests.functional.test_cli import TestWeaverClientBase
from tests.utils import mocked_sub_requests, run_command
from weaver.cli import main as weaver_cli
from weaver.formats import ContentType


@pytest.mark.vault
class TestVault(TestWeaverClientBase):
    def setUp(self):
        pass  # skip setup processes

    def test_vault_encrypted_decrypted_contents(self):
        """
        Validate that Vault file gets encrypted on upload, that description still works, and is decrypted on download.
        """
        # upload file
        data = {"fake": "data"}
        text = json.dumps(data)
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w+") as tmp_file:
            tmp_file.write(text)
            tmp_file.seek(0)
            tmp_name = os.path.split(tmp_file.name)[-1]
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # weaver
                    "upload",
                    "-u", self.url,
                    "-f", tmp_file.name,
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
        result = json.loads("\n".join(lines))
        assert "file_id" in result

        # check encrypted contents in vault
        vault_dir = self.settings.get("weaver.vault_dir")
        vault_id = result["file_id"]
        vault_path = os.path.join(vault_dir, vault_id, tmp_name)
        with open(vault_path, "r") as vault_fd:
            vault_data = vault_fd.read()
        assert vault_data != data
        assert "{" not in vault_data
        assert vault_data.endswith("=")

        # check details
        vault_token = result["access_token"]
        vault_url = f"/vault/{vault_id}"
        resp = mocked_sub_requests(self.app, "HEAD", vault_url, headers={"X-Auth-Vault": vault_token})
        assert resp.status_code == 200
        assert resp.headers["Content-Type"].startswith(ContentType.APP_JSON)

        # check download decrypted
        resp = mocked_sub_requests(self.app, "GET", vault_url, headers={"X-Auth-Vault": vault_token})
        assert resp.status_code == 200
        assert resp.text == text
