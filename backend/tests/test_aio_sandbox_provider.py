"""Tests for AioSandboxProvider mount helpers."""

import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from deerflow.config.paths import Paths, join_host_path

# ── ensure_thread_dirs ───────────────────────────────────────────────────────


def test_ensure_thread_dirs_creates_acp_workspace(tmp_path):
    """ACP workspace directory must be created alongside user-data dirs."""
    paths = Paths(base_dir=tmp_path)
    paths.ensure_thread_dirs("thread-1")

    assert (tmp_path / "threads" / "thread-1" / "user-data" / "workspace").exists()
    assert (tmp_path / "threads" / "thread-1" / "user-data" / "uploads").exists()
    assert (tmp_path / "threads" / "thread-1" / "user-data" / "outputs").exists()
    assert (tmp_path / "threads" / "thread-1" / "acp-workspace").exists()


def test_ensure_thread_dirs_acp_workspace_is_world_writable(tmp_path):
    """ACP workspace must be chmod 0o777 so the ACP subprocess can write into it."""
    paths = Paths(base_dir=tmp_path)
    paths.ensure_thread_dirs("thread-2")

    acp_dir = tmp_path / "threads" / "thread-2" / "acp-workspace"
    mode = oct(acp_dir.stat().st_mode & 0o777)
    assert mode == oct(0o777)


def test_host_thread_dir_rejects_invalid_thread_id(tmp_path):
    paths = Paths(base_dir=tmp_path)

    with pytest.raises(ValueError, match="Invalid thread_id"):
        paths.host_thread_dir("../escape")


# ── _get_thread_mounts ───────────────────────────────────────────────────────


def _make_provider(tmp_path):
    """Build a minimal AioSandboxProvider instance without starting the idle checker."""
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    with patch.object(aio_mod.AioSandboxProvider, "_start_idle_checker"):
        provider = aio_mod.AioSandboxProvider.__new__(aio_mod.AioSandboxProvider)
        provider._config = {}
        provider._sandboxes = {}
        provider._lock = MagicMock()
        provider._idle_checker_stop = MagicMock()
    return provider


def test_get_thread_mounts_includes_acp_workspace(tmp_path, monkeypatch):
    """_get_thread_mounts must include /mnt/acp-workspace (read-only) for docker sandbox."""
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    monkeypatch.setattr(aio_mod, "get_paths", lambda: Paths(base_dir=tmp_path))

    mounts = aio_mod.AioSandboxProvider._get_thread_mounts("thread-3")

    container_paths = {m[1]: (m[0], m[2]) for m in mounts}

    assert "/mnt/acp-workspace" in container_paths, "ACP workspace mount is missing"
    expected_host = str(tmp_path / "threads" / "thread-3" / "acp-workspace")
    actual_host, read_only = container_paths["/mnt/acp-workspace"]
    assert actual_host == expected_host
    assert read_only is True, "ACP workspace should be read-only inside the sandbox"


def test_get_thread_mounts_includes_user_data_dirs(tmp_path, monkeypatch):
    """Baseline: user-data mounts must still be present after the ACP workspace change."""
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    monkeypatch.setattr(aio_mod, "get_paths", lambda: Paths(base_dir=tmp_path))

    mounts = aio_mod.AioSandboxProvider._get_thread_mounts("thread-4")
    container_paths = {m[1] for m in mounts}

    assert "/mnt/user-data/workspace" in container_paths
    assert "/mnt/user-data/uploads" in container_paths
    assert "/mnt/user-data/outputs" in container_paths


def test_join_host_path_preserves_windows_drive_letter_style():
    base = r"C:\Users\demo\deer-flow\backend\.deer-flow"

    joined = join_host_path(base, "threads", "thread-9", "user-data", "outputs")

    assert joined == r"C:\Users\demo\deer-flow\backend\.deer-flow\threads\thread-9\user-data\outputs"


