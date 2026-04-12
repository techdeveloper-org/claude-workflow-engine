"""
Jenkins integration adapter.

Maps the AbstractIntegration lifecycle to Jenkins CI/CD build operations.
Only active when ENABLE_JENKINS=1 and JENKINS_URL/JENKINS_USER/JENKINS_API_TOKEN
are set.

Lifecycle mapping:
  create()    -> Step 8:  no-op (Jenkins does not create issues)
  on_branch() -> Step 9:  no-op (Jenkins discovers branches automatically)
  update()    -> Step 10: trigger build on the implementation branch
  on_review() -> Step 11: validate build status before PR is merged
  close()     -> Step 12: trigger post-merge build on the default branch

Jenkins REST API uses Basic auth with base64(user:api_token).
Only stdlib urllib is used (no external dependencies).

Environment Variables:
  JENKINS_URL         - Base URL (e.g. https://jenkins.company.com)
  JENKINS_USER        - Username for API authentication
  JENKINS_API_TOKEN   - API token (NOT password; tokens bypass CSRF crumb)
  JENKINS_JOB_NAME    - Default job name to trigger (optional)
  JENKINS_VERIFY_SSL  - 'true' (default) or 'false' for self-signed certs

Version: 1.4.1
"""

import base64
import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from .base import AbstractIntegration, IntegrationState

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_JENKINS_REQUEST_TIMEOUT = 60  # seconds
_BUILD_POLL_INTERVAL = 10  # seconds between build status polls
_BUILD_POLL_MAX_WAIT = 300  # seconds before giving up on a build


