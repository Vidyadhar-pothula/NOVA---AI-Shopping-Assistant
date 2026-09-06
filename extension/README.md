🚀 NOVA — AI Shopping & Agentic Commerce Assistant
An AI-powered, voice-first commerce agent that discovers products, understands user intent, recommends intelligently, interacts with live shopping pages, manages a unified cart, and completes gated transactions through Razorpay TEST Mode.
NOVA is an agentic AI shopping assistant designed around a simple idea:
Shopping should be conversational, intelligent, personalized, and actionable — not just a search box.
Instead of forcing users to manually search, compare, open product pages, manage carts, and navigate checkout flows, NOVA allows them to interact naturally through text or voice.
NOVA can understand requests such as:

"Find me three good wireless earbuds."

"Which one do you recommend?"

"Add the second one to my cart."

"Show me something that pairs well with it."

"What is in my cart?"

"Add this product to my cart."

"Checkout my cart."

"Yes, proceed."
The agent converts these conversational instructions into controlled application actions, while commerce-critical operations such as product identity, cart state, spending validation, payment authorization, and payment verification remain deterministic.
🎯 Razorpay AI Buildathon — Track 01
AI Growth & Agentic Commerce
NOVA is designed for Track 01: AI Growth & Agentic Commerce.
The track focuses on:

Growing merchant revenue and making merchants sellable to AI buyers.
NOVA addresses this through an agentic commerce pipeline that combines:
AI-powered product discovery
Conversational shopping
Personalized recommendations
Cross-sell and complementary product recommendations
Agent-readable product catalogs
Browser-based shopping assistance
Conversational cart management
Gated agentic checkout
Razorpay TEST Mode payments
Transaction verification
Auditability
Failure-safe commerce operations
The goal is not merely to build a chatbot that talks about products.
NOVA is designed to actually perform the shopping workflow.

🧠 What is NOVA?
NOVA is a custom agentic AI architecture rather than a traditional chatbot.
The system combines:

LLM reasoning
Intent understanding
Application-level tools
Persistent conversational context
Dynamic product discovery
Product normalization
Canonical product identity
Authoritative cart management
Personalized recommendation logic
Explicit purchase authorization
Expenditure validation
Razorpay TEST payment
Payment verification
Order creation
Email confirmation
Audit logging
The LLM is responsible for understanding what the user wants and deciding which application action is appropriate.
The application itself remains responsible for validating and executing commerce-critical operations.

🏗️ High-Level Architecture



🔄 Complete Agentic Commerce Flow



🧩 Core Design Principle
NOVA separates AI reasoning from commerce execution.
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
 Recommendations         Payment gate
                          Payment verification
                          Order creation
This is important because an LLM should not be trusted to directly manufacture:
Product IDs
Prices
Payment amounts
Payment status
Cart contents
Order success
Transaction verification
Instead, NOVA resolves these values from authoritative application state.
🤖 Agent Architecture
NOVA uses a custom agent architecture.



Why a custom agent architecture?
NOVA does not depend on LangChain, LangGraph, CrewAI, or another agent framework for its core orchestration.
This was an intentional architectural decision.

The objective is to demonstrate agentic commerce, not to demonstrate a particular agent framework.

A lightweight custom architecture provides tighter control over:

Product identity
Cart consistency
Spending validation
Payment authorization
Payment verification
Failure handling
Auditability
The LLM is used where it provides the most value:
Natural-language understanding, reasoning, contextual interpretation, and action selection.
🛍️ Dynamic Product Discovery
NOVA does not depend on a hardcoded product catalog.
Product discovery is designed around dynamically available commerce sources.




Each discovered product is normalized into a common product representation containing information such as:
product_id
name
brand
category
description
price
currency
availability
stock
rating
merchant
source
exact_product_url
image
variants
attributes
This allows NOVA to work with products from different sources without coupling the rest of the application to a specific marketplace.
🔑 Canonical Product Identity
One of the most important parts of NOVA is maintaining a strict distinction between:
Product Name
        ≠
Product ID
        ≠
Product URL
The LLM never invents canonical product IDs.
Instead:

User Request
     ↓
Search Results
     ↓
Normalized Product
     ↓
Canonical Product ID
     ↓
Validated Product
     ↓
Cart
This prevents errors such as:
add_to_cart("Acer Aspire 5")
when the actual application expects a canonical internal product ID.
💬 Conversational Product References
NOVA understands contextual references.
For example:

NOVA:
Here are three products.

1. Product A
2. Product B
3. Product C

USER:
Add the second one.

