"""Integration tests for the full GitHub PR lifecycle.

Tests the issue -> branch -> PR -> merge -> close sequence offline.
Each step's output feeds into the next to verify end-to-end contract
compliance with zero live network calls.

Run with:
    pytest tests/integration/test_github_pr_workflow.py -m integration -v
"""

import pytest
import requests

pytestmark = pytest.mark.integration

BASE_URL = "https://api.github.com"
OWNER = "test-owner"
REPO = "test-repo"


class TestGitHubPRLifecycle:
    """End-to-end PR lifecycle: create_issue -> get_sha -> create_branch
    -> create_pr -> merge_pr -> close_issue.

    Each step asserts on the HTTP status code and one or more payload fields
    before passing state to the next step.  The final assertions confirm:
      - PR was merged (merged == True)
      - Issue was closed (state == 'closed')
    """

    def test_full_pr_lifecycle_issue_to_close(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Full lifecycle: create_issue -> get_sha -> create_branch ->
        create_pr -> merge_pr -> close_issue.

        Asserts the final state is: PR merged=True, issue state=closed.
        """
        # ------------------------------------------------------------------ #
        # Step 1: Create issue
        # ------------------------------------------------------------------ #
        issue_resp = requests.post(
            "{}/repos/{}/{}/issues".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={
                "title": "v1.19.0 test issue",
                "body": "Integration test issue",
                "labels": ["ci"],
            },
        )
        assert issue_resp.status_code == 201, "Step 1 (create issue) failed: HTTP {}".format(issue_resp.status_code)
        issue_number = issue_resp.json()["number"]
        assert issue_number == 1, "Expected issue number 1; got {}".format(issue_number)
        assert issue_resp.json()["state"] == "open"

        # ------------------------------------------------------------------ #
        # Step 2: Get SHA for branch creation
        # ------------------------------------------------------------------ #
        sha_resp = requests.get(
            "{}/repos/{}/{}/git/refs/heads/main".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
        )
        assert sha_resp.status_code == 200, "Step 2 (get SHA) failed: HTTP {}".format(sha_resp.status_code)
        sha = sha_resp.json()["object"]["sha"]
        assert len(sha) > 0, "Base SHA must not be empty"
        assert sha == mock_github_repo["base_sha"], "SHA mismatch: expected '{}'; got '{}'".format(
            mock_github_repo["base_sha"], sha
        )

        # ------------------------------------------------------------------ #
        # Step 3: Create feature branch from SHA
        # ------------------------------------------------------------------ #
        branch_name = "feature/issue-{}".format(issue_number)
        branch_resp = requests.post(
            "{}/repos/{}/{}/git/refs".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"ref": "refs/heads/{}".format(branch_name), "sha": sha},
        )
        assert branch_resp.status_code == 201, "Step 3 (create branch) failed: HTTP {}".format(branch_resp.status_code)
        created_ref = branch_resp.json().get("ref", "")
        assert len(created_ref) > 0, "Branch ref must not be empty"

        # ------------------------------------------------------------------ #
        # Step 4: Create pull request
        # ------------------------------------------------------------------ #
        pr_resp = requests.post(
            "{}/repos/{}/{}/pulls".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={
                "title": "Fix #{}".format(issue_number),
                "body": "Closes #{}".format(issue_number),
                "head": branch_name,
                "base": mock_github_repo["default_branch"],
            },
        )
        assert pr_resp.status_code == 201, "Step 4 (create PR) failed: HTTP {}".format(pr_resp.status_code)
        pr_number = pr_resp.json()["number"]
        assert pr_number > 0, "PR number must be a positive integer"
        assert pr_resp.json()["state"] == "open"

        # ------------------------------------------------------------------ #
        # Step 5: Merge pull request
        # ------------------------------------------------------------------ #
        merge_resp = requests.put(
            "{}/repos/{}/{}/pulls/{}/merge".format(BASE_URL, OWNER, REPO, pr_number),
            headers=github_api_headers,
            json={"merge_method": "squash"},
        )
        assert merge_resp.status_code == 200, "Step 5 (merge PR) failed: HTTP {}".format(merge_resp.status_code)
        assert merge_resp.json()["merged"] is True, "Expected merged=True; got {}".format(
            merge_resp.json().get("merged")
        )
        merge_sha = merge_resp.json().get("sha", "")
        assert len(merge_sha) > 0, "Merge SHA must not be empty"

        # ------------------------------------------------------------------ #
        # Step 6: Close the issue
        # ------------------------------------------------------------------ #
        close_resp = requests.patch(
            "{}/repos/{}/{}/issues/{}".format(BASE_URL, OWNER, REPO, issue_number),
            headers=github_api_headers,
            json={"state": "closed"},
        )
        assert close_resp.status_code == 200, "Step 6 (close issue) failed: HTTP {}".format(close_resp.status_code)
        assert close_resp.json()["state"] == "closed", "Expected issue state 'closed'; got '{}'".format(
            close_resp.json().get("state")
        )

    def test_pr_lifecycle_label_check(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Verify labels endpoint works as part of the PR preparation workflow.

        Labels are fetched before issue creation to validate that the intended
        labels (e.g. 'ci') exist in the repository.
        """
        labels_resp = requests.get(
            "{}/repos/{}/{}/labels".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
        )
        assert labels_resp.status_code == 200, "Labels fetch failed: HTTP {}".format(labels_resp.status_code)
        labels = labels_resp.json()
        assert isinstance(labels, list), "Labels response must be a list; got {}".format(type(labels).__name__)
        assert len(labels) > 0, "Labels list must contain at least one item"
        assert all("name" in lbl for lbl in labels), "Every label must have a 'name' key"

        # Verify the 'ci' label is present (used by the lifecycle test)
        label_names = {lbl["name"] for lbl in labels}
        assert "ci" in label_names, "'ci' label not found in repo labels: {}".format(label_names)

    def test_pr_lifecycle_sequential_sha_to_branch(self, mock_github_responses, mock_github_repo, github_api_headers):
        """Verify SHA retrieved in step 2 is directly usable in branch creation step 3."""
        # Get SHA
        sha_resp = requests.get(
            "{}/repos/{}/{}/git/refs/heads/main".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
        )
        assert sha_resp.status_code == 200
        sha = sha_resp.json()["object"]["sha"]

        # Use the SHA immediately to create a branch
        branch_resp = requests.post(
            "{}/repos/{}/{}/git/refs".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"ref": "refs/heads/feature/sha-test", "sha": sha},
        )
        assert branch_resp.status_code == 201, "Branch creation with SHA '{}' failed: HTTP {}".format(
            sha, branch_resp.status_code
        )
        # Branch object SHA must match the base SHA
        branch_sha = branch_resp.json()["object"]["sha"]
        assert branch_sha == sha, "Branch SHA '{}' does not match requested base SHA '{}'".format(branch_sha, sha)

    def test_pr_lifecycle_create_pr_then_verify_merge_fields(
        self, mock_github_responses, mock_github_repo, github_api_headers
    ):
        """Verify that create-PR then merge-PR produces the expected merged response fields."""
        # Create PR
        pr_resp = requests.post(
            "{}/repos/{}/{}/pulls".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={
                "title": "Merge fields test",
                "body": "",
                "head": "feature/test-1",
                "base": "main",
            },
        )
        assert pr_resp.status_code == 201
        pr_number = pr_resp.json()["number"]

        # Merge PR
        merge_resp = requests.put(
            "{}/repos/{}/{}/pulls/{}/merge".format(BASE_URL, OWNER, REPO, pr_number),
            headers=github_api_headers,
            json={"merge_method": "squash"},
        )
        assert merge_resp.status_code == 200
        merge_body = merge_resp.json()

        # Verify all required merge response fields
        assert "sha" in merge_body, "Merge response missing 'sha' field"
        assert "merged" in merge_body, "Merge response missing 'merged' field"
        assert "message" in merge_body, "Merge response missing 'message' field"
        assert merge_body["merged"] is True
        assert len(merge_body["sha"]) > 0
        assert len(merge_body["message"]) > 0

    def test_pr_lifecycle_close_issue_idempotent_call(
        self, mock_github_responses, mock_github_repo, github_api_headers
    ):
        """Verify that closing the issue returns the expected closed state.

        This test isolates the close step to confirm that PATCH /issues/1
        with state=closed always returns state == 'closed' regardless of
        prior steps in the same test session.
        """
        close_resp = requests.patch(
            "{}/repos/{}/{}/issues/1".format(BASE_URL, OWNER, REPO),
            headers=github_api_headers,
            json={"state": "closed"},
        )
        assert close_resp.status_code == 200
        body = close_resp.json()
        assert "number" in body, "Close-issue response missing 'number'"
        assert "state" in body, "Close-issue response missing 'state'"
        assert body["state"] == "closed"