class JenkinsIntegration(AbstractIntegration):
    """Jenkins CI/CD lifecycle integration for pipeline Steps 10-12.

    Calls the Jenkins REST API directly using stdlib urllib.  No external
    packages are required.

    The integration is stateless between pipeline steps: job_name and
    build_number are resolved from the context dict at each call site and
    also persisted in instance attributes as a convenience cache.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialise Jenkins integration adapter.

        Args:
            config: Must contain 'enabled' (bool).  Optional keys:
                - 'jenkins_url' (str): Overrides JENKINS_URL env var.
                - 'jenkins_user' (str): Overrides JENKINS_USER env var.
                - 'jenkins_api_token' (str): Overrides JENKINS_API_TOKEN.
                - 'jenkins_job_name' (str): Default job to trigger.
        """
        super().__init__(config)
        self._job_name: Optional[str] = config.get(
            "jenkins_job_name",
            os.environ.get("JENKINS_JOB_NAME", ""),
        )
        self._last_build_number: int = 0
        self._state = IntegrationState.READY if self.is_enabled else IntegrationState.DISABLED

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Return integration name."""
        return "jenkins"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_base_url(self) -> str:
        """Return the Jenkins base URL without a trailing slash."""
        url = (self._config.get("jenkins_url", "") or os.environ.get("JENKINS_URL", "")).rstrip("/")
        return url

    def _build_auth_header(self) -> str:
        """Build the Basic-auth header value."""
        user = self._config.get("jenkins_user", "") or os.environ.get("JENKINS_USER", "")
        token = self._config.get("jenkins_api_token", "") or os.environ.get("JENKINS_API_TOKEN", "")
        if not user or not token:
            return ""
        raw = "{}:{}".format(user, token)
        encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        return "Basic {}".format(encoded)

    def _ssl_context(self) -> Optional[ssl.SSLContext]:
        """Return an SSL context that skips verification when configured."""
        verify = os.environ.get("JENKINS_VERIFY_SSL", "true").strip().lower()
        if verify == "false":
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return None

    def _api_get(self, path: str) -> Optional[Dict[str, Any]]:
        """Perform a GET request to the Jenkins REST API.

        Args:
            path: URL path (e.g. '/job/my-job/api/json').

        Returns:
            Parsed JSON dict, or None on any error.
        """
        base = self._get_base_url()
        if not base:
            logger.debug("[JenkinsIntegration] JENKINS_URL not configured")
            return None

        url = base + path
        try:
            req = urllib.request.Request(url)
            req.add_header("Accept", "application/json")
            auth = self._build_auth_header()
            if auth:
                req.add_header("Authorization", auth)

            ctx = self._ssl_context()
            with urllib.request.urlopen(req, timeout=_JENKINS_REQUEST_TIMEOUT, context=ctx) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body.strip() else {}

        except urllib.error.HTTPError as exc:
            logger.debug("[JenkinsIntegration] GET %s failed: HTTP %d", path, exc.code)
            return None
        except urllib.error.URLError as exc:
            logger.debug("[JenkinsIntegration] GET %s unreachable: %s", path, exc.reason)
            return None
        except Exception as exc:
            logger.debug("[JenkinsIntegration] GET %s error: %s", path, exc)
            return None

    def _api_post(self, path: str, params: Optional[Dict[str, str]] = None) -> bool:
        """Perform a POST request to the Jenkins REST API.

        Args:
            path:   URL path (e.g. '/job/my-job/build').
            params: Optional query parameters appended to the URL.

        Returns:
            True when the server responded with 2xx, False otherwise.
        """
        base = self._get_base_url()
        if not base:
            logger.debug("[JenkinsIntegration] JENKINS_URL not configured")
            return False

        url = base + path
        if params:
            url = url + "?" + urllib.parse.urlencode(params)

        try:
            req = urllib.request.Request(url, data=b"", method="POST")
            req.add_header("Accept", "application/json")
            auth = self._build_auth_header()
            if auth:
                req.add_header("Authorization", auth)

            ctx = self._ssl_context()
            with urllib.request.urlopen(req, timeout=_JENKINS_REQUEST_TIMEOUT, context=ctx) as resp:
                return 200 <= resp.status < 300

        except urllib.error.HTTPError as exc:
            # 201 Created is returned by Jenkins for build triggers.
            if exc.code == 201:
                return True
            logger.debug("[JenkinsIntegration] POST %s failed: HTTP %d", path, exc.code)
            return False
        except urllib.error.URLError as exc:
            logger.debug("[JenkinsIntegration] POST %s unreachable: %s", path, exc.reason)
            return False
        except Exception as exc:
            logger.debug("[JenkinsIntegration] POST %s error: %s", path, exc)
            return False

    def _encode_job_path(self, job_name: str) -> str:
        """Convert a job name (with optional folder path) to a URL path.

        'folder/subfolder/job' -> '/job/folder/job/subfolder/job/job'

        Args:
            job_name: Jenkins job name or folder-qualified path.

        Returns:
            URL path string starting with '/job/'.
        """
        parts = job_name.strip("/").split("/")
        encoded_parts = [urllib.parse.quote(p, safe="") for p in parts if p]
        return "/job/" + "/job/".join(encoded_parts)

    def _get_next_build_number(self, job_name: str) -> int:
        """Fetch the next build number from the job's API endpoint.

        Args:
            job_name: Jenkins job name.

        Returns:
            Next build number as an int, or 0 on error.
        """
        job_path = self._encode_job_path(job_name)
        data = self._api_get("{}/api/json?tree=nextBuildNumber".format(job_path))
        if data is None:
            return 0
        return int(data.get("nextBuildNumber", 0))

    def _get_build_result(self, job_name: str, build_number: int) -> Optional[str]:
        """Fetch the result of a specific build.

        Args:
            job_name:     Jenkins job name.
            build_number: Build number to query.

        Returns:
            Result string ('SUCCESS', 'FAILURE', 'ABORTED', 'UNSTABLE'),
            None when the build is still in progress, or empty string on error.
        """
        job_path = self._encode_job_path(job_name)
        path = "{}/{}/api/json?tree=result,building".format(job_path, build_number)
        data = self._api_get(path)
        if data is None:
            return ""
        if data.get("building"):
            return None  # still running
        return data.get("result", "UNKNOWN")

    def _wait_for_build(self, job_name: str, build_number: int) -> Dict[str, Any]:
        """Poll until a build completes or times out.

        Args:
            job_name:     Jenkins job name.
            build_number: Build number to wait for.

        Returns:
            Dict with keys: result (str), build_number (int), timed_out (bool).
        """
        deadline = time.monotonic() + _BUILD_POLL_MAX_WAIT
        while time.monotonic() < deadline:
            result = self._get_build_result(job_name, build_number)
            if result is not None:  # None means still building
                logger.info(
                    "[JenkinsIntegration] Build #%d result: %s",
                    build_number,
                    result,
                )
                return {
                    "result": result,
                    "build_number": build_number,
                    "timed_out": False,
                }
            logger.debug(
                "[JenkinsIntegration] Build #%d still running; " "waiting %ds",
                build_number,
                _BUILD_POLL_INTERVAL,
            )
            time.sleep(_BUILD_POLL_INTERVAL)

        logger.warning(
            "[JenkinsIntegration] Build #%d timed out after %ds",
            build_number,
            _BUILD_POLL_MAX_WAIT,
        )
        return {
            "result": "TIMED_OUT",
            "build_number": build_number,
            "timed_out": True,
        }

    # ------------------------------------------------------------------
    # Lifecycle methods
    # ------------------------------------------------------------------

    def create(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 8: No-op - Jenkins does not create work items.

        Jenkins does not have an issue or ticket concept in the pipeline.
        This method succeeds immediately to keep the lifecycle consistent.

        Args:
            context: Pipeline state (unused).

        Returns:
            Dict with success=True.
        """
        logger.debug("[JenkinsIntegration] create() - no-op (Jenkins has no issue concept)")
        if not self.is_enabled:
            return {"success": False, "reason": "Jenkins integration not enabled"}

        self._state = IntegrationState.CREATED
        return {"success": True, "reason": "Jenkins has no issue creation step"}

    def on_branch(self, branch_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 9: No-op - Jenkins discovers branches via SCM polling/webhooks.

        Args:
            branch_name: Branch name (stored for later use in build triggers).
            context:     Pipeline state.

        Returns:
            Dict with success=True and branch_name.
        """
        logger.debug(
            "[JenkinsIntegration] on_branch() - no-op for branch %s",
            branch_name,
        )
        if not self.is_enabled:
            return {"success": False, "reason": "Jenkins integration not enabled"}

        # Store branch for use in update() build trigger.
        self._config["_branch_name"] = branch_name
        return {
            "success": True,
            "branch_name": branch_name,
            "reason": "Jenkins discovers branches automatically",
        }

    def update(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 10: Trigger a Jenkins build on the implementation branch.

        Triggers the configured job and waits for the build to complete.
        The build is triggered with the branch name as a parameter when
        the job supports parameterized builds.

        Args:
            context: Pipeline state.  Uses:
                - 'jenkins_job_name' (str): Job to trigger (overrides default).
                - 'branch_name' (str): Branch to build.

        Returns:
            Dict with success (bool), build_number (int), result (str).
        """
        job_name = context.get(
            "jenkins_job_name",
            self._job_name or "",
        )
        branch_name = context.get(
            "branch_name",
            self._config.get("_branch_name", ""),
        )
        logger.info(
            "[JenkinsIntegration] update() - Step 10: trigger build for " "job=%s branch=%s",
            job_name,
            branch_name,
        )

        if not self.is_enabled:
            return {"success": False, "reason": "Jenkins integration not enabled"}

        if not job_name:
            return {"success": False, "reason": "No Jenkins job name configured"}

        if not self._get_base_url():
            return {"success": False, "reason": "JENKINS_URL not configured"}

        try:
            next_build = self._get_next_build_number(job_name)
            job_path = self._encode_job_path(job_name)

            # Attempt parameterized build first; fall back to plain trigger.
            params: Optional[Dict[str, str]] = None
            if branch_name:
                params = {"BRANCH": branch_name}

            build_path = "{}/buildWithParameters".format(job_path)
            triggered = self._api_post(build_path, params=params)

            if not triggered and params:
                # Job may not be parameterized; try plain build.
                build_path = "{}/build".format(job_path)
                triggered = self._api_post(build_path)

            if not triggered:
                self._state = IntegrationState.ERROR
                return {
                    "success": False,
                    "reason": "Failed to trigger Jenkins build for {}".format(job_name),
                }

            # Wait briefly for Jenkins to assign the build number.
            time.sleep(2)
            build_number = next_build or self._get_next_build_number(job_name)
            if build_number and next_build and build_number > next_build:
                build_number = next_build  # Use the pre-trigger number.

            self._last_build_number = build_number
            self._artifact_id = str(build_number)

            # Poll until complete.
            wait_result = _NOOP_WAIT_RESULT
            if build_number:
                wait_result = self._wait_for_build(job_name, build_number)

            build_result = wait_result.get("result", "UNKNOWN")
            success = build_result == "SUCCESS"

            if success:
                self._state = IntegrationState.IN_PROGRESS
            else:
                self._state = IntegrationState.ERROR

            return {
                "success": success,
                "build_number": build_number,
                "result": build_result,
                "job_name": job_name,
                "timed_out": wait_result.get("timed_out", False),
            }

        except Exception as exc:
            logger.error("[JenkinsIntegration] update() failed: %s", exc)
            self._state = IntegrationState.ERROR
            return {"success": False, "reason": str(exc)}

    def on_review(self, pr_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 11: Validate the build status before PR merge.

        Fetches the result of the most recent build triggered in update().
        A fresh build may be triggered when no prior build number is cached
        and the context supplies a build number.

        Args:
            pr_data: Dict with pr_url (str), pr_number (int).
            context: Pipeline state.  Uses:
                - 'jenkins_job_name' (str): Job name.
                - 'jenkins_build_number' (int): Specific build to check.

        Returns:
            Dict with success (bool), build_number (int), result (str),
            passed (bool).
        """
        job_name = context.get("jenkins_job_name", self._job_name or "")
        build_number = int(
            context.get(
                "jenkins_build_number",
                self._last_build_number or 0,
            )
        )
        logger.info(
            "[JenkinsIntegration] on_review() - Step 11: validate build " "job=%s build=%d",
            job_name,
            build_number,
        )

        if not self.is_enabled:
            return {"success": False, "reason": "Jenkins integration not enabled"}

        if not job_name:
            return {"success": False, "reason": "No Jenkins job name configured"}

        if not self._get_base_url():
            return {"success": False, "reason": "JENKINS_URL not configured"}

        try:
            if build_number:
                result = self._get_build_result(job_name, build_number)
                if result is None:
                    # Still building; wait for completion.
                    wait_result = self._wait_for_build(job_name, build_number)
                    result = wait_result.get("result", "UNKNOWN")
            else:
                # No cached build; fetch the last completed build result.
                job_path = self._encode_job_path(job_name)
                data = self._api_get("{}/lastBuild/api/json?tree=number,result,building".format(job_path))
                if data is None:
                    return {
                        "success": False,
                        "reason": "Could not fetch last build from Jenkins",
                    }
                if data.get("building"):
                    build_number = int(data.get("number", 0))
                    wait_result = self._wait_for_build(job_name, build_number)
                    result = wait_result.get("result", "UNKNOWN")
                else:
                    result = data.get("result", "UNKNOWN")
                    build_number = int(data.get("number", 0))

            passed = result == "SUCCESS"
            if passed:
                self._state = IntegrationState.IN_REVIEW
            else:
                self._state = IntegrationState.ERROR

            return {
                "success": passed,
                "build_number": build_number,
                "result": result,
                "job_name": job_name,
                "passed": passed,
            }

        except Exception as exc:
            logger.error("[JenkinsIntegration] on_review() failed: %s", exc)
            self._state = IntegrationState.ERROR
            return {"success": False, "reason": str(exc)}

    def close(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Step 12: Trigger post-merge build on the default branch.

        After the PR is merged the pipeline calls close() to kick off a final
        build confirming the merge is green on the main branch.

        Args:
            context: Pipeline state.  Uses:
                - 'jenkins_job_name' (str): Job to trigger.
                - 'default_branch' (str): Branch to build (default 'main').
                - 'pr_number' (int): Merged PR number (informational).

        Returns:
            Dict with success (bool), build_number (int), result (str).
        """
        job_name = context.get("jenkins_job_name", self._job_name or "")
        default_branch = context.get("default_branch", "main")
        pr_number = context.get("pr_number", 0)
        logger.info(
            "[JenkinsIntegration] close() - Step 12: post-merge build " "job=%s branch=%s pr=%s",
            job_name,
            default_branch,
            pr_number,
        )

        if not self.is_enabled:
            return {"success": False, "reason": "Jenkins integration not enabled"}

        if not job_name:
            return {"success": False, "reason": "No Jenkins job name configured"}

        if not self._get_base_url():
            return {"success": False, "reason": "JENKINS_URL not configured"}

        try:
            next_build = self._get_next_build_number(job_name)
            job_path = self._encode_job_path(job_name)

            params = {"BRANCH": default_branch} if default_branch else None
            build_path = "{}/buildWithParameters".format(job_path)
            triggered = self._api_post(build_path, params=params)

            if not triggered:
                build_path = "{}/build".format(job_path)
                triggered = self._api_post(build_path)

            if not triggered:
                self._state = IntegrationState.ERROR
                return {
                    "success": False,
                    "reason": "Failed to trigger post-merge build for {}".format(job_name),
                }

            time.sleep(2)
            build_number = next_build or 0
            self._last_build_number = build_number
            self._artifact_id = str(build_number)

            wait_result = _NOOP_WAIT_RESULT
            if build_number:
                wait_result = self._wait_for_build(job_name, build_number)

            build_result = wait_result.get("result", "UNKNOWN")
            success = build_result == "SUCCESS"

            if success:
                self._state = IntegrationState.DONE
            else:
                self._state = IntegrationState.ERROR

            return {
                "success": success,
                "build_number": build_number,
                "result": build_result,
                "job_name": job_name,
                "timed_out": wait_result.get("timed_out", False),
                "pr_number": pr_number,
            }

        except Exception as exc:
            logger.error("[JenkinsIntegration] close() failed: %s", exc)
            self._state = IntegrationState.ERROR
            return {"success": False, "reason": str(exc)}


# Sentinel used when no build was triggered (no build number to poll).
_NOOP_WAIT_RESULT: Dict[str, Any] = {
    "result": "UNKNOWN",
    "build_number": 0,
    "timed_out": False,
}
