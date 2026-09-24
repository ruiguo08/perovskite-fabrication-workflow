"""Phase 4D fresh-installed-wheel smoke test.

The Phase 4 cutover deletes the legacy Jinja templates and static JavaScript,
so the release wheel must be proven self-sufficient from outside the source
checkout. This test:

1. Installs the newest wheel from ``dist/`` into a throwaway venv created with
   ``python -m venv --system-site-packages``. The bridge to the host runtime
   (a ``*.pth`` inside the child venv's own site-packages pointing at the
   running interpreter's site-packages) supplies THIRD-PARTY runtime
   dependencies only (fastapi, sqlalchemy, uvicorn, ...); the application
   packages ``web`` and ``perovskite_bo`` must both come from the wheel and
   both resolve only under the child venv's own site-packages — never from
   ``src/``.
2. Runs a child subprocess from a working directory OUTSIDE the repository
   that imports ``web`` and ``perovskite_bo`` from the installed package and
   exercises real HTTP responses through FastAPI's TestClient:
   - ``/app/`` returns the React entry document and every referenced hashed
     asset serves 200 with immutable cache headers;
   - legacy GETs redirect (303) to their React equivalents;
   - ``/api/session`` is 401 unauthenticated and ``/healthz`` is 200;
   - removed legacy POST routes return 404/405;
   - no ``web/templates`` or ``web/static`` directories are installed;
   - a real experiment created through the JSON API exports valid JSON and
     PDF attachments (not redirects).

No network is used: the wheel installs with ``--no-deps`` and runtime
dependencies resolve from the system site-packages environment.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# The canonical recipe builder shares the same fixture the rest of the suite
# uses (tests/test_web_app.py), so the smoke exercises a server-accepted recipe.
sys.path.insert(0, str(REPO_ROOT / "tests"))
from test_web_app import (  # noqa: E402  (import order guarded below)
    complete_guided_setup,
)
from perovskite_bo import deposition_recipe_from_process  # noqa: E402

ADMIN_USERNAME = "wheel-smoke-admin"
ADMIN_PASSWORD = "Wheel smoke admin password 2026!"

# Child driver that performs the actual installed-package verification. It is
# written into the temporary directory (never into the repository) and executed
# with the child venv's interpreter.
CHILD_SCRIPT = r"""# Fresh-installed-wheel verification (runs entirely under the child venv).
import json
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(sys.argv[1]).resolve()
RECIPE_PATH = Path(sys.argv[2])

ADMIN_USERNAME = "wheel-smoke-admin"
ADMIN_PASSWORD = "Wheel smoke admin password 2026!"

# The host interpreter's venv may have reached this child through an editable
# project install (a *.pth that appends the repository's src/). Enforce the
# isolation contract before any import: the source tree must never resolve.
#
# The throwaway venv is created with --system-site-packages plus a ".pth"
# bridge (see setUpClass) that exposes the host interpreter's site-packages.
# That bridge supplies THIRD-PARTY runtime dependencies only (fastapi,
# sqlalchemy, uvicorn, ...). The application packages `web` and `perovskite_bo`
# must both come from the installed wheel, i.e. resolve only under the child
# venv's own <venv>\Lib\site-packages, never under REPO_ROOT/src.
def _is_under_repo(path: Path) -> bool:
    try:
        resolved = Path(path).resolve()
    except (OSError, RuntimeError):
        return False
    return resolved == REPO_ROOT / "src" or REPO_ROOT / "src" in resolved.parents

sys.path[:] = [entry for entry in sys.path if not _is_under_repo(entry)]

# --- Installed-package resolution assertions --------------------------------
import sysconfig  # noqa: E402
import web  # noqa: E402
import perovskite_bo  # noqa: E402

# venv layouts differ by platform (Windows: <venv>/Lib/site-packages, posix:
# <venv>/lib/python3.x/site-packages), so never hard-code one.
CHILD_SITE = Path(sysconfig.get_paths()["purelib"]).resolve()
for module in (web, perovskite_bo):
    installed_file = Path(module.__file__).resolve()
    assert CHILD_SITE in installed_file.parents, (
        f"{module.__name__} resolved outside the child venv site-packages: "
        f"{module.__file__}\nsys.path: {sys.path!r}"
    )
    assert not _is_under_repo(installed_file), (
        f"{module.__name__} resolved under the repository source tree: "
        f"{module.__file__}"
    )

WEB_FILE = Path(web.__file__).resolve()
for name in ("templates", "static"):
    assert not (WEB_FILE.parent / name).exists(), (
        f"installed package unexpectedly ships web/{name}/"
    )

# --- Isolated app + real HTTP responses -------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from web import create_app  # noqa: E402
from web.repository import UserRole  # noqa: E402

problems: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        problems.append(message)


