# File Service

**Purpose:** Handle file uploads, storage, and retrieval for documents users submit for review.

**Key functions:**
- Save uploaded files to `data/uploads/<uuid>/` and return metadata.
- Provide helpers to list and retrieve stored files and their paths.

**Inputs:** upload stream, filename, content type, optional metadata.

**Outputs:** file save result with local path, size, and identifier.

**Side effects:** Writes files to disk under `data/uploads/`; must ensure safe filename handling and directory permissions.

**Tests / checks:** Validate successful save & retrieval, ensure directory creation, and confirm behavior on duplicate filenames.
