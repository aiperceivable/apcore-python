### Problem
The 128-character limit for Module IDs was becoming a bottleneck for cross-language integration, particularly when deriving IDs from deeply nested Java or .NET namespaces. This caused registration failures for modules that would otherwise be valid.

### Why
The original limit was based on early filesystem safety assumptions. However, PROTOCOL_SPEC §2.7 EBNF constraint #1 was updated to accommodate deeper hierarchies while still remaining safe for common filesystems like ext4, NTFS, and APFS (where the byte limit for filenames is typically 255).

### Solution
Raised `MAX_MODULE_ID_LENGTH` from 128 to 192 characters in `apcore/registry/registry.py`. This relaxation is forward-compatible for existing modules while providing enough headroom for long FQN-derived IDs.

### Verification
Added a test case in `tests/registry/test_registry.py` that successfully registers a module with a 192-character ID and fails for a 193-character ID. Verified filesystem safety by running tests on Linux and macOS.
