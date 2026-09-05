# NOVA - Personal AI Commerce Agent

This is the first prototype of NOVA, a Personal AI Commerce Agent.

## Run the local app

```bash
cd "/Users/vidyadhar/razorpay hackathon"
.venv/bin/python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000`.

## Voice assistant mode

The localhost app and browser extension both support voice mode.

In the localhost app:

1. Open `http://localhost:8000`.
2. Click Voice Mode in the header, or click the mic beside the chat send button.
3. Click Start Voice and allow microphone permission.
4. Say `hey nova` followed by your request.

NOVA submits the command into chat and speaks the response back.

## Browser extension

NOVA also includes a local browser extension in `extension/`. It injects a floating assistant on supported shopping websites and connects to the same local backend at `http://localhost:8000`.

To install in Chrome or Edge:

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Click Load unpacked.
4. Select `/Users/vidyadhar/razorpay hackathon/extension`.
5. Open or reload a supported shopping website.

Safari requires converting the same WebExtension folder into a Safari Web Extension wrapper with Xcode.
