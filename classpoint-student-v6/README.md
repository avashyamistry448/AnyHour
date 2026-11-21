# anyhour v6 — Student Workspace & Canvas

This is a standalone local anyhour demo with the **v5 professor workspace preserved** and a more complete student experience. Canvas remains the official LMS; anyhour is a professor-grounded student support resource.

## Quick start (Mac)

1. Open Terminal in this **classpoint-student-v6** folder. The root repository also has older v5 files, so make sure you're in this folder.
2. Run:

```bash
bash start-mac.sh
```

3. Open **http://127.0.0.1:8000** and leave Terminal open. If port 8000 is already occupied, stop the old server (Control+C), or use `PORT=8001 bash start-mac.sh` and visit port 8001.

The script creates a local Python environment, installs `requirements.txt`, and starts `server.py`. Data is stored in an ignored local `classpilot.db`, not in Git.

## Student pages

- **Dashboard:** Joined sections and shortcuts to professor-approved content and Canvas.
- **My Sections:** Join with professor-issued codes, then read the official syllabus summary, FAQs, resources, and office hours for each section.
- **Course Assistant:** Ask syllabus, assignment, and course-policy questions using the professor's section-specific materials.
- **Canvas & Tasks:** Optional student-controlled, **read-only** Canvas OAuth integration to view Canvas courses, published assignments, due dates, and original Canvas links. Match a Canvas course to a anyhour section to ground deadline questions.

The professor's existing Sections, Course Knowledge, Office Hours, Students & Access, Insights, and Profile pages remain in place.

## Configuring Canvas OAuth (optional)

**Institutional administrator approval is required.** Canvas is not connected automatically. Without credentials, the page correctly displays an unconfigured status while non-Canvas anyhour features still work.

1. Ask your Canvas administrator for a developer key and authorized read-only scopes.
2. Copy `canvas.env.example` to `canvas.env`, and enter your institution's HTTPS Canvas domain, OAuth client ID, and client secret **on your own computer**.
3. Register the exact callback `http://127.0.0.1:8000/api/canvas/callback` with Canvas (or override `CANVAS_REDIRECT_URI` to the authorized callback). Production uses HTTPS.
4. Restart the local app. On **Student → Canvas & Tasks**, click **Connect with Canvas** and authorize in Canvas.

The connector can request your permitted Canvas courses and assignments, follow pagination, and refresh tokens. Tokens are stored in server memory associated with a browser cookie and cleared on disconnect or server restart. Don't commit `canvas.env` or share secrets.

## Development checks

```bash
python3 -m unittest discover -s tests
python3 -m py_compile server.py canvas_api.py
node --check app.js
```

## Important demo limitations

This local prototype is **not production secure**. It has no verified user logins, instructor authorization, identity verification, or FERPA-ready access controls. Do not expose it publicly or add sensitive student records. Role switching, join codes, and demo activity are not substitutes for real authentication. The professor's official Simple Syllabus is prioritized for academic policy; Canvas remains authoritative for assignments, deadlines, submissions, and grades. Canvas integration is configured in code but has not been tested with university OAuth credentials. Grades and submissions are not fetched.

[Canvas OAuth documentation](https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth.md)