with tempfile.TemporaryDirectory() as db_tmp:
    database_path = Path(db_tmp) / "wheel-smoke.sqlite3"
    app = create_app(
        database_path,
        secure_cookies=False,
        _test_user=(ADMIN_USERNAME, ADMIN_PASSWORD, UserRole.ADMINISTRATOR),
    )
    with TestClient(app, base_url="https://testserver") as client:
        # React entry document and immutable hashed assets.
        entry = client.get("/app/", follow_redirects=False)
        check(entry.status_code == 200, f"GET /app/ -> {entry.status_code}")
        asset_urls = re.findall(r'(?:src|href)="(/app/assets/[^"]+)"', entry.text)
        check(len(asset_urls) >= 2, f"expected hashed JS/CSS references, got {asset_urls!r}")
        for asset_url in asset_urls:
            asset = client.get(asset_url, follow_redirects=False)
            check(asset.status_code == 200, f"GET {asset_url} -> {asset.status_code}")
            expected = "public, max-age=31536000, immutable"
            check(
                asset.headers.get("cache-control") == expected,
                f"GET {asset_url} cache-control: {asset.headers.get('cache-control')!r}",
            )

        # Legacy GET URLs must 303 to their React equivalents, never HTML.
        legacies = {
            "/": "/app/",
            "/experiments": "/app/experiments",
        }
        for legacy, react in legacies.items():
            response = client.get(legacy, follow_redirects=False)
            check(response.status_code == 303, f"GET {legacy} -> {response.status_code}")
            check(
                response.headers.get("location") == react,
                f"GET {legacy} location: {response.headers.get('location')!r}",
            )
        login_redirect = client.get(
            "/login", params={"next": "/experiments/42"}, follow_redirects=False
        )
        check(login_redirect.status_code == 303, f"GET /login?next= -> {login_redirect.status_code}")
        check(
            login_redirect.headers.get("location", "").startswith("/app/login?next="),
            f"GET /login?next= location: {login_redirect.headers.get('location')!r}",
        )
        check(
            "next=%2Fexperiments%2F42" in login_redirect.headers.get("location", ""),
            f"safe next not preserved: {login_redirect.headers.get('location')!r}",
        )

        # Session + health contracts.
        check(client.get("/api/session", follow_redirects=False).status_code == 401,
              "GET /api/session unauthenticated != 401")
        check(client.get("/healthz", follow_redirects=False).status_code == 200,
              "GET /healthz != 200")

        # Removed legacy form-POST routes.
        for legacy_post in ("/login", "/experiments"):
            status_code = client.post(legacy_post, follow_redirects=False).status_code
            check(status_code in (404, 405),
                  f"POST {legacy_post} -> {status_code} (expected 404 or 405)")

        # Authenticated workflow: login through the JSON API, then create a
        # valid experiment and fetch both exports.
        csrf = client.get("/api/auth/login-csrf")
        assert csrf.status_code == 200, csrf.text
        login = client.post(
            "/api/auth/login",
            json={
                "username": ADMIN_USERNAME,
                "password": ADMIN_PASSWORD,
                "login_csrf": csrf.json()["login_csrf_token"],
            },
        )
        assert login.status_code == 200, login.text
        client.headers["X-CSRF-Token"] = client.cookies.get("perovskite_csrf")

        # The layout catalog is database-authoritative with no factory seed;
        # create the reference layout through the admin API before planning.
        import asyncio
        from decimal import Decimal

        from web.services.catalog_service import create_device_layout

        async def _seed_layout() -> None:
            async with app.state.database.engine.begin() as connection:
                await create_device_layout(
                    connection,
                    code="15x15_dual_005",
                    version=1,
                    substrate_width_mm=Decimal("15"),
                    substrate_length_mm=Decimal("15"),
                    devices_per_substrate=2,
                    device_active_area_cm2=Decimal("0.05"),
                    total_active_area_cm2=Decimal("0.10"),
                    description="15 × 15 mm substrate, 2 devices, 0.05 cm² each",
                )

        asyncio.run(_seed_layout())

        recipe = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
        created = client.post("/api/experiments", json={"recipe": recipe})
        assert created.status_code == 201, created.text
        experiment_id = created.json()["id"]

        for suffix, content_type in (("json", "application/json"), ("pdf", "application/pdf")):
            export = client.get(
                f"/experiments/{experiment_id}/export.{suffix}",
                follow_redirects=False,
            )
            check(export.status_code == 200,
                  f"GET export.{suffix} -> {export.status_code}")
            check("location" not in export.headers,
                  f"export.{suffix} must not redirect")
            check(
                export.headers.get("content-type", "").startswith(content_type),
                f"export.{suffix} content-type: {export.headers.get('content-type')!r}",
            )
            check(
                export.headers.get("content-disposition", "").startswith("attachment;"),
                f"export.{suffix} must be an attachment download",
            )
        pdf = client.get(f"/experiments/{experiment_id}/export.pdf")
        check(pdf.content.startswith(b"%PDF-"), "export.pdf is not a PDF document")

if problems:
    raise AssertionError("installed-wheel smoke failures:\n- " + "\n- ".join(problems))

