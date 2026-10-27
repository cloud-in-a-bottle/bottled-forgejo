import subprocess
import time

import requests
from openhost_test_harness import OpenhostStack

HTML = {"Accept": "text/html"}


def _logs(stack: OpenhostStack) -> str:
    return f"\n\napp logs:\n{stack.app_logs()[-5000:]}"


def _wait_for_forgejo(stack: OpenhostStack) -> None:
    deadline = time.monotonic() + 60
    while True:
        try:
            response = requests.get(f"{stack.url}/api/v1/version", timeout=30)
            if response.status_code == 200 or time.monotonic() > deadline:
                break
        except requests.ConnectionError:
            if time.monotonic() > deadline:
                raise
        time.sleep(2)
    assert response.status_code == 200, f"/api/v1/version: {response.status_code}: {response.text[:300]}{_logs(stack)}"


def test_owner_is_signed_in_as_admin(stack: OpenhostStack) -> None:
    _wait_for_forgejo(stack)
    # A page that needs a signed-in user: anonymous visitors are redirected to /user/login.
    settings = stack.owner_session.get(f"{stack.url}/user/settings", headers=HTML, timeout=30)
    assert settings.status_code == 200 and "/user/login" not in settings.url, (
        f"owner wasn't signed in: {settings.status_code} {settings.url}{_logs(stack)}"
    )
    # The owner's own username, or the fallback when it's reserved/invalid in Forgejo.
    logins = [name for name in (stack.owner_username, "operator") if f'value="{name}"' in settings.text]
    assert logins, f"settings page isn't the owner's account: {settings.text[:2000]}"
    # Only a Forgejo admin can open the site administration pages.
    admin_pages = [
        stack.owner_session.get(f"{stack.url}{path}", headers=HTML, allow_redirects=False, timeout=30)
        for path in ("/admin", "/-/admin")
    ]
    assert any(page.status_code == 200 for page in admin_pages), (
        f"owner isn't a Forgejo admin: {[(page.url, page.status_code) for page in admin_pages]}"
    )


def test_anonymous_visitors_get_password_login_only(stack: OpenhostStack) -> None:
    _wait_for_forgejo(stack)
    # Everything is a public path, so invited users can reach Forgejo's own login form.
    login = requests.get(f"{stack.url}/user/login", headers=HTML, timeout=30)
    assert login.status_code == 200 and 'name="password"' in login.text, f"login page: {login.status_code}"
    assert requests.get(f"{stack.url}/api/v1/user", timeout=30).status_code == 401
    settings = requests.get(f"{stack.url}/user/settings", headers=HTML, allow_redirects=False, timeout=30)
    assert settings.status_code in (302, 303) and "/user/login" in settings.headers["Location"], settings.status_code
    # Walk-in registration is off.
    sign_up = requests.get(f"{stack.url}/user/sign_up", headers=HTML, timeout=30)
    assert sign_up.status_code >= 400 or 'name="retype"' not in sign_up.text, "sign-up form is open to anyone"


def test_auth_proxy_ignores_a_forged_user_header(stack: OpenhostStack) -> None:
    _wait_for_forgejo(stack)
    # Straight to the container, past the router: only the router's owner header may sign someone in, never a
    # client-supplied X-Openhost-User.
    forged = requests.get(
        f"{stack.app_url}/user/settings",
        headers={**HTML, "X-Openhost-User": stack.owner_username},
        allow_redirects=False,
        timeout=30,
    )
    assert forged.status_code in (302, 303) and "/user/login" in forged.headers.get("Location", ""), (
        f"forged X-Openhost-User signed someone in: {forged.status_code}: {forged.text[:300]}"
    )


def test_data_is_stored_under_app_data(stack: OpenhostStack) -> None:
    _wait_for_forgejo(stack)
    databases = list((stack.data_dir / "gitea").glob("*.db"))
    assert databases, f"no Forgejo database under {stack.data_dir / 'gitea'}: {list(stack.data_dir.rglob('*'))[:50]}"


def test_forgejo_credentials_in_authorization_reach_forgejo(stack: OpenhostStack) -> None:
    _wait_for_forgejo(stack)
    # An invited user, created by the admin as the readme describes.
    user, password = "invitee", "invitee-password-1234"
    create_user = ["forgejo", "admin", "user", "create", "--username", user, "--password", password]
    create_user += ["--email", f"{user}@example.com", "--must-change-password=false"]
    created = subprocess.run(
        ["podman", "exec", "-u", "git", stack.container_name, *create_user], capture_output=True, text=True, timeout=60
    )
    assert created.returncode == 0, f"creating {user}: {created.stdout} {created.stderr}"

    # No router session: these reach Forgejo on the public path with only Forgejo's own credentials in Authorization.
    basic = requests.get(f"{stack.url}/api/v1/user", auth=(user, password), timeout=30)
    assert basic.status_code == 200 and basic.json()["login"] == user, (
        f"basic auth: {basic.status_code}: {basic.text[:300]}"
    )
    created_token = requests.post(
        f"{stack.url}/api/v1/users/{user}/tokens",
        auth=(user, password),
        json={"name": "git", "scopes": ["write:repository", "read:user"]},
        timeout=30,
    )
    assert created_token.status_code == 201, (
        f"creating a token: {created_token.status_code}: {created_token.text[:300]}"
    )
    token = created_token.json()["sha1"]
    me = requests.get(f"{stack.url}/api/v1/user", headers={"Authorization": f"token {token}"}, timeout=30)
    assert me.status_code == 200 and me.json()["login"] == user, f"token auth: {me.status_code}: {me.text[:300]}"

    # Git over HTTPS with the token as the password: a private repo's push endpoint lets the user in, not anonymous.
    repo = requests.post(
        f"{stack.url}/api/v1/user/repos", auth=(user, password), json={"name": "notes", "private": True}, timeout=30
    )
    assert repo.status_code == 201, f"creating a repo: {repo.status_code}: {repo.text[:300]}"
    refs = f"{stack.url}/{user}/notes.git/info/refs?service=git-receive-pack"
    assert requests.get(refs, timeout=30).status_code == 401
    push = requests.get(refs, auth=(user, token), timeout=30)
    assert push.status_code == 200 and push.headers["Content-Type"] == "application/x-git-receive-pack-advertisement", (
        f"git push over http: {push.status_code} {push.headers.get('Content-Type')}: {push.text[:300]}"
    )


def test_platform_owner_token_does_not_reach_forgejo(stack: OpenhostStack) -> None:
    _wait_for_forgejo(stack)
    minted = stack.owner_session.post(f"{stack.router_url}/api/tokens", json={"name": "forgejo-test"}, timeout=30)
    assert minted.status_code == 200, f"minting an owner token: {minted.status_code}: {minted.text[:300]}"
    owner_token = minted.json()["token"]
    # The router takes its own token from either header and drops it before proxying. Forgejo rejects every API
    # call, even public ones, that carries a bearer token it doesn't know ("access token does not exist", echoing
    # the token), so this only passes if the platform token never reached Forgejo.
    for header in ("Authorization", "X-OpenHost-Authorization"):
        version = requests.get(f"{stack.url}/api/v1/version", headers={header: f"Bearer {owner_token}"}, timeout=30)
        assert version.status_code == 200, f"owner token in {header}: {version.status_code}: {version.text[:300]}"
