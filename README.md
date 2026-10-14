# Apex test site: Decap CMS trial (FICTIONAL business)

An isolated test repository for Apex Creative Studio's client-editing trial. **Not a client site**, and separate from Apex's internal repository. All content is fictional; photos are generated placeholders.

- `content/`: what the client can edit through `/admin/` (business info + uploaded photos)
- `templates/`, `build.py`, `netlify.toml`, `admin/`: Apex-only (layout, build, host, editor config)
- Build: `python build.py` → `site/` (Python + PyYAML from `requirements.txt`). Invalid content or a broken editor config stops the build; the host keeps the last good deploy.

Trial plan and results live in the Apex repository: `tests/2026-09-30-editor-trial/` (local stage) and `tests/2026-10-decap-live/` (this stage).
