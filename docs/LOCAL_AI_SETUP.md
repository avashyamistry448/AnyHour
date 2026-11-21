# Local AI and grading accuracy

ClassPoint includes the original professor/student pages. The course assistant now uses **Ollama + Qwen3** locally instead of the paid OpenAI API.

## Windows setup

1. Install [Ollama](https://ollama.com/download/windows).
2. In a fresh Command Prompt:

   ```bat
   ollama pull qwen3:4b
   ```

3. In the project folder (the one containing `server.py`):

   ```bat
   python -m pip install -r requirements.txt
   python server.py
   ```

4. Open **http://127.0.0.1:8000** and upload a syllabus in the instructor's course knowledge page.

Ollama normally runs in the background on Windows. The server sends requests to `http://127.0.0.1:11434/api/chat` and uses `qwen3:4b`. To change the model, set `OLLAMA_MODEL`; to use an alternate local Ollama host, set `OLLAMA_URL`. **Do not expose Ollama or the ClassPoint demo API to the public internet.**

## Answer behavior

- For grading questions, the assistant looks for an **explicit row in the official syllabus grading-policy table** and returns the component's exact percentage and points, with a page citation. It will not guess a weight when the table is absent or unclear.
- Other questions rank relevant PDF pages and instructor materials, and send only selected excerpts to Qwen3 with instructions for concise, source-grounded answers.
- If Ollama is unavailable, the assistant says so briefly and cites matching sources instead of dumping PDF pages.
- Instructor-approved FAQs remain supported.
- The existing professor and student interface is unchanged.

### CHEM 107 regression fixture (illustrative sample)

On page 6 of the supplied CHEM 107 syllabus: Exam 1 = 200 points / 20%; Exam 2 = 200 points / 20%; Final Exam = 250 points / 25%.

Run tests from the repository root:

```bat
python -m unittest discover -s tests -v
```

No OpenAI API key or paid credits are required. Model outputs are not guaranteed accurate; verify important facts against original instructor materials.

## Scope and safeguards

The original app's access model is for local demonstration, **not production**: the UI role switch is not authentication, and endpoint authorization has not been hardened. Avoid real student records and private course data until login, instructor ownership, section enrollment enforcement, and student privacy protections are implemented.

The repository previously tracked SQLite databases and a `.venv` directory. The updated `.gitignore` prevents *new* untracked copies from being added; already tracked files require a separate coordinated cleanup and review before they can be removed safely.
