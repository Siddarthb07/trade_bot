# Host-side NSE fallback ingest (Windows Task Scheduler)
# Posts nsepython data to the API when Docker ingest fails.

param(
  [string]$ApiUrl = "http://127.0.0.1:8000/internal/ingest/nse",
  [string]$ApiKey = "host-fallback-key"
)

$ErrorActionPreference = "Stop"

try {
  python -c @"
import json, sys
try:
  from nsepython import nse_largedeals
except ImportError:
  print(json.dumps({'error': 'nsepython not installed on host'}))
  sys.exit(1)

payloads = []
for mode in ('bulk_deals', 'block_deals'):
  try:
    df = nse_largedeals(mode=mode)
    for _, row in df.iterrows():
      payloads.append({
        'source': 'nse_bulk' if 'bulk' in mode else 'nse_block',
        'source_ref': f\"host-{row.get('SYMBOL','')}-{row.get('CLIENT_NAME','')}-{row.get('DATE','')}\",
        'market': 'IN',
        'entity': str(row.get('CLIENT_NAME', 'UNKNOWN')),
        'ticker': str(row.get('SYMBOL', '')),
        'action': str(row.get('BUY_SELL', 'BUY')),
        'qty': float(row.get('QUANTITY', 0) or 0),
        'value': None,
        'disclosed_at': str(row.get('DATE')),
        'source_url': 'https://www.nseindia.com/market-data/block-deal',
        'raw_json': row.to_dict(),
      })
  except Exception as exc:
    print(f'mode failed: {exc}', file=sys.stderr)

print(json.dumps({'signals': payloads}))
"@ | Out-File -Encoding utf8 "$env:TEMP\nse_payload.py"

  $json = python "$env:TEMP\nse_payload.py"
  if ($LASTEXITCODE -ne 0) { throw "nsepython script failed" }

  Invoke-RestMethod -Uri $ApiUrl -Method Post -Headers @{ "X-Api-Key" = $ApiKey } -ContentType "application/json" -Body $json
  Write-Host "Host NSE fallback ingest complete"
}
catch {
  Write-Error $_
  exit 1
}
