import asyncio
import json
import shutil
import subprocess
import logging
import os

logger = logging.getLogger(__name__)


class CamofoxCliNotFoundError(Exception):
    """camofox CLI not available."""
    pass


class CamofoxCliError(Exception):
    """camofox CLI command failed."""
    def __init__(self, message: str, returncode: int = 1):
        self.returncode = returncode
        super().__init__(message)


def _find_npx() -> str | None:
    """Find npx binary."""
    return shutil.which("npx")


def _is_camofox_package_installed() -> bool:
    """Check if the global npm package is installed."""
    try:
        result = subprocess.run(
            ["npm", "list", "-g", "camofox-browser", "--depth=0"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return "camofox-browser" in result.stdout
    except Exception:
        return False


def _find_camofox_binary() -> str | None:
    """Find the camofox binary on PATH or common locations."""
    found = shutil.which("camofox")
    if found:
        return found
    # Check npm global bin
    try:
        result = subprocess.run(
            ["npm", "bin", "-g"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            candidate = os.path.join(result.stdout.strip(), "camofox")
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    except Exception:
        pass
    # Common locations
    for path in [
        "/usr/local/bin/camofox",
        "/usr/bin/camofox",
        os.path.expanduser("~/.local/bin/camofox"),
        os.path.expanduser("~/.npm-global/bin/camofox"),
        "/root/.npm-global/bin/camofox",
    ]:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def install_camofox_package() -> bool:
    """Install the global npm package that provides the server and CLI."""
    try:
        result = subprocess.run(
            ["npm", "install", "-g", "camofox-browser"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            logger.warning("CamoFox CLI auto-install failed: %s", result.stderr.strip())
            return False
        return True
    except Exception as e:
        logger.warning("CamoFox CLI auto-install raised: %s", e)
        return False


def resolve_camofox_command(
    binary_path: str | None = None,
    *,
    auto_install: bool = True,
) -> list[str]:
    """Resolve a usable camofox command, optionally repairing install first."""
    if binary_path:
        return [binary_path]

    direct = _find_camofox_binary()
    if direct:
        return [direct]

    npx = _find_npx()
    if npx and _is_camofox_package_installed():
        return [npx, "camofox"]

    if auto_install and install_camofox_package():
        direct = _find_camofox_binary()
        if direct:
            return [direct]
        npx = _find_npx()
        if npx and _is_camofox_package_installed():
            return [npx, "camofox"]

    raise CamofoxCliNotFoundError(
        "CamoFox CLI is not available. Automatic repair could not find or install it. "
        "Install the global npm package `camofox-browser` and ensure either the "
        "`camofox` binary or `npx camofox` is usable."
    )


def get_cli_status(
    binary_path: str | None = None,
    *,
    auto_install: bool = False,
) -> dict:
    """Return current CLI usability without raising."""
    if binary_path:
        return {
            "installed": True,
            "usable": True,
            "path": binary_path,
            "source": "explicit",
        }

    direct = _find_camofox_binary()
    if direct:
        return {
            "installed": True,
            "usable": True,
            "path": direct,
            "source": "binary",
        }

    npx = _find_npx()
    if npx and _is_camofox_package_installed():
        return {
            "installed": True,
            "usable": True,
            "path": npx,
            "source": "npx",
        }

    if auto_install:
        try:
            cmd = resolve_camofox_command(binary_path, auto_install=True)
            return {
                "installed": True,
                "usable": True,
                "path": cmd[0],
                "source": "auto_install",
            }
        except CamofoxCliNotFoundError:
            pass

    return {
        "installed": False,
        "usable": False,
        "path": None,
        "source": None,
    }


class CamofoxCli:
    """Subprocess executor for camofox CLI commands.

    Resolution is LAZY — construction never fails. The error is raised
    only when execute() is called and no binary/npx can be found.
    """

    def __init__(self, binary_path: str | None = None, default_user: str = ""):
        self.default_user = default_user
        self._explicit_path = binary_path
        self._cmd_prefix: list[str] | None = None

    def _resolve_command(self) -> list[str]:
        """Lazy resolution — called on first execute(), not in __init__."""
        return resolve_camofox_command(self._explicit_path, auto_install=True)

    async def execute(self, *args: str, timeout: int = 30) -> dict:
        """Run a camofox CLI command and return parsed JSON output."""
        # Lazy resolve on first call
        if self._cmd_prefix is None:
            self._cmd_prefix = self._resolve_command()

        cmd = list(self._cmd_prefix)
        cmd.extend(args)
        if self.default_user and "--user" not in args:
            cmd.extend(["--user", self.default_user])
        if "--format" not in args:
            cmd.extend(["--format", "json"])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise CamofoxCliError(
                f"camofox command timed out after {timeout}s: {' '.join(args)}",
                returncode=-1,
            )

        if proc.returncode != 0:
            err_msg = stderr.decode().strip() or stdout.decode().strip() or "Unknown error"
            raise CamofoxCliError(err_msg, returncode=proc.returncode)

        output = stdout.decode().strip()
        if not output:
            return {"ok": True}
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"ok": True, "raw": output}
