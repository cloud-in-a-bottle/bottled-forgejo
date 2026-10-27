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
    # The web visit left a Forgejo session cookie, which the API also accepts.
    user = stack.owner_session.get(f"{stack.url}/api/v1/user", timeout=30)
    assert user.status_code == 200, f"/api/v1/user: {user.status_code}: {user.text[:300]}"
    # The owner's own username, or the fallback when it's reserved/invalid in Forgejo.
    assert user.json()["login"] in (stack.owner_username, "operator"), user.text
    assert user.json()["is_admin"] is True, f"owner isn't a Forgejo admin: {user.text}"


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
