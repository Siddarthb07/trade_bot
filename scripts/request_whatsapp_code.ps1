# Request WAHA pairing code for phone login (no QR scan)
param(
  [string]$Phone = "919606754584",
  [string]$ApiUrl = "http://127.0.0.1:3001",
  [string]$ApiKey = "smtracker-waha-key-7f3a9c2e1b8d4f6a"
)

$headers = @{
  "X-Api-Key"    = $ApiKey
  "Content-Type" = "application/json"
}
$body = @{ phoneNumber = $Phone } | ConvertTo-Json

$response = Invoke-RestMethod -Uri "$ApiUrl/api/default/auth/request-code" -Method Post -Headers $headers -Body $body
Write-Host ""
Write-Host "Pairing code: $($response.code)" -ForegroundColor Green
Write-Host ""
Write-Host "On your phone (WhatsApp):"
Write-Host "  1. Linked devices -> Link a device"
Write-Host "  2. Link with phone number instead"
Write-Host "  3. Enter this code: $($response.code)"
Write-Host ""
Write-Host "Code expires in ~2 minutes. Re-run this script if it fails."
