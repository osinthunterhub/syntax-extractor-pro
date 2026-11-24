# Research scope and verification notes

Reference: https://github.com/princepiamotox/Extractor_Pro_x
Snapshot: f4ac41b2903242f99dd914b1e7db9a484bc9e0bb (GPL-3.0).
Static inventory: 48 Python files, 13,105 AST source lines. Original audit's 44
findings and 16 defect-check passes are not working-feature certifications.
**Every original source line has NOT been fully audited.** The attached command
inventory was derived by AST inspection without importing/running target code.
Feature matrix groups capabilities; it is not proof of A–Z equivalence.

New core/adapters are independently written. No upstream embedded credentials,
login records, fixed decryption secrets or raw source snapshot are bundled.
AppX endpoints and Classplus schemas are reference-informed assumptions. Neither
adapter was verified against an official public purchased-course API contract or
an actual account. Mock tests validate implementation against fixtures, not the
provider's current behavior. Real playback, completeness and speed remain unknown.

Official Telegram documentation consulted: https://core.telegram.org/bots/api
getChatMember guarantees for other users require bot admin; can_post_messages is
needed for channel posting; webhook secret header/callback updates and command
registration are implemented. Final remote permission check cannot eliminate
permissions changing during an in-flight upload.

Official hosting limits consulted: https://render.com/docs/free
Free web services idle after 15 minutes, may cold-start slowly, have ephemeral
filesystems and monthly/shared usage limits; high outbound traffic can trigger
suspension. No always-on/free-forever guarantee or payment authorization is implied.

Next validation gate: a NEW bot identity, approved coaching AppX host and lawful
redacted account schemas; verify own entitled course listing, traversal, pagination,
unsupported encrypted data and permission revocation. Tokens stay in deployment
environment/private runtime memory, never in reference fixtures or committed files.
