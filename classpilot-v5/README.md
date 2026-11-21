# ClassPilot v5 — Streamlined professor workspace

This version simplifies the professor experience without changing the app's original identity or removing your syllabus, FAQ, section codes, analytics or documents.

## Start on Mac

1. Extract the ZIP. In Finder, open the **classpilot-v5** folder.
2. Open Terminal, type `cd ` (with a space), drag the **classpilot-v5** folder onto Terminal, and press Return.
3. Run:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python3 server.py
```

4. Open `http://127.0.0.1:8000`.

If port 8000 is occupied by an earlier ClassPilot version, close its Terminal window or run `PORT=8001 python3 server.py` and open `http://127.0.0.1:8001`.

## Pages

**Professor:** Overview, Sections, Course Knowledge (three tabs: Official Syllabus, Resources, FAQs), Office Hours, Students & Access (enrollments + join codes), Insights and Profile.

**Student:** My Sections, Course Assistant, Canvas & Tasks.

### Office hours

1. Select a section.
2. Select **By appointment** and save booking instructions or a scheduling URL, **or** select **Recurring hours**.
3. In recurring mode, select a weekday and add a time interval. Existing intervals show in a day agenda with delete controls. Overlapping times are rejected.
4. Official syllabus office-hour details remain visible, and the student section page also displays available information.

### Course Knowledge

An official printed Simple Syllabus PDF remains the authoritative primary reference. Use Course Knowledge → Official Syllabus → Import/Replace for that document. Other resources and FAQ answers have separate tabs. The bundled FINP 235 Section 598 example comes from the user-provided syllabus's extracted text and includes page references; it is for demonstration purposes only.

### Canvas

Only student pages show Canvas & Tasks. Students may store a **local browser shortcut** for each joined section and open its actual Canvas course. No Canvas API login, authorization, or live assignments/grades synchronization is implemented. The professor UI does not request or configure a Canvas link.

## Notes

The app uses SQLite (`classpilot.db`) for demo content and browser localStorage for display preferences and personal Canvas shortcuts. An existing database from v4 can be placed inside the `classpilot-v5` folder before starting, and the app will add the new office-hour settings table. Never copy sensitive real student data into this local prototype. No authentication, university identity verification, FERPA controls, or production access management are implemented yet.
