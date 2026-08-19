#!/bin/bash
# Clear Agreement Workflow Data via Docker
# Run this script to clear all agreement-related data from the database

echo "Clearing Agreement Workflow Data..."
echo ""

# Get database container name (adjust if needed)
DB_CONTAINER="postgres"  # Change this to your actual postgres container name

# SQL commands to clear agreement data
psql_command="
DELETE FROM agreement_inline_comments;
DELETE FROM agreement_comments;
DELETE FROM agreement_documents;
DELETE FROM agreement_versions;
DELETE FROM agreements;
DELETE FROM study_templates;

SELECT 'agreement_inline_comments' as table_name, COUNT(*) as remaining FROM agreement_inline_comments
UNION ALL
SELECT 'agreement_comments', COUNT(*) FROM agreement_comments
UNION ALL
SELECT 'agreement_documents', COUNT(*) FROM agreement_documents
UNION ALL
SELECT 'agreement_versions', COUNT(*) FROM agreement_versions
UNION ALL
SELECT 'agreements', COUNT(*) FROM agreements
UNION ALL
SELECT 'study_templates', COUNT(*) FROM study_templates;
"

# Execute via docker exec (adjust connection string as needed)
# Option 1: If you know the container name
# docker exec -i $DB_CONTAINER psql -U postgres -d crm_db -c "$psql_command"

# Option 2: Use docker-compose exec
echo "To execute, run one of these commands:"
echo ""
echo "Option 1 (if using docker-compose):"
echo "  docker-compose exec postgres psql -U postgres -d crm_db -c \"$psql_command\""
echo ""
echo "Option 2 (if you know container name):"
echo "  docker exec -i postgres psql -U postgres -d crm_db -c \"$psql_command\""
echo ""
echo "Or use the SQL file directly:"
echo "  docker exec -i postgres psql -U postgres -d crm_db < clear_agreement_data.sql"
