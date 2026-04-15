"""Shared pytest fixtures for GitHub integration tests.

All fixtures are offline -- zero live network calls are made.
HTTP interception is provided by the `responses` library (ADR-002).

Run the integration suite with:
    pytest tests/integration/ -m integration
"""

import pytest
import responses as responses_lib

# ---------------------------------------------------------------------------
# Module-scoped static fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mock_github_repo():
    """Return a dict describing the test repository metadata."""
    return {
        "owner": "test-owner",
        "repo": "test-repo",
        "default_branch": "main",
        "labels": ["bug", "enhancement", "ci"],
        "base_sha": "abc123def456789abc123def456789abc123def4",
    }


@pytest.fixture(scope="module")
def mock_github_token():
    """Return a synthetic (non-functional) GitHub token string."""
    return "ghp_mock_token_for_testing_only"


@pytest.fixture(scope="module")
def github_api_headers():
    """Return HTTP headers required for GitHub REST API calls."""
    return {
        "Authorization": "token ghp_mock_token_for_testing_only",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Function-scoped HTTP mock fixture
# ---------------------------------------------------------------------------

_OWNER = "test-owner"
_REPO = "test-repo"
_BASE = "https://api.github.com"
_BASE_SHA = "abc123def456789abc123def456789abc123def4"


@pytest.fixture
def mock_github_responses():
    """Activate the `responses` HTTP interceptor and register 6 GitHub endpoints.

    The fixture is function-scoped so each test starts with a clean interceptor
    state.  All registered endpoints accept unlimited calls
    (match_querystring=False, allowing extra query params).

    Endpoints registered:
      1. POST  /repos/{owner}/{repo}/issues          -> 201
      2. GET   /repos/{owner}/{repo}/git/refs/heads/main -> 200
      3. POST  /repos/{owner}/{repo}/git/refs        -> 201
      4. POST  /repos/{owner}/{repo}/pulls           -> 201
      5. PUT   /repos/{owner}/{repo}/pulls/1/merge   -> 200
      6. PATCH /repos/{owner}/{repo}/issues/1        -> 200
      7. GET   /repos/{owner}/{repo}/labels          -> 200
    """
    with responses_lib.RequestsMock(assert_all_requests_are_fired=False) as rsps:

        # 1. Create issue
        rsps.add(
            method=responses_lib.POST,
            url="{}/repos/{}/{}/issues".format(_BASE, _OWNER, _REPO),
            json={
                "id": 1001,
                "number": 1,
                "title": "v1.19.0 test issue",
                "body": "Integration test issue body",
                "state": "open",
                "html_url": "https://github.com/{}/{}/issues/1".format(_OWNER, _REPO),
                "labels": [],
            },
            status=201,
        )

        # 2. Get main branch SHA
        rsps.add(
            method=responses_lib.GET,
            url="{}/repos/{}/{}/git/refs/heads/main".format(_BASE, _OWNER, _REPO),
            json={
                "ref": "refs/heads/main",
                "object": {
                    "sha": _BASE_SHA,
                    "type": "commit",
                },
            },
            status=200,
        )

        # 3. Create feature branch
        rsps.add(
            method=responses_lib.POST,
            url="{}/repos/{}/{}/git/refs".format(_BASE, _OWNER, _REPO),
            json={
                "ref": "refs/heads/feature/test-1",
                "object": {
                    "sha": _BASE_SHA,
                },
            },
            status=201,
        )

        # 4. Create pull request
        rsps.add(
            method=responses_lib.POST,
            url="{}/repos/{}/{}/pulls".format(_BASE, _OWNER, _REPO),
            json={
                "id": 2001,
                "number": 1,
                "title": "Fix #1",
                "state": "open",
                "html_url": "https://github.com/{}/{}/pull/1".format(_OWNER, _REPO),
                "head": {"ref": "feature/test-1"},
                "base": {"ref": "main"},
            },
            status=201,
        )

        # 5. Merge pull request
        rsps.add(
            method=responses_lib.PUT,
            url="{}/repos/{}/{}/pulls/1/merge".format(_BASE, _OWNER, _REPO),
            json={
                "sha": "def456abc789",
                "merged": True,
                "message": "Pull Request successfully merged",
            },
            status=200,
        )

        # 6. Close (update) issue
        rsps.add(
            method=responses_lib.PATCH,
            url="{}/repos/{}/{}/issues/1".format(_BASE, _OWNER, _REPO),
            json={
                "number": 1,
                "state": "closed",
                "title": "Test issue",
            },
            status=200,
        )

        # 7. List labels
        rsps.add(
            method=responses_lib.GET,
            url="{}/repos/{}/{}/labels".format(_BASE, _OWNER, _REPO),
            json=[
                {"name": "bug", "color": "d73a4a"},
                {"name": "enhancement", "color": "a2eeef"},
                {"name": "ci", "color": "0075ca"},
            ],
            status=200,
        )

        yield rsps