NOVA:
→ Resolves "second one"
→ Finds Product B
→ Uses Product B's canonical ID
→ Validates Product B
→ Adds Product B to cart
The system supports references such as:
"the second one"
"the cheaper one"
"the expensive one"
"that product"
"this one"
"the one from Amazon"
product-name references
contextual pronouns
Ambiguous references are not guessed.
NOVA can request clarification when multiple products match.

🛒 Authoritative Shopping Cart
NOVA maintains a single authoritative cart.



This prevents the following situation:
Frontend Cart
      ≠
Agent Cart
      ≠
Extension Cart
Instead:
             ONE CART
                │
      ┌─────────┼─────────┐
      │         │         │
    Chat      Voice   Extension
Every interface reads and modifies the same underlying cart state.
🌐 Browser Extension
NOVA can operate alongside an existing shopping website.
The browser extension allows NOVA to understand the currently authorized shopping page.

Example:

User opens a product page
          ↓
NOVA Extension
          ↓
Extract current product information
          ↓
Normalize product
          ↓
Validate product
          ↓
Create / resolve canonical product
          ↓
Add to shared NOVA cart
The extension does not maintain a separate shadow cart.
It communicates with the same backend used by the main NOVA application.

🔗 Exact Product URLs
NOVA preserves exact product URLs.
A product card must correspond to the actual product page represented by that card.

The system avoids treating:

/search
/category
/browse
/listing
pages as individual products.
A listing page cannot simply become a cart item.

This prevents situations where the UI displays one product while the cart actually contains a generic marketplace search result.

🔍 Catalogue Mode
NOVA includes Catalogue Mode to demonstrate how an AI agent can consume structured commerce information.



Catalogue Mode can expose information such as:
Source
Merchant
Page URL
Page Type
Product Name
Product ID
Brand
Category
Description
Price
Currency
Availability
Stock
Exact Product URL
Image
Variants
Attributes
Relationships
The purpose is to make it visible that NOVA is not simply reading arbitrary page text.
It converts commerce information into a structured representation that the agent can reason over.

🧠 Personalized Recommendations
NOVA can use authorized shopping history to make recommendations.
Personalization is based on actual available information rather than invented assumptions.

Potential signals include:

Previous purchases
Purchase frequency
Purchase recency
Frequently purchased categories
Frequently purchased brands
Frequently purchased products
Products purchased together
Current product
Current cart
Current shopping context
Product relationships
Availability
For example:
User frequently purchases:

Tennis Rackets
Overgrips
Tennis Balls
When the user buys a racket, NOVA can prioritize relevant complementary products.
The same architecture works for:

Laptop → Mouse / Keyboard / Bag

Camera → Memory Card / Battery / Tripod

Coffee Machine → Coffee Beans / Filters

Running Shoes → Socks / Insoles

Headphones → Case / Adapter
The recommendation engine is therefore relationship-driven, rather than hardcoded around a particular product category.
🔄 Recommendation & Cross-Sell Flow



NOVA can explain recommendations using evidence such as:
"You frequently purchase this type of accessory with similar products."
The system should not invent a reason that does not exist in the available data.
🎙️ Voice-First Interaction
Voice is treated as another interface to the same agent.
                  NOVA Agent
                      ▲
             ┌────────┴────────┐
             │                 │
          Text Input       Voice Input
Voice can perform application actions such as:
"Switch to Discover."

"Go back home."

"Open my orders."

"Find wireless earbuds."

"Add the second one."

"Show me something compatible."

"Open that product."

"Add this to my cart."

"Checkout my cart."
Voice and text do not use separate commerce logic.
Both ultimately call the same application-level action layer.

💳 Agentic Checkout
Checkout is deliberately gated.
NOVA does not treat a conversational "yes" as proof that a payment succeeded.

The intended flow is:




🔐 Payment Safety
Commerce actions are separated into stages.
1. Explainable
NOVA should be able to show:
What is being purchased?
From which source?
At what price?
What is the total?
Why is the action being taken?
2. Bounded
Existing application spending rules are evaluated before payment.
NOVA does not arbitrarily create new limits during runtime.

3. Gated
Payment requires explicit user authorization.
NOVA:
Your cart total is ₹XX,XXX.
Ready to proceed?

USER:
Yes, proceed.

→ Razorpay TEST checkout opens
4. Verified
The application verifies the Razorpay payment before considering the transaction successful.
💰 Razorpay TEST Mode
NOVA integrates with Razorpay TEST Mode for the hackathon demonstration.
The payment flow is:

NOVA
 ↓
Prepare Checkout
 ↓
