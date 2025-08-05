# setup_task.ps1
param (
    [string]$TaskName = "FB-Pipeline"
)

# 1. Get this script's directory (repo path)
$repo = Split-Path -Parent $MyInvocation.MyCommand.Definition

# 2. Load the task XML template
$xml = Get-Content "$repo\fb_pipeline_daily.xml"

# 3. Replace placeholders
$xml = $xml -replace '{{CLONED_PATH}}', ($repo -replace '\\','\\')
$xml = $xml -replace '{{TODAY}}', (Get-Date -Format "yyyy-MM-dd")

# 4. Save a temporary filled-in XML file (UTF-16 required!)
$tempFile = [IO.Path]::GetTempFileName()
$xml | Set-Content $tempFile -Encoding Unicode

# 5. Register the task
schtasks /create /tn $TaskName /xml $tempFile /f

# 6. Clean up
Remove-Item $tempFile

Write-Host " Task '$TaskName' created and scheduled successfully!"
Write-Host " Repo path: $repo"
Write-Host " Config file: C:\conf\creds.env (edit for brands, scrolls, etc.)"
