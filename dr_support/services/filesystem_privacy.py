"""Conservative filesystem privacy checks for authorized hospital roots."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path


# Paths travel through the child environment, never through PowerShell code.
_WINDOWS_ACL_PROBE = r"""
$env:PSModulePath = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/Modules'
$ErrorActionPreference = 'Stop'
try {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $allowed = @($sid, 'S-1-5-18', 'S-1-5-32-544')
    $root = Get-Item -LiteralPath $env:DR_SUPPORT_PRIVACY_PROBE_ROOT -Force
    $items = @($root) + @(Get-ChildItem -LiteralPath $root.FullName -Recurse -Force)
    foreach ($item in $items) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'redirected' }
        $acl = Get-Acl -LiteralPath $item.FullName
        if ($acl.Owner -eq $null -or $acl.Access.Count -eq 0) { throw 'missing ACL' }
        $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
        if ($owner -notin $allowed) { throw 'untrusted owner' }
        $readable = $false
        foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
            if ($rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) { continue }
            $identity = $rule.IdentityReference.Value
            if ($rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow) {
                if ($identity -notin $allowed -and [int]$rule.FileSystemRights -ne 0) { throw 'broad access' }
                if ($identity -eq $sid -and ([int]$rule.FileSystemRights -band 1)) { $readable = $true }
            } elseif ($identity -in $allowed -and ([int]$rule.FileSystemRights -band 1)) {
                throw 'read denied'
            }
        }
        if (-not $readable) { throw 'no explicit operator read access' }
    }
    '{"private":true}'
} catch { '{"private":false}' }
"""


def has_reparse_component(path: Path) -> bool:
    """Reject symlinks and Windows junctions before canonicalizing a root."""
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            return True
    return False


def private_hospital_root(root: Path) -> bool:
    """Keep POSIX mode semantics; on Windows inspect real ACLs, including children.

    Windows permits only this operator, SYSTEM and local Administrators. Unknown
    principals, unreadable ACLs, redirected paths and probe failures are rejected.
    The probe never modifies permissions or logs paths/ACLs.
    """
    try:
        if has_reparse_component(root):
            return False
        if os.name != "nt":
            return (root.stat().st_mode & 0o077) == 0
        environment = os.environ.copy()
        environment["DR_SUPPORT_PRIVACY_PROBE_ROOT"] = str(root)
        windows_root = os.environ.get("SystemRoot", r"C:\Windows")
        executable = str(Path(windows_root) / "System32/WindowsPowerShell/v1.0/powershell.exe")
        result = subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_ACL_PROBE],
            env=environment, capture_output=True, text=True, timeout=30, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        payload = json.loads(result.stdout)
        return result.returncode == 0 and isinstance(payload, dict) and payload.get("private") is True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