Explicit User Confirmation
 ↓
Create Razorpay TEST Order
 ↓
Razorpay TEST Checkout
 ↓
Payment
 ↓
Backend Verification
 ↓
Order Creation
 ↓
Cart Clearing
The cart is cleared only after successful payment verification.
A failed or cancelled payment should preserve the cart.

📧 Email Confirmation
After a successfully verified transaction, NOVA can send a confirmation email through SMTP.
Verified Payment
       ↓
Order Created
       ↓
SMTP Email Service
       ↓
Customer Confirmation
The email can contain:
Order information
Purchased products
Verified transaction information
Amount
Confirmation details
Email delivery is treated separately from payment verification.
A payment should never be reported as successful simply because an email operation succeeded.

🧾 Audit Trail
Commerce actions are auditable.
The intended transaction history is:

User Intent
     ↓
Product Discovery
     ↓
Product Selection
     ↓
Recommendation
     ↓
Cart Mutation
     ↓
Checkout Preparation
     ↓
Confirmation
     ↓
Razorpay Order
     ↓
Payment Result
     ↓
Verification
     ↓
Order
     ↓
Email
This provides an explainable trail for commerce-critical actions.
🛡️ Failure Handling
A core design principle is:
Never claim success when the underlying operation failed.
For example:
Failed cart operation
Tool:
Add to cart → FAILED

NOVA:
I couldn't add that product to your cart.
Not:
❌ I've successfully added it.
Failed payment
Razorpay TEST payment
        ↓
Payment failed / cancelled
        ↓
Order NOT created
        ↓
Cart preserved
        ↓
NOVA reports failure
Invalid product
Invalid product ID
        ↓
Validation failure
        ↓
No cart mutation
This keeps the conversational state aligned with actual application state.
🏪 Merchant Revenue Growth
NOVA is not limited to simply helping customers find products.
The architecture enables revenue-growth mechanisms such as:

Personalized recommendations
Products can be recommended based on customer behavior.
Cross-sell
Complementary products can be presented during shopping.
Upsell
Higher-value relevant alternatives can be presented when appropriate.
Contextual recommendations
The current product, cart, or browsing context can influence recommendations.
AI-readable catalog
Products can be represented in a structured format that an AI agent can consume.
The objective is to make the merchant's catalog more accessible to AI-driven buyers.

📈 Revenue Measurement Concept
The system can compare:
Baseline Shopping
       VS
AI-Assisted Shopping
Useful metrics include:
Average Order Value
Conversion Rate
Items Per Order
Cross-Sell Rate
Recommendation Acceptance
Revenue Per Session
The goal is to demonstrate measurable incremental value from agent-assisted commerce rather than simply claiming that AI increases revenue.
🧱 System Architecture



📁 Project Structure
NOVA---AI-Shopping-Assistant/
│
├── backend/
│   ├── api/
│   │   └── main.py
│   │
│   ├── commerce/
│   │   ├── service.py
│   │   └── ...
│   │
│   ├── ...
│   │
│   └── requirements.txt
│
├── extension/
│   ├── manifest.json
│   ├── content.js
│   ├── popup.js
│   └── ...
│
├── frontend/
│   ├── ...
│   └── ...
│
├── tests/
│   ├── test_product_identity.py
│   ├── test_agent_flows.py
│   ├── test_external_cart_bridge.py
│   └── ...
│
├── _e2e_test.py
├── _patch_agent.py
├── _repro.py
├── _run_full_e2e_matrix.py
├── _smtp_diag.py
├── _verify_stabilization.py
├── _verify_wrapper_fix.py
│
├── requirements.txt
├── render.yaml
├── README.md
└── .gitignore
🔌 Major Components
1. NOVA Agent
Responsible for:
Understanding user requests
Maintaining conversational context
Selecting application actions
Resolving conversational references
Coordinating commerce workflows
2. Product Discovery
Responsible for:
Searching available commerce sources
Normalizing products
Validating product information
Deduplicating results
Ranking products
Preserving exact product URLs
3. Recommendation Engine
Responsible for:
Product recommendations
Complementary products
Cross-sell opportunities
Personalized recommendations
Purchase-pattern analysis
4. Catalog Layer
Responsible for transforming raw shopping-page information into structured, AI-readable product data.
5. Cart Service
Responsible for:
Canonical product validation
Quantity
Cart state
Price integrity
Persistent cart state
Cart synchronization across interfaces
6. Checkout Service
Responsible for:
Reading authoritative cart state
Calculating checkout amount
Applying existing expenditure rules
Explicit confirmation
Razorpay order preparation
Payment verification
Order creation
7. Browser Extension
Responsible for:
Reading authorized shopping-page context
Extracting product information
Connecting page products to NOVA
Sharing the same backend cart
Providing agent assistance while browsing
8. Email Service
Responsible for sending transactional confirmation emails after verified orders.
9. Audit Service
Responsible for recording important commerce events.
🧪 Testing
NOVA includes automated tests covering the major agentic commerce paths.
Representative scenarios include:

