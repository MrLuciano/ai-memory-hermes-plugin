from __future__ import annotations

import argparse
import datetime
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# Ensure sibling modules are findable when this file is loaded standalone
# (Hermes pre-loads submodules before executing __init__.py).
_PLUGIN_DIR = str(Path(__file__).resolve().parent)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from client import AiMemoryClient  # noqa: E402
from config import _secret_keys, load_config, save_config  # noqa: E402

PLUGIN_DIR = Path(__file__).resolve().parent
REPO_TARBALL_URL = "https://github.com/MrLuciano/ai-memory-hermes-plugin/archive/refs/heads/main.zip"


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("status", help="Show ai-memory server connection status")
    p.set_defaults(func=cmd_status)

    p = subparsers.add_parser("config", help="Show ai-memory plugin configuration")
    p.set_defaults(func=cmd_config)

    p = subparsers.add_parser("config-set", help="Set a config value (secrets are env-only)")
    p.add_argument("key", help="Config key to set")
    p.add_argument("value", help="Value to set")
    p.set_defaults(func=cmd_config_set)

    p = subparsers.add_parser("link", help="Link plugin into Hermes plugin directory")
    p.set_defaults(func=cmd_link)

    p = subparsers.add_parser("update", help="Update the ai-memory plugin from GitHub")
    p.set_defaults(func=cmd_update)


def cmd_status(args: argparse.Namespace) -> None:
    config = load_config(args.hermes_home)
    client = AiMemoryClient(config)
    try:
        result = client.status()
        print("ai-memory server: reachable")
        print(f"  Pages:    {result.get('pages', '?')}")
        print(f"  Sessions: {result.get('sessions', '?')}")
    except Exception as e:
        print(f"ai-memory server: unreachable ({e})")


def cmd_config(args: argparse.Namespace) -> None:
    config = load_config(args.hermes_home)
    secrets = _secret_keys()
    print("ai-memory configuration:")
    print(f"  server_url: {config.server_url}")
    for key, env_var in secrets.items():
        value = getattr(config, key, "")
        if os.environ.get(env_var):
            status = f"(set via env: {env_var})"
        elif value:
            status = "(set — migrate to env var)"
        else:
            status = "(not set)"
        print(f"  {key}: {status}")
    print(f"  workspace:  {config.workspace}")
    print(f"  project:    {config.project}")


def cmd_config_set(args: argparse.Namespace) -> None:
    secrets = _secret_keys()
    key = args.key
    value = args.value

    if key in secrets:
        env_var = secrets[key]
        print(f"NOT WRITTEN TO DISK: {key} is a secret — use an environment variable:")
        print(f"  export {env_var}='{value}'")
        print("Add it to your shell profile or systemd environment for persistence.")
        return

    skipped = save_config({key: value}, args.hermes_home)
    if skipped:
        for s in skipped:
            print(f"  skipped: {s} (use env var)")
    print(f"  saved: {key} -> {Path(args.hermes_home) / 'ai-memory.json'}")


def cmd_link(args: argparse.Namespace) -> None:
    target_dir = Path(args.hermes_home) / "plugins" / "ai-memory"
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    if target_dir.exists():
        if os.path.islink(str(target_dir)):
            print(f"Already linked: {target_dir} -> {PLUGIN_DIR}")
        else:
            print(f"Target exists but is not a symlink: {target_dir}")
        return

    try:
        os.symlink(str(PLUGIN_DIR), str(target_dir), target_is_directory=True)
        print(f"Linked: {target_dir} -> {PLUGIN_DIR}")
    except FileExistsError:
        print(f"Already linked: {target_dir}")
    except OSError as e:
        print(f"Failed to link: {e}")


