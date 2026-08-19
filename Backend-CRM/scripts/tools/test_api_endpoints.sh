#!/bin/bash
# Test API endpoints for dual-database architecture

API_BASE="http://localhost:8000/api"

echo "=========================================="
echo "API ENDPOINT TESTING"
echo "=========================================="

# Test health
echo -e "\n[TEST] Health check..."
curl -s "$API_BASE/health" | jq .

# Test conversation creation
echo -e "\n[TEST] Creating conversation..."
CONV_RESPONSE=$(curl -s -X POST "$API_BASE/conversations" \
  -H "Content-Type: application/json" \
  -d '{
    "participant_email": "test@example.com",
    "subject": "Test Conversation",
    "study_id": "1",
    "site_id": "1"
  }')
echo "$CONV_RESPONSE" | jq .
CONV_ID=$(echo "$CONV_RESPONSE" | jq -r '.id')
echo "Created conversation ID: $CONV_ID"

# Test listing conversations
echo -e "\n[TEST] Listing conversations..."
curl -s "$API_BASE/conversations?limit=5" | jq '.[0] | {id, subject, participant_email}'

# Test creating message
echo -e "\n[TEST] Creating message..."
MSG_RESPONSE=$(curl -s -X POST "$API_BASE/conversations/$CONV_ID/messages" \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "email",
    "body": "Test message from API"
  }')
echo "$MSG_RESPONSE" | jq '{id, body, channel, status}'

# Test getting conversation with messages
echo -e "\n[TEST] Getting conversation with messages..."
curl -s "$API_BASE/conversations/$CONV_ID?limit=10" | jq '{id, subject, message_count: (.messages | length)}'

# Test statistics
echo -e "\n[TEST] Getting conversation statistics..."
curl -s "$API_BASE/conversations/stats" | jq .

echo -e "\n=========================================="
echo "API TESTING COMPLETE"
echo "=========================================="

