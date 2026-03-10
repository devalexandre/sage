# Privacy Policy — Sage

**Last updated:** 2026-03-09

## Overview

Sage is a personal knowledge widget that stores your notes and data **locally on your device**. Your privacy is fundamental to how Sage works.

## Data Collection

Sage does **not** collect, transmit, or share any personal data. Specifically:

- **No telemetry** — Sage does not send usage analytics or crash reports.
- **No user accounts** — Sage does not require registration or login.
- **No cloud storage** — All memories and documents are stored locally on your machine (`~/.sage/` directory).
- **No tracking** — Sage does not use cookies, advertising IDs, or fingerprinting.

## Data Stored Locally

Sage stores the following data exclusively on your device:

- **Memories** — Text entries you save, stored as encrypted vector embeddings in a local Milvus database.
- **Documents** — Files you import for knowledge search, indexed locally via Qdrant.
- **History** — A local SQLite log of your interactions.
- **Configuration** — Your settings (language, provider preferences), stored in a local config file.

All local data is under your full control. You can delete it at any time by removing the `~/.sage/` directory.

## Third-Party API Calls

When you configure an LLM provider (OpenAI, Ollama, LM Studio, or vLLM), Sage sends your queries to that provider's API to generate responses. These calls are made directly from your device to the provider. Sage does not proxy, log, or intercept these communications beyond what is needed to display the response.

Please refer to your chosen provider's privacy policy for how they handle API requests:

- **OpenAI**: https://openai.com/privacy
- **Ollama / LM Studio / vLLM**: Self-hosted — no external data transfer.

## Data Encryption

Memories stored in Sage are encrypted locally before being saved to disk. The encryption key is derived from your machine and is never transmitted.

## Children's Privacy

Sage does not knowingly collect data from children under 13. Since Sage does not collect any data at all, this is inherently satisfied.

## Changes to This Policy

If this policy changes, the updated version will be included in the application repository and release notes.

## Contact

If you have questions about this privacy policy, please open an issue at:
https://github.com/devalexandre/sage/issues
