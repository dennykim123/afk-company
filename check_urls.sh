#!/bin/bash

sites_file="config/sites.txt"
failed_url=""
failed_code=""
success_count=0
total_count=0

while IFS= read -r url; do
  # Skip empty lines
  [[ -z "$url" ]] && continue
  
  total_count=$((total_count + 1))
  
  # Check HTTP status code with curl
  http_code=$(curl -s -L --max-time 15 -o /dev/null -w "%{http_code}" "$url")
  
  echo "Checking $url: $http_code"
  
  if [[ "$http_code" == "200" ]]; then
    success_count=$((success_count + 1))
  else
    # Store first failing URL
    if [[ -z "$failed_url" ]]; then
      failed_url="$url"
      failed_code="$http_code"
    fi
  fi
done < "$sites_file"

# Output result
if [[ -z "$failed_url" ]]; then
  echo "DONE: $success_count/$total_count sites healthy"
else
  echo "BLOCKED: $failed_url returned $failed_code"
fi