Test	Description
A	Search → Add selected product
B	Multiple products → Add second product
C	Select cheaper product
D	Open exact product URL
E	Product-name reference → Canonical product
F	Browse/listing result rejected from cart
G	Invalid product ID safely rejected
H	Ambiguous product names require clarification
I	Authoritative cart validation
K	Cart synchronization
L	Cart state verification
N	Razorpay TEST order/payment verification
Additional end-to-end validation covers:
Product discovery
Product normalization
Product identity
Conversational references
Cart operations
Checkout gating
Payment verification
Failure handling
Audit logging
🔬 Example Agent Interaction
Step 1 — Discovery
USER:
Find me three good wireless earbuds.
NOVA dynamically searches available commerce sources and returns normalized products.
Step 2 — Recommendation
USER:
Which one do you recommend?
NOVA evaluates the available products and provides an explanation.
Step 3 — Conversational Selection
USER:
Add the second one to my cart.
NOVA resolves:
"second one"
      ↓
Product Context
      ↓
Canonical Product ID
      ↓
Validation
      ↓
Cart
Step 4 — Cross-Sell
USER:
Show me something that would pair well with it.
NOVA uses product relationships and available commerce information to recommend complementary products.
Step 5 — Cart
USER:
What's in my cart?
NOVA retrieves the authoritative cart.
Step 6 — Catalogue Mode
The user opens Catalogue Mode to inspect how products are represented for AI consumption.
Step 7 — Browser Shopping
The user opens an external shopping page and asks:
USER:
Add this to my cart.
The extension extracts the authorized current-page product and sends it through the same product normalization and cart pipeline.
Step 8 — Checkout
USER:
Checkout my cart.
NOVA shows the checkout summary and validates the applicable purchase rules.
Step 9 — Explicit Confirmation
NOVA:
Your cart total is ₹XX,XXX.
Would you like to proceed?

USER:
Yes, proceed.
Step 10 — Razorpay
Razorpay TEST checkout opens.
The user completes the test payment.

Step 11 — Verification
The backend verifies the payment before creating the order.
Step 12 — Completion
Only after successful verification:
Payment verified
      ↓
Order created
      ↓
Cart cleared
      ↓
Email sent
      ↓
Audit recorded
🖥️ User Interfaces
NOVA provides a unified interface containing:
Chat
Discover
Settings
Catalogue Mode
Voice Mode
Shopping Cart
Agent Console
The interface is designed around a dark futuristic visual language inspired by AI assistants such as JARVIS / EDITH.
The primary visual palette uses dark blue, purple, and violet tones.

🌐 Deployment Architecture
The deployed architecture uses a single backend serving the NOVA web application and APIs.



Current deployment:
Repository:
Vidyadhar-pothula/NOVA---AI-Shopping-Assistant

Backend:
https://nova-ai-shopping-assistant.onrender.com

Platform:
Render

Runtime:
Python / FastAPI

Deployment:
Render Web Service
The browser extension communicates with the deployed backend rather than a local development server.
🚀 Running Locally
Clone the repository:
git clone https://github.com/Vidyadhar-pothula/NOVA---AI-Shopping-Assistant.git
cd NOVA---AI-Shopping-Assistant
Create a virtual environment:
python3 -m venv .venv
source .venv/bin/activate
Install dependencies:
pip install -r requirements.txt
Start the backend:
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
Then open the local NOVA application in the browser.
🔐 Environment Configuration
Secrets should be supplied through environment variables and must not be committed to GitHub.
Example configuration:

RAZORPAY_KEY_ID
RAZORPAY_KEY_SECRET

SMTP_HOST
SMTP_PORT
SMTP_USER
SMTP_PASSWORD
SMTP_FROM

DEBUG
Example:
RAZORPAY_KEY_ID=your_test_key
RAZORPAY_KEY_SECRET=your_test_secret

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email
SMTP_PASSWORD=your_app_password
SMTP_FROM=your_email