def test_get_thread_mounts_preserves_windows_host_path_style(tmp_path, monkeypatch):
    """Docker bind mount sources must keep Windows-style paths intact."""
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    monkeypatch.setenv("DEER_FLOW_HOST_BASE_DIR", r"C:\Users\demo\deer-flow\backend\.deer-flow")
    monkeypatch.setattr(aio_mod, "get_paths", lambda: Paths(base_dir=tmp_path))

    mounts = aio_mod.AioSandboxProvider._get_thread_mounts("thread-10")

    container_paths = {container_path: host_path for host_path, container_path, _ in mounts}

    assert container_paths["/mnt/user-data/workspace"] == r"C:\Users\demo\deer-flow\backend\.deer-flow\threads\thread-10\user-data\workspace"
    assert container_paths["/mnt/user-data/uploads"] == r"C:\Users\demo\deer-flow\backend\.deer-flow\threads\thread-10\user-data\uploads"
    assert container_paths["/mnt/user-data/outputs"] == r"C:\Users\demo\deer-flow\backend\.deer-flow\threads\thread-10\user-data\outputs"
    assert container_paths["/mnt/acp-workspace"] == r"C:\Users\demo\deer-flow\backend\.deer-flow\threads\thread-10\acp-workspace"


def test_get_thread_mounts_falls_back_to_discovered_container_bind_source(tmp_path, monkeypatch):
    """Use the gateway container's own bind source when host env points at a stale path."""
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    paths_mod = importlib.import_module("deerflow.config.paths")
    container_base_dir = tmp_path / "app" / "backend" / ".deer-flow"
    container_base_dir.mkdir(parents=True)
    host_base_dir = tmp_path / "srv" / "power-flow" / "infra" / "backend" / ".deer-flow"
    host_base_dir.mkdir(parents=True)

    monkeypatch.setenv("DEER_FLOW_HOST_BASE_DIR", str(tmp_path / "missing" / ".deer-flow"))
    monkeypatch.setenv("HOSTNAME", "gateway-container")
    monkeypatch.setattr(aio_mod, "get_paths", lambda: Paths(base_dir=container_base_dir))
    monkeypatch.setattr(paths_mod.subprocess, "run", lambda *args, **kwargs: MagicMock(stdout=json.dumps([{
        "Mounts": [
            {"Destination": str(container_base_dir), "Source": str(host_base_dir)},
        ]
    }])))
    paths_mod._MOUNT_SOURCE_CACHE.clear()

    mounts = aio_mod.AioSandboxProvider._get_thread_mounts("thread-11")

    container_paths = {container_path: host_path for host_path, container_path, _ in mounts}
    assert container_paths["/mnt/user-data/workspace"] == str(host_base_dir / "threads" / "thread-11" / "user-data" / "workspace")


def test_discover_or_create_only_unlocks_when_lock_succeeds(tmp_path, monkeypatch):
    """Unlock should not run if exclusive locking itself fails."""
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    provider = _make_provider(tmp_path)
    provider._discover_or_create_with_lock = aio_mod.AioSandboxProvider._discover_or_create_with_lock.__get__(
        provider,
        aio_mod.AioSandboxProvider,
    )

    monkeypatch.setattr(aio_mod, "get_paths", lambda: Paths(base_dir=tmp_path))
    monkeypatch.setattr(
        aio_mod,
        "_lock_file_exclusive",
        lambda _lock_file: (_ for _ in ()).throw(RuntimeError("lock failed")),
    )

    unlock_calls: list[object] = []
    monkeypatch.setattr(
        aio_mod,
        "_unlock_file",
        lambda lock_file: unlock_calls.append(lock_file),
    )

    with patch.object(provider, "_create_sandbox", return_value="sandbox-id"):
        with pytest.raises(RuntimeError, match="lock failed"):
            provider._discover_or_create_with_lock("thread-5", "sandbox-5")

    assert unlock_calls == []


def test_resolve_host_skills_path_prefers_existing_env_path(tmp_path, monkeypatch):
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    host_skills = tmp_path / "host-skills"
    host_skills.mkdir()
    container_skills = tmp_path / "container-skills"
    container_skills.mkdir()

    monkeypatch.setenv("DEER_FLOW_HOST_SKILLS_PATH", str(host_skills))

    resolved = aio_mod.AioSandboxProvider._resolve_host_skills_path(container_skills)

    assert resolved == str(host_skills)


