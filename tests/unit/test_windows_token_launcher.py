from pathlib import Path


def test_windows_token_launcher_keeps_secret_input_temporary_and_hidden() -> None:
    script = (Path(__file__).parents[2] / "scripts" / "start_dota_support_draft.ps1").read_text(
        encoding="utf-8"
    )

    assert "$PSScriptRoot" in script
    assert ".venv\\Scripts\\python.exe" in script
    assert (
        "Read-Host -Prompt 'Paste your STRATZ token for this local launch' -AsSecureString"
        in script
    )
    assert "[string]::IsNullOrWhiteSpace($token)" in script
    assert "Token was empty. The app was not started." in script
    assert "[Environment]::SetEnvironmentVariable('STRATZ_API_TOKEN', $token, 'Process')" in script
    assert "& $python -m dota_support_draft" in script
    assert "finally" in script
    assert "[Environment]::SetEnvironmentVariable('STRATZ_API_TOKEN', $null, 'Process')" in script
    assert "[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenBstr)" in script
    assert "$secureToken.Dispose()" in script
    assert "Write-Output $token" not in script
    assert "Write-Host $token" not in script
