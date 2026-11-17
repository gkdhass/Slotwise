#!/usr/bin/env pwsh
Set-Location (Get-Location)
& "backend\.venv\Scripts\pytest.exe" "backend\tests\db" "--tb=no" "-q"
