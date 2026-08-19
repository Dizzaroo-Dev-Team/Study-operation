# Save Document Feature Implementation

## Overview
Enhanced the document review workflow with a "Save Document" feature that allows users to persist their review progress (including comments) without submitting, and ensures "Submit Review" always uses the latest saved version.

## Changes Made

### 1. Backend API Endpoints (`app/api/v1/endpoints/legal_docs.py`)

#### New Endpoints:
- **POST `/agreements/{agreement_id}/save-review-document`**
  - Captures current document state with all comments
  - Uploads to Azure Blob Storage in `review-documents` folder
  - Uses unique naming with timestamp/UUID for versioning
  - Updates AgreementReviewDocument with saved file info

- **GET `/agreements/{agreement_id}/latest-saved-review`**
  - Retrieves the most recently saved review document
  - Returns file URL and unique document key for OnlyOffice
  - Ensures cache issues are avoided with unique keys

#### Enhanced Endpoint:
- **POST `/agreements/{agreement_id}/submit-review`**
  - Updated to check for and use latest saved review document first
  - Falls back to original review document if no saved version exists
  - Ensures submission always uses the most recent version with comments

### 2. Database Schema Updates (`app/models.py`)

#### AgreementReviewDocument Model - New Fields:
- `saved_review_url` (TEXT) - URL to saved document in Azure
- `saved_review_path` (TEXT) - Blob path in Azure storage
- `saved_at` (TIMESTAMP) - When document was last saved

#### Migration:
- Added SQL migration script to safely add new fields
- Fields are nullable to maintain backward compatibility

### 3. Azure Storage Enhancements (`app/utils/azure_storage.py`)

#### New Functions:
- `build_review_save_blob_name()` - Creates unique blob paths for saved reviews
- `get_file_url()` - Retrieves URL for a blob
- Enhanced `upload_file()` - Supports both BinaryIO and bytes content

#### Storage Structure:
```
review-documents/
├── review_{agreement_id}_{timestamp}_{unique_id}.docx
└── review_ab030b35-2150-4ce0-8342-6e8dc9f105af_20260318_143022_a1b2c3d4.docx
```

### 4. Frontend Implementation (`src/components/AgreementReviewPage.tsx`)

#### New Features:
- **Save Document Button** (Blue, positioned left of Submit Review)
- **State Management** for save operations
- **Success Messages** for user feedback
- **Error Handling** for failed save operations

#### UI Changes:
- Added "Save Document" button before "Submit Review"
- Added success message display
- Proper loading states and disabled button handling
- Fixed TypeScript lint warnings

#### Behavior:
- Forces OnlyOffice save before capturing document
- Calls save API endpoint
- Shows temporary success message
- Maintains review progress without submission

## Workflow

### Save Document Flow:
1. User adds comments in OnlyOffice
2. Clicks "Save Document" button
3. Frontend calls OnlyOffice force-save
4. Backend downloads current document state
5. Uploads to Azure Blob Storage with unique naming
6. Updates database with saved file info
7. Shows success message to user

### Submit Review Flow (Enhanced):
1. User clicks "Submit Review"
2. Backend checks for latest saved review document
3. If found: downloads and uses saved version
4. If not found: uses original review document
5. Processes submission with latest comments
6. Creates new agreement version with changes

## Technical Details

### API Response Examples:

#### Save Document Response:
```json
{
  "success": true,
  "message": "Review document saved successfully",
  "file_url": "https://account.blob.core.windows.net/container/review-documents/review_ab030b35-2150-4ce0-8342-6e8dc9f105af_20260318_143022_a1b2c3d4.docx",
  "blob_path": "review-documents/review_ab030b35-2150-4ce0-8342-6e8dc9f105af_20260318_143022_a1b2c3d4.docx",
  "saved_at": "2026-03-18T14:30:22Z",
  "review_document_id": "uuid-here"
}
```

#### Latest Saved Review Response:
```json
{
  "success": true,
  "file_url": "https://account.blob.core.windows.net/container/review-documents/review_ab030b35-2150-4ce0-8342-6e8dc9f105af_20260318_143022_a1b2c3d4.docx",
  "document_key": "review_ab030b35-2150-4ce0-8342-6e8dc9f105af_review_doc_id_1647625822",
  "saved_at": "2026-03-18T14:30:22Z",
  "review_document_id": "uuid-here",
  "file_type": "docx"
}
```

### Error Handling:
- Comprehensive error messages for all failure scenarios
- Graceful fallbacks for missing saved documents
- Proper logging for debugging
- User-friendly error messages in frontend

### Security:
- Uses existing authentication/authorization
- Validates tokens for review access
- Secure Azure Blob Storage access
- No sensitive data in URLs

## Testing

### Manual Testing Steps:
1. Start a document review process
2. Add comments in OnlyOffice editor
3. Click "Save Document" - verify success message
4. Add more comments
5. Click "Save Document" again - verify new version created
6. Click "Submit Review" - verify latest saved version is used
7. Check Azure Blob Storage for saved files

### Automated Testing:
- Database schema validation
- API endpoint availability
- Azure storage utility functions
- Frontend component structure

## Benefits

### For Users:
- **Progress Persistence**: Save review progress anytime
- **No Data Loss**: Comments preserved between sessions
- **Flexibility**: Review at own pace, submit when ready
- **Confidence**: Latest version always used for submission

### For System:
- **Version Control**: Multiple saved versions maintained
- **Storage Efficiency**: Separate storage for review documents
- **Audit Trail**: Clear history of review progress
- **Performance**: Optimized OnlyOffice configuration

## Deployment Notes

### Database Migration:
```sql
ALTER TABLE agreement_review_documents 
ADD COLUMN IF NOT EXISTS saved_review_url TEXT,
ADD COLUMN IF NOT EXISTS saved_review_path TEXT,
ADD COLUMN IF NOT EXISTS saved_at TIMESTAMP WITH TIME ZONE;
```

### Environment Variables:
- No new environment variables required
- Uses existing Azure Blob Storage configuration
- Compatible with current OnlyOffice setup

### Backward Compatibility:
- All existing functionality preserved
- New fields are nullable
- Graceful degradation if no saved document exists
- No breaking changes to existing APIs

## Future Enhancements

### Potential Improvements:
1. **Auto-save**: Periodic automatic saving during review
2. **Version History**: UI to view/restore previous saved versions
3. **Collaboration**: Multiple reviewers saving same document
4. **Analytics**: Track review progress and save patterns
5. **Notifications**: Alert users when documents are saved/updated

### Scaling Considerations:
- Azure Blob Storage handles unlimited files
- Database queries optimized for latest version lookup
- OnlyOffice caching strategies for performance
- Cleanup policies for old saved versions

## Summary

The Save Document feature successfully enhances the document review workflow by providing users with the ability to persist their review progress, ensuring no comments are lost, and guaranteeing that submissions always use the most recent version. The implementation maintains full backward compatibility while adding robust error handling, proper logging, and a seamless user experience.
