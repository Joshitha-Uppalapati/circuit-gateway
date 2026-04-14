#!/bin/bash

URL="http://127.0.0.1:8080/v1/chat/completions"
KEY="test-key"

echo "health"
curl -s http://127.0.0.1:8080/health
echo ""

echo "ok request"
curl -s $URL \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hello"}]}'
echo ""

echo "forcing failures"
for i in {1..4}; do
  curl -s $URL \
    -H "Authorization: Bearer $KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"gpt-4o","messages":[{"role":"user","content":"force failure"}]}'
  echo ""
done

echo "after breaker"
curl -s $URL \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"force failure again"}]}'
echo ""

echo "metrics"
curl -s http://127.0.0.1:8080/metrics
echo ""