DEBUG=false
Never expose:
API secrets
Payment secrets
SMTP passwords
App passwords
Private keys
Session credentials
🔒 Security Principles
NOVA follows several important security principles:
No fabricated product identity
The LLM cannot manufacture canonical product IDs.
No fabricated payment success
Payment success is determined by backend verification.
No automatic purchase without authorization
Checkout requires explicit user confirmation.
No arbitrary spending limits
Existing application spending rules are respected rather than inventing new hardcoded limits.
No cart mutation from invalid listings
Search/category/listing pages cannot automatically become individual cart products.
No credential extraction
The browser extension does not attempt to bypass authentication, CAPTCHA, cookies, passwords, or payment credentials.
No false success messages
Application state is authoritative.
📊 Agentic Commerce Safety Model
             USER INTENT
                  ↓
          AI INTERPRETATION
                  ↓
          APPLICATION ACTION
                  ↓
             VALIDATION
                  ↓
          AUTHORITATIVE STATE
                  ↓
       EXPLICIT PURCHASE GATE
                  ↓
          RAZORPAY TEST
                  ↓
         PAYMENT VERIFICATION
                  ↓
              ORDER
The LLM can reason about the action.
The application decides whether the action is valid and executable.

🧠 Why NOVA is Agentic
A traditional chatbot might do this:
User
 ↓
Question
 ↓
Text Response
NOVA instead follows:
User
 ↓
Intent
 ↓
Reasoning
 ↓
Tool / Application Action
 ↓
State Change
 ↓
Verification
 ↓
Next Action
For example:
"Add the second one."

        ↓

Resolve conversational reference

        ↓

Identify canonical product

        ↓

Validate product

        ↓

Mutate authoritative cart

        ↓

Return actual cart state
That is the difference between AI-generated text and agentic execution.
🏆 Key Differentiators
1. Conversational Commerce
Users interact naturally instead of navigating a traditional shopping workflow.
2. Voice Agent
The same agent can execute shopping actions through voice.
3. Browser Agent
NOVA can operate alongside external shopping pages.
4. AI-Readable Catalog
Commerce information is normalized into structured representations for AI consumption.
5. Contextual Product Resolution
Users can say:
"the second one"
instead of repeatedly naming products.
6. Personalized Shopping
Recommendations can use authorized purchase history and product relationships.
7. Cross-Sell
NOVA can dynamically identify complementary products.
8. Unified Cart
Chat, voice, web UI, and extension share the same authoritative cart.
9. Gated Agentic Payment
NOVA can progress from conversation to a real Razorpay TEST checkout.
10. Explainable Commerce
Commerce-critical actions have a traceable path from user intent to transaction.
🎯 Track 01 Mapping
Track Requirement	NOVA Implementation
Grow merchant revenue	Recommendations, cross-sell, upsell
AI buyers	AI-readable catalog
Conversational commerce	NOVA chat + voice
Agentic shopping	Product → cart → checkout
Product discovery	Dynamic commerce search
Personalized shopping	Purchase-history signals
Browser commerce	NOVA browser extension
Explainable money actions	Checkout summary + audit
Bounded money actions	Existing expenditure rules
Gated money actions	Explicit confirmation
Payment	Razorpay TEST Mode
Failure handling	Cart-preserving failure flow
Auditability	Commerce audit trail
🗺️ Future Expansion
The current architecture can be extended toward:
Multi-merchant AI shopping
        ↓
Merchant-specific agents
        ↓
AI-to-merchant commerce
        ↓
Agent-readable merchant catalogs
        ↓
Autonomous product comparison
        ↓
Personalized offers
        ↓
Dynamic merchant campaigns
        ↓
AI-driven conversion optimization
Potential future capabilities include:
Merchant-side campaign orchestration
Dynamic offers
AI-generated bundles
Merchant analytics
Conversion optimization
Agent-to-agent commerce
Multi-merchant checkout
Intelligent price tracking
Automated replenishment
AI buyer APIs
📌 Project Philosophy
NOVA is built around one principle:
The AI should be intelligent enough to understand what the user wants, but the application should be deterministic enough to make sure the money and commerce state are correct.
This separation enables NOVA to combine the flexibility of generative AI with the reliability required for commerce.
👨‍💻 Project
NOVA — AI Shopping & Agentic Commerce Assistant
Built for the Razorpay AI Buildathon — Track 01: AI Growth & Agentic Commerce

GitHub:
Vidyadhar-pothula/NOVA---AI-Shopping-Assistant

Live Application:
https://nova-ai-shopping-assistant.onrender.com

⭐ Final Architecture at a Glance



NOVA turns natural-language shopping into a controlled agentic commerce workflow — from discovery to recommendation, cart, checkout, payment, verification, and order completion.
