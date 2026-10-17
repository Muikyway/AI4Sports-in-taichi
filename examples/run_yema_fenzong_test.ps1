$ErrorActionPreference = "Stop"

Set-Location (Split-Path $PSScriptRoot -Parent)

python -m rule_scoring `
  --rules rules\yema_fenzong_test.yaml `
  --evidence examples\yema_fenzong_evidence.json `
  --mode strict `
  --output examples\yema_fenzong_score.json

python scripts\generate_report.py `
  --score examples\yema_fenzong_score.json `
  --output examples\yema_fenzong_report.md

Write-Host "Generated examples\yema_fenzong_score.json"
Write-Host "Generated examples\yema_fenzong_report.md"
