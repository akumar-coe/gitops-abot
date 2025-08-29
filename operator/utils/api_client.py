from __future__ import annotations
import requests
from typing import Dict, Any, Optional

class AbotClient:
    """
    Thin client around Abot REST APIs used by the operator.
    Expects base_url like: https://<ABOT_HOST>
    Operator appends /abot/api/v5/* paths.
    """
    def __init__(self, base_url: str, email: str, password: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()
        self._login(email, password)

    def _login(self, email: str, password: str) -> None:
        r = self.s.post(
            f"{self.base_url}/abot/api/v5/login",
            json={"email": email, "password": password},
            timeout=self.timeout,
        )
        r.raise_for_status()
        token = r.json().get("token")
        if not token:
            raise RuntimeError("Abot login succeeded but no token in response.")
        self.s.headers.update({"Authorization": f"Bearer {token}"})

    # --- Optional discovery (if you want to validate tags) ---
    def get_feature_tags(self) -> Dict[str, Any]:
        r = self.s.get(f"{self.base_url}/abot/api/v5/feature_files_tags", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # --- Optional config update before execution ---
    def update_config_properties(
        self,
        filename: str,
        update: Optional[Dict[str, str]] = None,
        comment: Optional[list[str]] = None,
        uncomment: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        body = {
            "filename": filename,
            "data": {
                "update": update or {},
                "comment": comment or [],
                "uncomment": uncomment or [],
            },
        }
        r = self.s.post(
            f"{self.base_url}/abot/api/v5/update_config_properties",
            json=body,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    # --- Execute a single test by feature tag ---
    def execute_feature(self, params: str, build: str) -> Dict[str, Any]:
        body = {"params": params, "build": build}
        r = self.s.post(
            f"{self.base_url}/abot/api/v5/feature_files/execute",
            json=body,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()  # may or may not include a run id

    # --- Polling endpoints ---
    def execution_status(self) -> Dict[str, Any]:
        r = self.s.get(f"{self.base_url}/abot/api/v5/execution_status", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def detail_execution_status(self) -> Dict[str, Any]:
        r = self.s.get(f"{self.base_url}/abot/api/v5/detail_execution_status", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # --- Artifacts (optional) ---
    def latest_artifact_name(self) -> Dict[str, Any]:
        r = self.s.get(f"{self.base_url}/abot/api/v5/latest_artifact_name", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def download_test_log(self) -> str:
        r = self.s.get(f"{self.base_url}/abot/api/v5/download_testautomation_log", timeout=self.timeout)
        r.raise_for_status()
        return r.text

