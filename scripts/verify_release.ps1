param(
    [switch]$SkipNpmInstall
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$testTemp = Join-Path $projectRoot ".tmp\release-verification"

if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到项目虚拟环境：$python"
}

New-Item -ItemType Directory -Force -Path $testTemp | Out-Null

function Invoke-Checked {
    param(
        [string]$Label,
        [scriptblock]$Command
    )
    Write-Host "`n==> $Label" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label 失败，退出码：$LASTEXITCODE"
    }
}

Push-Location $projectRoot
try {
    Invoke-Checked "运行后端测试" {
        & $python -m pytest --basetemp $testTemp
    }
    Invoke-Checked "运行 Agent/RAG 评估" {
        & $python -m procurement_agent.evaluation.runner
    }

    Push-Location (Join-Path $projectRoot "frontend")
    try {
        if (-not $SkipNpmInstall) {
            Invoke-Checked "安装锁定的前端依赖" { npm ci }
        }
        Invoke-Checked "检查前端类型" { npm run typecheck }
        Invoke-Checked "构建前端生产包" { npm run build }
    }
    finally {
        Pop-Location
    }

    Write-Host "`n全部发布验证通过。" -ForegroundColor Green
}
finally {
    Pop-Location
}