def cmd_update(args: argparse.Namespace) -> None:
    hermes_home = Path(args.hermes_home)
    plugin_dir = hermes_home / "plugins" / "ai-memory"
    config_file = hermes_home / "ai-memory.json"
    backup_root = hermes_home / ".ai-memory-backups"
    wrong_plugin_dir = hermes_home / "plugins" / "memory" / "ai-memory"

    print("==> ai-memory Hermes plugin updater")
    print("")

    if not plugin_dir.exists():
        print("ERROR: plugin not installed at {plugin_dir}")
        print("Run the install script first.")
        return

    if plugin_dir.is_dir() and not (plugin_dir / "__init__.py").exists():
        print(f"WARNING:     {plugin_dir} exists but is empty; continuing update.")

    if wrong_plugin_dir.exists():
        print("")
        print(f"  WARNING:     found {wrong_plugin_dir}")
        print("               User-installed memory providers belong in {plugin_dir},")
        print("               not in plugins/memory/. Remove the nested path.")

    update_from_local = os.environ.get("UPDATE_FROM_LOCAL", "false").lower() == "true"

    # Resolve source. The CLI update defaults to GitHub; UPDATE_FROM_LOCAL=true
    # is only safe for non-symlink installs (otherwise PLUGIN_DIR points to the
    # local repo itself and we would copy it onto itself).
    plugin_src: Path
    tmp_dir: Path | None = None
    if update_from_local and not _is_symlink_or_junction(plugin_dir):
        plugin_src = PLUGIN_DIR
        print(f"  Source:      {plugin_src} (local repo)")
    else:
        if update_from_local and _is_symlink_or_junction(plugin_dir):
            print(
                "  NOTE:        UPDATE_FROM_LOCAL=true ignored for "
                "symlink/junction install; using GitHub"
            )
        repo_url = os.environ.get("REPO_TARBALL_URL", REPO_TARBALL_URL)
        tmp_dir = Path(tempfile.mkdtemp())
        tarball = tmp_dir / "repo.zip"
        print(f"  Source:      {repo_url} (downloading...)")
        try:
            urllib.request.urlretrieve(repo_url, tarball)
        except Exception as e:
            print(f"ERROR: failed to download update: {e}")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return
        with zipfile.ZipFile(tarball, "r") as zf:
            zf.extractall(tmp_dir)
        plugin_src = tmp_dir / "ai-memory-hermes-plugin-main" / "plugins" / "memory" / "ai-memory"
        if not (plugin_src / "__init__.py").exists():
            print(f"ERROR: downloaded plugin source not found at {plugin_src}")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return

    print(f"  Target:      {plugin_dir}")

    # Backup current install outside plugins/ so Hermes does not discover it
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    backup_dir = backup_root / f"ai-memory.bak.{timestamp}"
    shutil.copytree(plugin_dir, backup_dir)
    print(f"  Backup:      {backup_dir}")

    # Remove old install
    if _is_symlink_or_junction(plugin_dir):
        plugin_dir.unlink()
    else:
        shutil.rmtree(plugin_dir)

    # Install updated files
    shutil.copytree(plugin_src, plugin_dir)
    print("  Updated:     copy (from downloaded source)")

    # Preserve config — strip any secrets from old backup
    backup_config = backup_dir / "ai-memory.json"
    if backup_config.exists() and not config_file.exists():
        try:
            import json as _json
            old_cfg = _json.loads(backup_config.read_text())
            for secret_key in _secret_keys():
                old_cfg.pop(secret_key, None)
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_text(_json.dumps(old_cfg, indent=2))
            print("  Config:      restored from backup (secrets stripped)")
        except Exception:
            shutil.copy2(backup_config, config_file)
            print("  Config:      restored from backup")
    elif config_file.exists():
        print(f"  Config:      {config_file} (preserved)")
    else:
        default_config = {
            "server_url": "http://127.0.0.1:49374",
            "workspace": "hermes",
            "project": "hermes-default",
        }
        config_body = ",\n".join(f'  "{k}": "{v}"' for k, v in default_config.items())
        config_file.write_text("{\n" + config_body + "\n}\n")
        print(f"  Config:      {config_file} (created)")

    # Cleanup temp download
    if tmp_dir:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print("  Cleanup:     removed temporary download")

    # List backups
    print("")
    print("  Backups:")
    if backup_root.exists():
        backups = sorted(backup_root.glob("ai-memory.bak.*"))
        for backup in backups:
            print(f"    - {backup}")

    # Verify update
    if not (plugin_dir / "__init__.py").exists():
        print("")
        print(f"ERROR: update verification failed — {plugin_dir}/__init__.py is missing.")
        print(f"             Restore from backup: {backup_dir}")
        return

    print("")
    print("==> Done. Restart Hermes for the update to take effect.")


def _is_symlink_or_junction(path: Path) -> bool:
    """Return True if path is a symlink or Windows junction."""
    if path.is_symlink():
        return True
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        return attrs != -1 and bool(attrs & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except Exception:
        return False
