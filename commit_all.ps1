
$files = git status -uall --porcelain | ForEach-Object { $_.Substring(3).Trim() }
foreach ($file in $files) {
    if ($file -ne "") {
        Write-Host "Committing $file..."
        git add "$file"
        git commit -m "Update $file"
    }
}
Write-Host "All files committed."
