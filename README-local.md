# Match 4 agent — laptop version

This is a copy of checkpoint 5. Its web retrieval, search-form navigation, table handling,
evidence checks and test pages are preserved. Only the model backend has changed:
`decision.py` now calls an online model through your approved ChatGPT Plus connection.
Your laptop does **not** download Qwen, PyTorch, or ROCm. Internet access is required
for sign-in, model inference and public websites.

## Set up on Windows (PowerShell)

1. Extract this ZIP and open PowerShell **inside** the `match4-agent-local` folder.
2. Create an isolated Python environment and install the small dependencies:

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

   Before connecting, run the offline check (no login or plan usage):

   ```powershell
   .\.venv\Scripts\python.exe local_selfcheck.py
   ``` 

3. Connect your **personal Plus account** in your browser:

   ```powershell
   .\.venv\Scripts\python.exe local_agent.py login
   ```

   Approve ChatGPT plan usage when the sign-in page offers it. The agent does not
   ask for your password or an API key. If you have both personal and Business
   workspaces, select the personal Plus account. Your browser must run on the
   same laptop because sign-in returns to `127.0.0.1`.

4. See the models available to this signed-in account:

   ```powershell
   .\.venv\Scripts\python.exe local_agent.py models
   ```

   Copy a `slug` from the **left** column; model access varies by account.
   The following commands use `YOUR_MODEL_SLUG` as a placeholder.

5. Run one local example before spending your plan usage on the full checks:

   ```powershell
   .\.venv\Scripts\python.exe local_agent.py smoke --model YOUR_MODEL_SLUG
   ```

6. Ask about a website:

   ```powershell
   .\.venv\Scripts\python.exe local_agent.py ask "https://www.w3.org/about/" "In what year did Tim Berners-Lee invent the World Wide Web?" --model YOUR_MODEL_SLUG
   ```

7. Optionally rerun all archived synthetic checks (12 scenarios, multiple model
   calls per scenario):

   ```powershell
   .\.venv\Scripts\python.exe local_agent.py checks --model YOUR_MODEL_SLUG
   ```

Results may differ from the checkpoint's Qwen results; always verify on this
backend. The sign-in flow and real model requests cannot be completed until
you approve sign-in locally.

## Where each part runs

| Component | Location |
| --- | --- |
| `retrieval.py`, `tables.py`, `forms.py` | Your laptop |
| `agent.py`, `evidence.py`, `validation.py` | Your laptop |
| `decision.py` | Your laptop, sends prompts to the online model |
| Model inference | OpenAI, using approved ChatGPT plan usage |

The local sign-in stores tokens in your user profile under
`%LOCALAPPDATA%\match4-agent-local\chatgpt-connection.json` on Windows.
Never upload that file. It is **outside** this project ZIP. Use
[ChatGPT Settings → Usage](https://chatgpt.com/#settings/usage) to review
connected-app limits. Sign-in usage shares your Plus allowance; it is
different from separately billed API-key access.

The sign-in method follows OpenAI's documented
[local open-source integration](https://developers.openai.com/siwc/token-sharing-open-source/sign-in).
Model requests use the documented
[OAuth Responses API contract](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)
with `store=false` and `stream=true`. This version is meant for your own
local use. The competition submission contract has not yet been confirmed,
so keep the AMD notebook version as your competition baseline.

## If sign-in or an answer fails

- Account has no plan permission: sign in again using personal Plus and approve plan use.
- Session expired: run `login` again; normal access-token refresh happens automatically.
- Model unavailable: run `models` and choose a listed slug.
- Output differs from the old checkpoint: run `smoke`, then `checks`;
  models can interpret the same page differently.
- Browser callback times out: confirm that browser and PowerShell run on the
  same computer, then repeat `login`.



