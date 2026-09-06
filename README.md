# NOVA — AI Shopping & Agentic Commerce Assistant

> **An AI-powered, voice-first commerce agent** that discovers products, understands user intent, recommends intelligently, interacts with live shopping pages, manages a unified cart, and completes gated transactions through **Razorpay TEST Mode**.

[![Razorpay AI Buildathon](https://img.shields.io/badge/Razorpay_AI_Buildathon-Track_01:_AI_Growth_%26_Agentic_Commerce-blueviolet?style=for-the-badge)](https://github.com/Vidyadhar-pothula/NOVA---AI-Shopping-Assistant)
[![Live Demo](https://img.shields.io/badge/Live_App-Render-00E5FF?style=for-the-badge&logo=render)](https://nova-ai-shopping-assistant.onrender.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)

---

## 🌟 Overview

**NOVA** is an agentic AI shopping assistant designed around a simple idea:

> **Shopping should be conversational, intelligent, personalized, and actionable — not just a search box.**

Instead of forcing users to manually search, compare, open product pages, manage carts, and navigate multi-step checkout flows, NOVA allows them to interact naturally through text or voice.

### Conversational Instruction Examples
- 🎧 *"Find me three good wireless earbuds."*
- 💡 *"Which one do you recommend?"*
- 🛒 *"Add the second one to my cart."*
- 🔗 *"Show me something that pairs well with it."*
- 📋 *"What is in my cart?"*
- 🛍️ *"Add this product to my cart."*
- 💳 *"Checkout my cart."*
- ✅ *"Yes, proceed."*

The agent converts these conversational instructions into controlled application actions, while commerce-critical operations such as **product identity, cart state, spending validation, payment authorization, and payment verification remain deterministic**.

---

## 🎯 Razorpay AI Buildathon — Track 01

### **Track 01: AI Growth & Agentic Commerce**
The track focuses on **growing merchant revenue and making merchants sellable to AI buyers**.

NOVA addresses this through an agentic commerce pipeline that combines:
- 🔍 AI-powered product discovery
- 💬 Conversational shopping
- 🎯 Personalized recommendations
- 🛍️ Cross-sell and complementary product recommendations
- 🤖 Agent-readable product catalogs
- 🌐 Browser-based shopping assistance
- 🛒 Conversational cart management
- 🔐 Gated agentic checkout
- 💳 Razorpay TEST Mode payments
- ✅ Transaction verification
- 🧾 Auditability
- 🛡️ Failure-safe commerce operations

> **The goal is not merely to build a chatbot that talks about products.** NOVA is designed to actually perform the shopping workflow safely and reliably.

---

## 🧠 What is NOVA?

NOVA is a **custom agentic AI architecture** rather than a traditional chatbot.

The system seamlessly combines:
- **LLM reasoning** & intent understanding
- **Application-level tools** & persistent conversational context
- **Dynamic product discovery** & normalization
- **Canonical product identity** & authoritative cart management
- **Personalized recommendation logic**
- **Explicit purchase authorization** & expenditure validation
- **Razorpay TEST payment**, verification & order creation
- **SMTP Email confirmation** & audit logging

The **LLM is responsible for understanding user requests and selecting application actions**, while the **application enforces validation and executes commerce-critical operations**.

---

## 🏗️ High-Level Architecture

```
                  ┌─────────────────────────────────────────┐
                  │              USER INPUT                 │
                  │            (Text / Voice)               │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │               NOVA AGENT                │
                  │   Intent Understanding & Action Selection│
                  └────────────────────┬────────────────────┘
                                       │
                 ┌─────────────────────┴─────────────────────┐
                 │                                           │
                 ▼                                           ▼
   ┌───────────────────────────┐               ┌───────────────────────────┐
   │ Dynamic Commerce Sources  │               │   Authoritative Cart &    │
   │ & Product Discovery       │               │   Commerce State          │
   └─────────────┬─────────────┘               └─────────────┬─────────────┘
                 │                                           │
                 └─────────────────────┬─────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │          Gated Agentic Checkout         │
                  │        Explicit User Authorization      │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │       Razorpay TEST Mode Payment       │
                  │      Backend Payment Verification       │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │       Order Creation & SMTP Email       │
                  │            Audit Log Entry              │
                  └─────────────────────────────────────────┘
```

---

## 🧩 Core Design Principle

NOVA strictly separates **AI reasoning** from **commerce execution**.

```
                                 NOVA
                                  │
                       ┌──────────┴──────────┐
                       │                     │
                  AI Reasoning          Deterministic
                     Layer             Commerce Layer
                       │                     │
                Intent understanding     Product identity
                Conversation             Product validation
                Action selection         Cart state
                Context                  Spending rules
                Recommendations          Payment gate
                                         Payment verification
                                         Order creation
```

> **Why this matters:** An LLM should not be trusted to directly manufacture product IDs, prices, payment amounts, payment statuses, cart contents, or order verification results. Instead, NOVA resolves these values from authoritative application state.

---

## 🤖 Agent Architecture

NOVA utilizes a lightweight, custom agent orchestration system.

```
       ┌──────────────────────────┐
       │       User Prompt        │
       └────────────┬─────────────┘
                    │
                    ▼
       ┌──────────────────────────┐
       │   Agent Loop (FastAPI)   │
       └────────────┬─────────────┘
                    │
           ┌────────┴────────┐
           ▼                 ▼
   ┌───────────────┐ ┌───────────────┐
   │ Tool Selector │ │ Context State │
   └───────┬───────┘ └───────┬───────┘
           │                 │
           └────────┬────────┘
                    ▼
       ┌──────────────────────────┐
       │ Commerce Action Layer    │
       │ (Cart / Order / Gateway) │
       └──────────────────────────┘
```

### Why a Custom Agent Architecture?
NOVA does not depend on heavy third-party agent frameworks (e.g., LangChain, LangGraph, CrewAI) for core orchestration. This architectural decision provides tighter control over:
- Product identity & cart consistency
- Spending validation & payment authorization
- Payment verification & failure handling
- Full end-to-end auditability

The LLM is leveraged specifically where it adds the highest value: **Natural-language understanding, reasoning, contextual interpretation, and action selection.**

---

## 🛍️ Dynamic Product Discovery & Canonical Product Identity

NOVA does not rely on a static, hardcoded catalog. Product discovery dynamically queries live commerce sources and normalizes data into a standardized structure:

```
  Live Shopping Pages / APIs
             │
             ▼
    Product Normalization Engine
             │
             ▼
  Normalized Product Data Representation
  (ID, Name, Price, Brand, Stock, URLs, etc.)
             │
             ▼
  Canonical Product Identity Resolution
```

### 🔑 Canonical Product Identity

NOVA maintains a strict technical boundary:

$$\text{Product Name} \neq \text{Product ID} \neq \text{Product URL}$$

The LLM **never** invents canonical product IDs.

```
User Request ──► Search Results ──► Normalized Product ──► Canonical Product ID ──► Validated Product ──► Cart
```

This prevents common LLM commerce errors such as attempting `add_to_cart("Acer Aspire 5")` when the application layer expects a validated canonical product ID.

---

## 💬 Conversational Product References

NOVA intelligently resolves natural, ambiguous contextual references in conversation:

**Example Conversation:**
- **NOVA:** *"Here are three wireless earbuds: 1. Product A, 2. Product B, 3. Product C."*
- **USER:** *"Add the second one."*
- **NOVA:**
  - `Resolves "second one"` $\rightarrow$ `Finds Product B`
  - `Extracts Canonical Product ID` $\rightarrow$ `Validates Product B`
  - `Mutates Authoritative Cart` $\rightarrow$ `Confirms Item Added`

Supported references include:
- *"the second one"*, *"the cheaper one"*, *"the most expensive one"*
- *"that product"*, *"this one"*, *"the one from Amazon"*
- Direct product-name partial matches & pronouns

*Ambiguous references trigger a clarification request rather than guessing.*

---

## 🛒 Authoritative Shopping Cart & Extension

NOVA maintains a **single authoritative cart** across all user touchpoints.

```
                           ONE AUTHORITATIVE CART
                                     │
                 ┌───────────────────┼───────────────────┐
                 │                   │                   │
             Web Chat            Voice Mode       Browser Extension
```

### 🌐 Browser Extension Integration
When browsing an external shopping site:
1. User opens a live product page.
2. Extension extracts authorized on-page metadata.
3. Metadata is normalized and sent to the NOVA backend.
4. Canonical product identity is validated.
5. Item is added to the shared NOVA cart.

The extension does not maintain a shadow cart—it directly interfaces with the unified backend.

---

## 🔍 Catalogue Mode

Catalogue Mode demonstrates how NOVA converts unstructured shopping page data into structured, AI-readable commerce representations:

| Attribute | Description |
| :--- | :--- |
| **Product ID & Name** | Canonical identifier and full product title |
| **Merchant & Source** | Authorized seller and origin page |
| **Price & Currency** | Verified cost and currency code |
| **Availability & Stock** | Real-time stock status |
| **Exact URLs** | Direct link to original product listing |
| **Variants & Attributes** | Color, size, specifications, relationships |

---

## 🧠 Personalized Recommendations & Cross-Sell

NOVA leverages authorized purchase signals to recommend relevant items:
- Purchase frequency, recency, and brand preferences
- Frequently bought together items (e.g., *Laptop* $\rightarrow$ *Mouse / Bag*, *Tennis Racket* $\rightarrow$ *Overgrips / Balls*)
- Category relationship mapping

```
Current Shopping Context ──► Relationship Engine ──► Complementary Recommendations ──► Explainable Output
```

---

## 🎙️ Voice-First Interaction

Voice functions as a direct interface to the exact same agent engine as text chat:

```
                            NOVA Agent Engine
                                    ▲
                   ┌────────────────┴────────────────┐
                   │                                 │
              Text Input                        Voice Input
```

Supported voice actions include:
- *"Find wireless earbuds."*
- *"Add the second one."*
- *"Show me something compatible."*
- *"Checkout my cart."*
- *"Yes, proceed."*

---

## 💳 Agentic Checkout & Razorpay TEST Integration

Checkout is strictly gated. A conversational `"yes"` triggers a controlled sequence:

```
1. Explainable Summary  ──►  Show items, prices, sources, and total
2. Spending Validation  ──►  Verify existing expenditure bounds
3. Gated Confirmation   ──►  Ask "Ready to proceed?"
4. Razorpay Gateway     ──►  Open Razorpay TEST Mode Payment
5. Backend Verification ──►  Validate signature & transaction status
6. Order & Cart Action  ──►  Create order record & clear cart
```

```
               User Confirmation ("Yes, proceed")
                               │
                               ▼
                   Create Razorpay TEST Order
                               │
                               ▼
                    Razorpay TEST Checkout
                               │
                               ▼
                Backend Signature Verification
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
     Payment Verified                      Payment Failed
            │                                     │
   - Create Order Record                 - Retain Cart State
   - Clear Cart                          - Report Failure
   - Send SMTP Confirmation Email        - Prompt Retry
```

---

## 🛡️ Failure Handling & Safety Principles

1. **No False Success Reports:** If a tool call fails, NOVA transparently reports the failure.
2. **Payment Safety:** Payment status is solely determined by backend signature verification.
3. **Preserved Cart State:** If checkout is canceled or payment fails, cart items are preserved.
4. **No Unsanctioned Purchasing:** Purchases require explicit user interaction with Razorpay TEST mode.

---

## 📈 Merchant Revenue Growth Concept

NOVA enables revenue growth mechanisms designed for Track 01:

| Mechanism | Description |
| :--- | :--- |
| **Personalized Recommendations** | Tailored suggestions based on shopping patterns |
| **Cross-Sell & Upsell** | Suggesting complementary or higher-tier options |
| **AI-Readable Catalog** | Exposing structured data optimized for AI buyers |

### Revenue Metrics Matrix
- Average Order Value (AOV)
- Conversion Rate & Items Per Order
- Recommendation Acceptance Rate
- Revenue Per Session

---

## 📁 Project Structure

```
NOVA---AI-Shopping-Assistant/
├── backend/
│   ├── api/
│   │   └── main.py                # FastAPI server & route handlers
│   ├── commerce/
│   │   ├── service.py             # Core commerce business logic
│   │   ├── connectors/            # External commerce integrations
│   │   └── models.py              # Normalized product & cart schemas
│   ├── tools/
│   │   ├── action_tools.py        # Executable agent tools
│   │   └── discovery_tools.py     # Search & normalization tools
│   ├── agent/                     # Agent orchestrator & LLM interface
│   └── requirements.txt
├── extension/                     # Browser Extension
│   ├── manifest.json              # WebExtension Manifest V3
│   ├── content.js                 # On-page DOM parser & assistant overlay
│   ├── background.js              # Background service worker
│   └── popup.html / popup.js      # Extension popup UI
├── frontend/                      # Web UI (HTML5, Vanilla CSS, JS)
│   ├── index.html                 # Main SPA container
│   ├── css/                       # Dark JARVIS/EDITH futuristic styles
│   └── js/                        # Audio processing & API bindings
├── tests/                         # Automated test suite
│   ├── test_product_identity.py
│   ├── test_agent_flows.py
│   └── test_external_cart_bridge.py
├── render.yaml                    # Render deployment blueprint
├── requirements.txt               # Global Python dependencies
├── README.md                      # Project documentation
└── .gitignore
```

---

## 🧪 Testing & Verification Matrix

NOVA includes an extensive automated test suite for agentic commerce scenarios:

| Test ID | Scenario | Description |
| :---: | :--- | :--- |
| **A** | Product Discovery | Search products & add selected item |
| **B** | Relative Reference | Resolve "add the second one" to canonical product |
| **C** | Price Filtering | Select cheapest / most expensive item |
| **D** | URL Integrity | Preserve exact product URLs |
| **E** | Name-to-ID Resolution | Map name reference to internal ID |
| **F** | Listing Rejection | Prevent adding raw search/listing pages to cart |
| **G** | Invalid Product Guard | Safely reject fake / unvalidated product IDs |
| **H** | Ambiguity Handling | Prompt for clarification when matches are ambiguous |
| **I** | Cart Validation | Enforce authoritative backend cart state |
| **K** | Cart Sync | Synchronize state across Web UI, Voice, & Extension |
| **N** | Razorpay Verification | Verify payment signature and order state |

---

## 🔬 Step-by-Step Agent Interaction Flow

```
Step 1: Discovery      ──► USER: "Find me three good wireless earbuds."
                           NOVA searches live sources & normalizes products.

Step 2: Recommendation ──► USER: "Which one do you recommend?"
                           NOVA presents personalized recommendations.

Step 3: Reference Add  ──► USER: "Add the second one to my cart."
                           NOVA resolves reference -> validates ID -> updates cart.

Step 4: Cross-Sell     ──► USER: "Show me something that pairs well with it."
                           NOVA identifies complementary accessories.

Step 5: Cart Query     ──► USER: "What is in my cart?"
                           NOVA retrieves authoritative cart contents.

Step 6: Extension Add  ──► User visits external shop page -> clicks "Add to NOVA cart".
                           Extension extracts on-page data -> updates shared cart.

Step 7: Checkout       ──► USER: "Checkout my cart."
                           NOVA presents total & validates spending bounds.

Step 8: Confirmation   ──► USER: "Yes, proceed."
                           NOVA opens Razorpay TEST checkout interface.

Step 9: Payment & Verification ──► User completes TEST payment -> Backend verifies HMAC.

Step 10: Completion    ──► Order created -> Cart cleared -> Email sent -> Audit logged.
```

---

## 🖥️ Visual Design & User Interface

The interface features a dark futuristic visual theme inspired by **JARVIS / EDITH**:
- **Primary Palette:** Deep space navy `#0a0e1a`, glowing cyan `#00E5FF`, electric purple `#8A2BE2`, vibrant violet `#9400D3`.
- **UI Sections:**
  - 💬 **Interactive Chat & Voice Console**
  - 🛍️ **Product Discovery Grid**
  - 🔍 **Structured Catalogue Inspector Mode**
  - 🛒 **Unified Live Shopping Cart**
  - ⚙️ **Settings & Audit Trail Viewer**

---

## 🚀 Running Locally

### 1. Clone the Repository
```bash
git clone https://github.com/Vidyadhar-pothula/NOVA---AI-Shopping-Assistant.git
cd NOVA---AI-Shopping-Assistant
```

### 2. Setup Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file or export environment variables:
```env
RAZORPAY_KEY_ID=your_test_key_id
RAZORPAY_KEY_SECRET=your_test_key_secret

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=your_email@gmail.com

DEBUG=false
```

### 4. Start the Application
```bash
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```
Open [http://localhost:8000](http://localhost:8000) in your web browser.

---

## 🔌 Installing the Browser Extension

1. Open Chrome or Edge and navigate to `chrome://extensions`.
2. Enable **Developer mode** (top right toggle).
3. Click **Load unpacked**.
4. Select the `extension/` folder inside the project directory.
5. Open any supported shopping page to start interacting with NOVA.

---

## 🎯 Track 01 Requirement Mapping

| Track Requirement | NOVA Implementation Feature |
| :--- | :--- |
| **Grow Merchant Revenue** | Personalized recommendations, cross-sell, and upsell logic |
| **Sellable to AI Buyers** | Structured, AI-readable Catalogue Mode & normalization |
| **Conversational Commerce** | Multi-modal Voice + Text agent interface |
| **Agentic Shopping** | End-to-end execution: Discovery $\rightarrow$ Cart $\rightarrow$ Checkout |
| **Gated & Bounded Money** | Explicit confirmation gate, rule validation, Razorpay TEST Mode |
| **Failure Handling** | Retains cart on failure, transparent error reporting |
| **Auditability** | Full trace from user intent to payment verification |

---

## 📌 Project Philosophy

> **The AI should be intelligent enough to understand what the user wants, but the application should be deterministic enough to ensure money and commerce state remain 100% correct.**

---

## 👨‍💻 Project Information

- **Project:** NOVA — AI Shopping & Agentic Commerce Assistant
- **Hackathon:** Razorpay AI Buildathon — Track 01 (AI Growth & Agentic Commerce)
- **GitHub Repository:** [Vidyadhar-pothula/NOVA---AI-Shopping-Assistant](https://github.com/Vidyadhar-pothula/NOVA---AI-Shopping-Assistant)
- **Live Application:** [https://nova-ai-shopping-assistant.onrender.com](https://nova-ai-shopping-assistant.onrender.com)