print("installed-wheel smoke: OK")
print(f"web at: {web.__file__}")
print(f"child venv site-packages: {CHILD_SITE}")
print(f"assets verified: {asset_urls!r}")
"""


class InstalledWheelSmokeTests(unittest.TestCase):
    """Install the newest release wheel and verify it standalone."""

    @classmethod
    def setUpClass(cls) -> None:
        wheels = sorted((REPO_ROOT / "dist").glob("*.whl"), key=lambda p: p.stat().st_mtime)
        if not wheels:
            raise unittest.SkipTest(
                f"no wheel in {REPO_ROOT / 'dist'}; run `uv build` first"
            )
        cls.wheel_path = wheels[-1]

        cls.temporary_directory = tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True
        )
        cls.root_dir = Path(cls.temporary_directory.name)
        cls.venv_dir = cls.root_dir / "venv"

        # Create the throwaway venv with --system-site-packages so pip can
        # install the wheel with --no-deps (no network). On this machine the
        # running interpreter is itself a venv whose third-party runtime
        # dependencies live in its own site-packages; a .pth bridge exposes
        # those third-party packages only — the wheel provides web and
        # perovskite_bo (asserted in the child script).
        venv_create = subprocess.run(
            [
                sys.executable,
                "-m",
                "venv",
                "--system-site-packages",
                str(cls.venv_dir),
            ],
            cwd=str(cls.root_dir),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if venv_create.returncode != 0:
            raise AssertionError(
                "venv creation failed:\n" + venv_create.stdout + venv_create.stderr
            )

        cls.venv_python = (
            cls.venv_dir / "Scripts" / "python.exe"
            if sys.platform == "win32"
            else cls.venv_dir / "bin" / "python"
        )

        # Bridge to the running interpreter's site-packages so the child can
        # reuse already-installed THIRD-PARTY runtime dependencies (fastapi,
        # sqlalchemy, uvicorn, ...) without network access. This exposes only
        # third-party packages: the application packages `web` and
        # perovskite_bo` are installed from the wheel into the child venv's
        # own site-packages, which is searched first, and the child script
        # asserts that both resolve there — never under the repository src/.
        # Both venv layouts are platform-specific (Windows: Lib/site-packages,
        # posix: lib/python3.x/site-packages); query each interpreter's real
        # layout through sysconfig instead of hard-coding one.
        import sysconfig

        host_site_packages = Path(sysconfig.get_paths()["purelib"])
        child_site_probe = subprocess.run(
            [
                str(cls.venv_python),
                "-c",
                "import sysconfig; print(sysconfig.get_paths()['purelib'])",
            ],
            cwd=str(cls.root_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if child_site_probe.returncode != 0:
            raise AssertionError(
                "child site-packages probe failed:\n"
                + child_site_probe.stdout
                + child_site_probe.stderr
            )
        cls.child_site_packages = Path(child_site_probe.stdout.strip())
        bridge = cls.child_site_packages / "_host_runtime.pth"
        bridge.parent.mkdir(parents=True, exist_ok=True)
        bridge.write_text(str(host_site_packages) + "\n", encoding="utf-8")

        # Install with an explicit --target: pip's own environment resolution
        # is unreliable in a venv created from another venv with system site
        # packages (on the CI runner it decided the application packages were
        # already satisfied and silently resolved them from the host), so the
        # wheel contents are unpacked directly into the child site-packages.
        install = subprocess.run(
            [
                str(cls.venv_python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--disable-pip-version-check",
                "--quiet",
                "--target",
                str(cls.child_site_packages),
                str(cls.wheel_path.resolve()),
            ],
            cwd=str(cls.root_dir),
            capture_output=True,
            text=True,
            timeout=600,
        )
        if install.returncode != 0:
            raise AssertionError(
                "wheel install failed:\n" + install.stdout + install.stderr
            )
        for package in ("web", "perovskite_bo"):
            if not (cls.child_site_packages / package).is_dir():
                raise AssertionError(
                    f"wheel install did not place {package}/ under "
                    f"{cls.child_site_packages}; install output:\n"
                    + install.stdout
                    + install.stderr
                )

        cls.recipe_path = cls.root_dir / "recipe.json"
        device_recipe, deposition_process = complete_guided_setup()
        recipe = {
            **deposition_recipe_from_process(deposition_process),
            "device_recipe": device_recipe,
        }
        cls.recipe_path.write_text(
            json.dumps(recipe), encoding="utf-8"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_fresh_installed_wheel_smoke(self) -> None:
        """The installed wheel serves React, redirects legacy GETs, and exports."""
        run = subprocess.run(
            [
                str(self.venv_python),
                "-c",
                CHILD_SCRIPT,
                str(REPO_ROOT),
                str(self.recipe_path),
            ],
            cwd=str(self.root_dir),
            capture_output=True,
            text=True,
            timeout=600,
        )
        if run.returncode != 0:
            raise AssertionError(
                f"installed-wheel smoke subprocess failed (exit {run.returncode}):\n"
                f"--- stdout ---\n{run.stdout}\n--- stderr ---\n{run.stderr}"
            )
        self.assertIn("installed-wheel smoke: OK", run.stdout)


if __name__ == "__main__":
    unittest.main()