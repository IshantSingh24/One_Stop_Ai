One Stop AI – Drive Sync, Slack Monitor, and RAG Notebook

## Overview

This repo contains three pieces that work together:

- Google Drive watcher (`drive.py`) – monitors a shared Drive and downloads new files into `knowledge_base/drive/` (supports Docs/Sheets/Slides export to docx/xlsx/pptx).
- Slack monitor (`simple_slack_monitor.py`) – polls Slack channels, logs messages, and downloads supported attachments into `knowledge_base/slack/`.
- RAG demo notebook (`day4.ipynb`) – builds a Chroma vector DB from files in `knowledge_base/` and serves a simple Gradio chat over the knowledge base.

## Prerequisites

- Python 3.12
- A virtual environment (.venv) recommended
- Access tokens/credentials:
	- Google Cloud service account JSON as `credentials.json` (Drive API enabled; target folders/files shared with the service account email)
	- Slack Bot token with basic permissions, stored in `config.json`

## Quick start

1) Create and activate a venv

```zsh
python3 -m venv .venv
source .venv/bin/activate
```

2) Install dependencies

```zsh
pip install -r requirements.txt
```

If you don’t want to use requirements.txt, the critical packages are:
- google-api-python-client, google-auth, google-auth-httplib2, google-auth-oauthlib, httplib2
- slack_sdk, requests
- watchdog (for the notebook’s file watcher), gradio, langchain, langchain-openai, langchain-community, chromadb, python-dotenv, python-docx, python-pptx

3) Provide credentials and config

- `credentials.json` (Google service account key) in the repo root.
- `config.json` for Slack, e.g.:

```json
{
	"slack": {
		"bot_token": "xoxb-your-token",
		"target_channel": ["C0123456789"]
	},
	"output": {"json_file": "knowledge_base/slack/events.json"},
	"monitoring": {"poll_interval": 30}
}
```

Ensure folders exist:

```zsh
mkdir -p knowledge_base/drive knowledge_base/slack vector_db
```

## Google Drive watcher (drive.py)

What it does
- Authenticates with the service account in `credentials.json`.
- Lists recent files and then polls every 30s.
- Downloads new files to `knowledge_base/drive/`.
- Exports Google Docs/Sheets/Slides to docx/xlsx/pptx automatically.

Run it

```zsh
python3 drive.py
```

Troubleshooting
- ModuleNotFoundError for googleapiclient → install `google-api-python-client` (already covered by requirements.txt).
- Permission errors or no files found → share the Drive folder/file with the service account email.

## Slack monitor (simple_slack_monitor.py)

What it does
- Loads `config.json` and connects with the Slack Bot token.
- Polls configured channels at `poll_interval` seconds.
- Logs events to JSON and downloads supported files (.txt, .pdf, .docx, .json, .md, .csv, .xlsx, .pptx) into `knowledge_base/slack/`.

Run it

```zsh
python3 simple_slack_monitor.py
```

Troubleshooting
- Invalid auth → verify the bot token and that the bot is a member of target channels.
- File downloads failing → ensure the file is within size/extension limits and the bot can access it.

## RAG Notebook (day4.ipynb)

What it does
- Loads files from `knowledge_base/` (txt, md, json, docx, pptx) and creates LangChain `Document`s.
- Splits text into chunks and persists a Chroma DB in `vector_db/`.
- Uses OpenAI embeddings (or swap in sentence-transformers) and serves a Gradio chat interface.

Before running
- Set your OpenAI API key in environment or .env (the notebook reads it via `python-dotenv`):

```zsh
echo "OPENAI_API_KEY=sk-..." > .env
```

Run it
- Open `day4.ipynb` in VS Code/Jupyter, execute cells from top to bottom.
- The notebook will install any missing libs (python-docx, python-pptx, gradio, watchdog) as needed.

Notes
- The notebook starts a file watcher that updates the vector store when new files land in `knowledge_base/`.
- Collection name defaults to `insurellm_docs`; DB folder is `vector_db/`.

## Project structure

```
knowledge_base/
	drive/        # Google Drive downloads
	slack/        # Slack downloads and logs
vector_db/      # Chroma persistence
drive.py        # Google Drive watcher
simple_slack_monitor.py  # Slack polling/downloader
day4.ipynb      # RAG builder + Gradio chat
config.json     # Slack config (you create this)
credentials.json# Google service account key (you provide)
requirements.txt
```

## Common issues

- Using the wrong pip package name for the Drive client
	- Correct: `google-api-python-client`. Incorrect: `googleapiclient`.
- Service account can’t see files
	- Share Drive items with the service account email.
- OpenAI key not loaded in the notebook
	- Ensure `.env` has `OPENAI_API_KEY` or export it in your shell.

## License

MIT (or your preferred license)

