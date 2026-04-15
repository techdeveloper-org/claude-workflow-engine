"""Integration tests for GitHub REST API endpoint mocking.

All tests are offline -- no live network calls are made.
The `responses` library intercepts every outbound HTTP request and returns
the payloads registered in conftest.mock_github_responses.

Run with:
    pytest tests/integration/test_github_integration.py -m integration -v
"""

import pytest
import requests

pytestmark = pytest.mark.integration

BASE_URL = "https://api.github.com"
OWNER = "test-owner"
REPO = "test-repo"


# ---------------------------------------------------------------------------
# Issue Operations
# ---------------------------------------------------------------------------


class TestGitHubIssueOperations:
    """Verify create-issue and close-issue endpoint contracts."""

    def test_create_issue_returns_201(self, mock_github_responses, mock_github_repo, github_api_headers):
        """POST to create an issue must return HTTP 201."""
        resp = requests.post(
            "{}/repos/{}/{}/issues".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"title": "Test issue", "body": "Body text", "labels": ["ci"]},
        )
        assert resp.status_code == 201, "Expected 201 Created; got {}".format(resp.status_code)

    def test_create_issue_response_has_required_fields(
        self, mock_github_responses, mock_github_repo, github_api_headers
    ):
        """Create-issue response body must include id, number, state, and html_url."""
        resp = requests.post(
            "{}/repos/{}/{}/issues".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"title": "Test issue", "body": "Body text"},
        )
        assert resp.status_code == 201
        body = resp.json()
        required_fields = {"id", "number", "state", "html_url"}
        missing = required_fields - set(body.keys())
        assert not missing, "Create-issue response is missing fields: {}".format(missing)

    def test_create_issue_number_is_positive_integer(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Issue number must be a positive integer (boundary: > 0)."""
        resp = requests.post(
            "{}/repos/{}/{}/issues".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"title": "Boundary test"},
        )
        assert resp.status_code == 201
        number = resp.json()["number"]
        assert isinstance(number, int) and number > 0, "Issue number must be a positive int; got {}".format(number)

    def test_create_issue_state_is_open(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Newly created issue state must be 'open'."""
        resp = requests.post(
            "{}/repos/{}/{}/issues".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"title": "State check"},
        )
        assert resp.status_code == 201
        assert resp.json()["state"] == "open"

    def test_close_issue_returns_200(self, mock_github_responses, mock_github_repo, github_api_headers):
        """PATCH issue/1 with state=closed must return HTTP 200."""
        resp = requests.patch(
            "{}/repos/{}/{}/issues/1".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"state": "closed"},
        )
        assert resp.status_code == 200, "Expected 200 OK on close; got {}".format(resp.status_code)

    def test_close_issue_response_state_is_closed(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Close-issue response body must have state == 'closed'."""
        resp = requests.patch(
            "{}/repos/{}/{}/issues/1".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"state": "closed"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "closed", "Expected state 'closed'; got '{}'".format(resp.json().get("state"))

    def test_close_issue_html_url_contains_repo(self, mock_github_responses, mock_github_repo, github_api_headers):
        """html_url on created issue must reference the correct repo."""
        resp = requests.post(
            "{}/repos/{}/{}/issues".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"title": "URL check"},
        )
        assert resp.status_code == 201
        html_url = resp.json().get("html_url", "")
        assert OWNER in html_url, "html_url does not contain owner '{}'".format(OWNER)
        assert REPO in html_url, "html_url does not contain repo '{}'".format(REPO)


# ---------------------------------------------------------------------------
# Branch Operations
# ---------------------------------------------------------------------------


class TestGitHubBranchOperations:
    """Verify get-SHA and create-branch endpoint contracts."""

    def test_get_main_branch_sha_returns_200(self, mock_github_responses, mock_github_repo, github_api_headers):
        """GET git/refs/heads/main must return HTTP 200."""
        resp = requests.get(
            "{}/repos/{}/{}/git/refs/heads/main".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
        )
        assert resp.status_code == 200, "Expected 200 for main branch SHA; got {}".format(resp.status_code)

    def test_get_main_branch_sha_value_is_present(self, mock_github_responses, mock_github_repo, github_api_headers):
        """SHA from the main branch ref must be a non-empty string."""
        resp = requests.get(
            "{}/repos/{}/{}/git/refs/heads/main".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
        )
        assert resp.status_code == 200
        sha = resp.json()["object"]["sha"]
        assert isinstance(sha, str) and len(sha) > 0, "SHA must be a non-empty string; got '{}'".format(sha)

    def test_get_main_branch_sha_matches_fixture(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Returned SHA must match the fixture base_sha value."""
        resp = requests.get(
            "{}/repos/{}/{}/git/refs/heads/main".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
        )
        assert resp.status_code == 200
        sha = resp.json()["object"]["sha"]
        assert sha == mock_github_repo["base_sha"], "SHA mismatch: expected '{}'; got '{}'".format(
            mock_github_repo["base_sha"], sha
        )

    def test_get_main_branch_ref_field_format(self, mock_github_responses, mock_github_repo, github_api_headers):
        """The ref field must begin with 'refs/heads/'."""
        resp = requests.get(
            "{}/repos/{}/{}/git/refs/heads/main".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
        )
        assert resp.status_code == 200
        ref = resp.json()["ref"]
        assert ref.startswith("refs/heads/"), "ref must start with 'refs/heads/'; got '{}'".format(ref)

    def test_create_feature_branch_returns_201(self, mock_github_responses, mock_github_repo, github_api_headers):
        """POST git/refs to create a feature branch must return HTTP 201."""
        sha = mock_github_repo["base_sha"]
        resp = requests.post(
            "{}/repos/{}/{}/git/refs".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"ref": "refs/heads/feature/test-1", "sha": sha},
        )
        assert resp.status_code == 201, "Expected 201 Created for branch; got {}".format(resp.status_code)

    def test_create_feature_branch_ref_field_present(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Create-branch response must contain a non-empty ref field."""
        sha = mock_github_repo["base_sha"]
        resp = requests.post(
            "{}/repos/{}/{}/git/refs".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"ref": "refs/heads/feature/test-1", "sha": sha},
        )
        assert resp.status_code == 201
        ref = resp.json().get("ref", "")
        assert len(ref) > 0, "Create-branch ref field must not be empty"


# ---------------------------------------------------------------------------
# Pull Request Operations
# ---------------------------------------------------------------------------


class TestGitHubPROperations:
    """Verify create-PR and merge-PR endpoint contracts."""

    def test_create_pr_returns_201(self, mock_github_responses, mock_github_repo, github_api_headers):
        """POST pulls must return HTTP 201."""
        resp = requests.post(
            "{}/repos/{}/{}/pulls".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={
                "title": "Test PR",
                "body": "Closes #1",
                "head": "feature/test-1",
                "base": "main",
            },
        )
        assert resp.status_code == 201, "Expected 201 Created for PR; got {}".format(resp.status_code)

    def test_create_pr_response_has_number(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Create-PR response must contain a positive integer number."""
        resp = requests.post(
            "{}/repos/{}/{}/pulls".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"title": "Test PR", "body": "", "head": "feature/test-1", "base": "main"},
        )
        assert resp.status_code == 201
        number = resp.json().get("number")
        assert isinstance(number, int) and number > 0

    def test_create_pr_state_is_open(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Newly created PR state must be 'open'."""
        resp = requests.post(
            "{}/repos/{}/{}/pulls".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"title": "State test", "body": "", "head": "feature/test-1", "base": "main"},
        )
        assert resp.status_code == 201
        assert resp.json()["state"] == "open"

    def test_create_pr_html_url_present(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Create-PR response must include a non-empty html_url."""
        resp = requests.post(
            "{}/repos/{}/{}/pulls".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"title": "URL test", "body": "", "head": "feature/test-1", "base": "main"},
        )
        assert resp.status_code == 201
        html_url = resp.json().get("html_url", "")
        assert len(html_url) > 0

    def test_merge_pr_returns_200(self, mock_github_responses, mock_github_repo, github_api_headers):
        """PUT pulls/1/merge must return HTTP 200."""
        resp = requests.put(
            "{}/repos/{}/{}/pulls/1/merge".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"merge_method": "squash"},
        )
        assert resp.status_code == 200, "Expected 200 OK for merge; got {}".format(resp.status_code)

    def test_merge_pr_returns_merged_true(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Merge response body must have merged == True."""
        resp = requests.put(
            "{}/repos/{}/{}/pulls/1/merge".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"merge_method": "squash"},
        )
        assert resp.status_code == 200
        assert resp.json()["merged"] is True, "merged field must be True; got {}".format(resp.json().get("merged"))

    def test_merge_pr_response_has_sha(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Merge response must contain a non-empty sha field."""
        resp = requests.put(
            "{}/repos/{}/{}/pulls/1/merge".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"merge_method": "squash"},
        )
        assert resp.status_code == 200
        sha = resp.json().get("sha", "")
        assert isinstance(sha, str) and len(sha) > 0, "Merge sha must be a non-empty string; got '{}'".format(sha)

    def test_merge_pr_response_message_present(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Merge response must contain a non-empty message field."""
        resp = requests.put(
            "{}/repos/{}/{}/pulls/1/merge".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"merge_method": "squash"},
        )
        assert resp.status_code == 200
        message = resp.json().get("message", "")
        assert len(message) > 0, "Merge message must not be empty"


# ---------------------------------------------------------------------------
# Label Operations
# ---------------------------------------------------------------------------


class TestGitHubLabelOperations:
    """Verify labels endpoint contracts."""

    def test_list_labels_returns_200(self, mock_github_responses, mock_github_repo, github_api_headers):
        """GET labels must return HTTP 200."""
        resp = requests.get(
            "{}/repos/{}/{}/labels".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
        )
        assert resp.status_code == 200, "Expected 200 for labels; got {}".format(resp.status_code)

    def test_list_labels_returns_list(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Labels response body must be a JSON array."""
        resp = requests.get(
            "{}/repos/{}/{}/labels".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list), "Labels response must be a list; got {}".format(type(body).__name__)

    def test_list_labels_at_least_one_item(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Labels list must contain at least one label (boundary: len >= 1)."""
        resp = requests.get(
            "{}/repos/{}/{}/labels".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
        )
        assert resp.status_code == 200
        labels = resp.json()
        assert len(labels) >= 1, "Expected at least 1 label; got 0"

    def test_list_labels_has_name_and_color(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Every label in the list must have both name and color keys."""
        resp = requests.get(
            "{}/repos/{}/{}/labels".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
        )
        assert resp.status_code == 200
        for idx, label in enumerate(resp.json()):
            assert "name" in label, "Label[{}] missing 'name' key".format(idx)
            assert "color" in label, "Label[{}] missing 'color' key".format(idx)

    def test_list_labels_names_match_fixture(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Returned label names must match the fixture label list."""
        resp = requests.get(
            "{}/repos/{}/{}/labels".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
        )
        assert resp.status_code == 200
        returned_names = {lbl["name"] for lbl in resp.json()}
        expected_names = set(mock_github_repo["labels"])
        assert returned_names == expected_names, "Label names mismatch. Expected: {}; Got: {}".format(
            expected_names, returned_names
        )

    def test_list_labels_color_is_hex_string(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Every label color must be a 6-character hex string (boundary: len == 6)."""
        resp = requests.get(
            "{}/repos/{}/{}/labels".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
        )
        assert resp.status_code == 200
        for label in resp.json():
            color = label["color"]
            assert (
                isinstance(color, str) and len(color) == 6
            ), "Label '{}' has invalid color '{}'; expected 6-char hex".format(label["name"], color)