def test_resolve_host_skills_path_infers_repo_checkout_from_host_base_dir(tmp_path, monkeypatch):
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    host_base_dir = tmp_path / "infra" / "backend" / ".deer-flow"
    host_base_dir.mkdir(parents=True)
    inferred_skills = tmp_path / "deer-flow" / "skills"
    inferred_skills.mkdir(parents=True)
    container_skills = tmp_path / "app" / "skills"
    container_skills.mkdir(parents=True)

    monkeypatch.setenv("DEER_FLOW_HOST_BASE_DIR", str(host_base_dir))
    monkeypatch.setenv("DEER_FLOW_HOST_SKILLS_PATH", str(tmp_path / "missing" / "skills"))

    resolved = aio_mod.AioSandboxProvider._resolve_host_skills_path(container_skills)

    assert resolved == str(inferred_skills)


def test_resolve_host_skills_path_uses_discovered_container_bind_source(tmp_path, monkeypatch):
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    paths_mod = importlib.import_module("deerflow.config.paths")
    host_skills = tmp_path / "srv" / "power-flow" / "deer-flow" / "skills"
    host_skills.mkdir(parents=True)
    container_skills = tmp_path / "app" / "skills"
    container_skills.mkdir(parents=True)

    monkeypatch.setenv("DEER_FLOW_HOST_SKILLS_PATH", str(tmp_path / "missing" / "skills"))
    monkeypatch.setenv("HOSTNAME", "gateway-container")
    monkeypatch.setattr(paths_mod.subprocess, "run", lambda *args, **kwargs: MagicMock(stdout=json.dumps([{
        "Mounts": [
            {"Destination": str(container_skills), "Source": str(host_skills)},
        ]
    }])))
    paths_mod._MOUNT_SOURCE_CACHE.clear()

    resolved = aio_mod.AioSandboxProvider._resolve_host_skills_path(container_skills)

    assert resolved == str(host_skills)


def test_resolve_host_skills_path_reconstructs_root_from_nested_mounts(tmp_path, monkeypatch):
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    paths_mod = importlib.import_module("deerflow.config.paths")
    host_skills = tmp_path / "srv" / "power-flow" / "deer-flow" / "skills"
    (host_skills / "public").mkdir(parents=True)
    (host_skills / "custom").mkdir(parents=True)
    container_skills = tmp_path / "app" / "skills"
    (container_skills / "public").mkdir(parents=True)
    (container_skills / "custom").mkdir(parents=True)

    monkeypatch.setenv("DEER_FLOW_HOST_SKILLS_PATH", str(tmp_path / "missing" / "skills"))
    monkeypatch.setenv("HOSTNAME", "gateway-container")
    monkeypatch.setattr(paths_mod.subprocess, "run", lambda *args, **kwargs: MagicMock(stdout=json.dumps([{
        "Mounts": [
            {"Destination": str(container_skills / "public"), "Source": str(host_skills / "public")},
            {"Destination": str(container_skills / "custom"), "Source": str(host_skills / "custom")},
        ]
    }])))
    paths_mod._MOUNT_SOURCE_CACHE.clear()

    resolved = aio_mod.AioSandboxProvider._resolve_host_skills_path(container_skills)

    assert resolved == str(host_skills)


def test_get_skills_mount_uses_inferred_host_path(tmp_path, monkeypatch):
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    host_base_dir = tmp_path / "infra" / "backend" / ".deer-flow"
    host_base_dir.mkdir(parents=True)
    inferred_skills = tmp_path / "deer-flow" / "skills"
    inferred_skills.mkdir(parents=True)
    container_skills = tmp_path / "app" / "skills"
    container_skills.mkdir(parents=True)

    monkeypatch.setenv("DEER_FLOW_HOST_BASE_DIR", str(host_base_dir))
    monkeypatch.setenv("DEER_FLOW_HOST_SKILLS_PATH", str(tmp_path / "missing" / "skills"))

    class _SkillsConfig:
        container_path = "/mnt/skills"

        @staticmethod
        def get_skills_path() -> Path:
            return container_skills

    class _Config:
        skills = _SkillsConfig()

    monkeypatch.setattr(aio_mod, "get_app_config", lambda: _Config())

    mount = aio_mod.AioSandboxProvider._get_skills_mount()

    assert mount == (str(inferred_skills), "/mnt/skills", True)
