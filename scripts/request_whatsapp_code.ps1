# Request WAHA pairing code for phone login (no QR scan)
param(
  [string]$Phone = "",
  [string]$ApiUrl = "http://127.0.0.1:3001",
  [string]$ApiKey = ""
)

if (-not $Phone) {
  $Phone = $env:WHATSAPP_TO
}
if (-not $Phone) {
  Write-Error "Set WHATSAPP_TO in .env or pass -Phone 91XXXXXXXXXX"
  exit 1
}

if (-not $ApiKey) {
  $ApiKey = $env:WAHA_API_KEY
}
if (-not $ApiKey) {
  Write-Error "Set WAHA_API_KEY in .env or pass -ApiKey"
  exit 1
}

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
