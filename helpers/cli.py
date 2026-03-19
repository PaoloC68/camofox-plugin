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
        if self._explicit_path:
            return [self._explicit_path]
        # Try direct binary first (faster)
        direct = _find_camofox_binary()
        if direct:
            return [direct]
        # Fall back to npx (always works if npm package is installed)
        npx = _find_npx()
        if npx:
            return [npx, "camofox"]
        raise CamofoxCliNotFoundError(
            "CamoFox CLI is not available. The camofox binary and npx were not found. "
            "CLI-based actions (session save/load, auth vault) require the CLI. "
            "REST-based actions (open, snapshot, click, navigate, search) work without it."
        )

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
