# NOVA Shopping Assistant Extension

This is a local browser extension for NOVA. It injects a floating assistant into supported shopping websites and sends page-aware chat messages to the existing NOVA backend at `http://localhost:8000`.

## Run

1. Start the NOVA backend:

   ```bash
   cd "/Users/vidyadhar/razorpay hackathon"
   .venv/bin/python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
   ```

2. Open Chrome or Edge and go to `chrome://extensions`.
3. Enable Developer mode.
4. Click Load unpacked.
5. Select this folder:

   ```text
   /Users/vidyadhar/razorpay hackathon/extension
   ```

6. Open a shopping website. The NOVA button appears at the bottom-right when the page looks commerce-related.

After code changes, click the reload icon on the NOVA extension card inside `chrome://extensions`, then reload the shopping page.

## What it can do on shopping pages

- If you ask for the best or top products from the current page, NOVA reads product cards from that page and ranks those results only.
- If you ask it to search for something from a store homepage or category page, NOVA uses that website's own search box and opens that store's results page.
- If a question is not page-specific, NOVA falls back to the local chat backend.

## Voice

1. Open the NOVA panel on a shopping page.
2. Click Voice.
3. Allow microphone permission if Chrome asks.
4. Say `hey nova` followed by your request, for example:

   ```text
   hey nova show top 5 best bottles from this page
   ```

NOVA will run the command and speak the reply. Chrome requires a page-level mic permission, so this is active while the shopping page is open rather than a hidden system-wide wake word.

## Notes

- This is a Chrome/Edge Manifest V3 extension.
- Safari support needs a Safari Web Extension wrapper through Xcode.
- The extension uses the same local backend, chat agent, cart, and payment flow as the main NOVA app.
