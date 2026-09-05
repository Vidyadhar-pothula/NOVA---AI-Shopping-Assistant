-- Schema definitions for NOVA Personal AI Commerce Agent

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL
);

-- Products table
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    brand TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    price REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    rating REAL,
    review_count INTEGER,
    availability INTEGER DEFAULT 1, -- 1 = in stock, 0 = out of stock
    merchant TEXT NOT NULL,
    merchant_name TEXT,
    source_name TEXT,
    product_url TEXT,
    delivery_information TEXT,
    specifications TEXT, -- JSON string
    images TEXT, -- JSON string (array of URLs or local assets)
    retrieved_at TEXT,
    is_verified INTEGER DEFAULT 1,
    is_demo INTEGER DEFAULT 0
);

-- Carts table
CREATE TABLE IF NOT EXISTS carts (
    id TEXT PRIMARY KEY, -- session_id or user_id
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cart items
CREATE TABLE IF NOT EXISTS cart_items (
    cart_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (cart_id, product_id),
    FOREIGN KEY (cart_id) REFERENCES carts(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL, -- 'prepared', 'paid', 'cancelled'
    total_amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    razorpay_order_id TEXT,       -- Razorpay order ID (order_xxx)
    razorpay_payment_id TEXT,     -- Razorpay payment ID after successful payment (pay_xxx)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Order items
CREATE TABLE IF NOT EXISTS order_items (
    order_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    price REAL NOT NULL,
    PRIMARY KEY (order_id, product_id),
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- Session state table for conversational reference mapping (e.g. "first one", "second one")
CREATE TABLE IF NOT EXISTS session_states (
    session_id TEXT PRIMARY KEY,
    last_product_ids TEXT, -- JSON array of product IDs in order of last display
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Shopping History (basic foundation for Phase 10)
CREATE TABLE IF NOT EXISTS shopping_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rating REAL,
    returned INTEGER DEFAULT 0, -- 0 = No, 1 = Yes
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- User Preferences (basic foundation for Phase 10)
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT NOT NULL,
    pref_key TEXT NOT NULL, -- e.g. 'preferred_brand', 'shoe_size', 'spending_range'
    pref_value TEXT,
    PRIMARY KEY (user_id, pref_key),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Audit Trail Table (Phase 7)
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL, -- 'USER_REQUEST', 'PRODUCT_DISCOVERY', 'AI_RECOMMENDATION', 'CART_UPDATED', 'CHECKOUT_CREATED', 'USER_CONFIRMED', 'RAZORPAY_ORDER_CREATED', 'PAYMENT_SUCCESS', 'PAYMENT_FAILED'
    event_data TEXT NOT NULL, -- JSON string payload
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Revenue Analytics Table (Phase 9)
CREATE TABLE IF NOT EXISTS revenue_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE NOT NULL,
    session_id TEXT NOT NULL,
    baseline_amount REAL NOT NULL DEFAULT 0,
    ai_assisted_amount REAL NOT NULL DEFAULT 0,
    incremental_amount REAL NOT NULL DEFAULT 0,
    has_recommendation INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Merchant Campaigns Table (Phase 10)
CREATE TABLE IF NOT EXISTS merchant_campaigns (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    goal TEXT NOT NULL, -- 'increase_aov', 'promote_cross_sell', 'category_boost'
    target_category TEXT,
    boost_factor REAL DEFAULT 1.5,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

