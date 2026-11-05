-- ============================================================================
-- HOTELAGENT v6.0 - PEARL CONTINENTAL (PC) LAHORE DATABASE SCHEMA & SEED DATA
-- Fully Free & Open-Source Local PostgreSQL Setup (FLOAT / PKR Price Version)
-- Compatible directly with pgAdmin 4 Query Tool and terminal psql
-- ============================================================================

-- 1. Enable btree_gist extension (MANDATORY for GiST Exclusion Constraints)
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Clean drop for a clean slate (Dropping dependent child tables first to avoid FK blocks)
DROP TABLE IF EXISTS chat_message CASCADE;
DROP TABLE IF EXISTS chat_thread CASCADE;
DROP TABLE IF EXISTS booking_otp CASCADE;
DROP TABLE IF EXISTS notification CASCADE;
DROP TABLE IF EXISTS transaction CASCADE;
DROP TABLE IF EXISTS booking_service CASCADE;
DROP TABLE IF EXISTS booking_room CASCADE;
DROP TABLE IF EXISTS booking CASCADE;
DROP TABLE IF EXISTS service CASCADE;
DROP TABLE IF EXISTS room CASCADE;
DROP TABLE IF EXISTS room_type CASCADE;
DROP TABLE IF EXISTS user_session CASCADE;
DROP TABLE IF EXISTS user_account CASCADE;

-- ----------------------------------------------------------------------------
-- 2. USER ACCOUNTS (Standard user-facing website accounts with profile details)
-- ----------------------------------------------------------------------------
CREATE TABLE user_account (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT,
    age INT CHECK (age >= 0 AND age <= 150),
    gender TEXT,
    address TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 3. USER SESSIONS (Multi-device active session token mapping)
-- ----------------------------------------------------------------------------
CREATE TABLE user_session (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES user_account(id) ON DELETE CASCADE,
    session_token_hash TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 4. ROOM TYPES (PC Lahore room categories with dynamic JSONB amenities)
-- ----------------------------------------------------------------------------
CREATE TABLE room_type (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    base_price FLOAT NOT NULL CHECK (base_price >= 0),
    max_guests INT NOT NULL CHECK (max_guests > 0),
    bed_type TEXT NOT NULL,
    amenities JSONB DEFAULT '[]'::jsonb
);

-- ----------------------------------------------------------------------------
-- 5. ROOMS (Physical hotel room inventory)
-- ----------------------------------------------------------------------------
CREATE TABLE room (
    id SERIAL PRIMARY KEY,
    room_type_id INT NOT NULL REFERENCES room_type(id) ON DELETE RESTRICT,
    room_number TEXT UNIQUE NOT NULL,
    floor INT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL
);

-- ----------------------------------------------------------------------------
-- 6. SERVICES (Add-ons: transport, breakfast, extra bed)
-- ----------------------------------------------------------------------------
CREATE TABLE service (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    price FLOAT NOT NULL CHECK (price >= 0),
    pricing_unit TEXT NOT NULL CHECK (pricing_unit IN ('per_booking', 'per_night', 'per_guest'))
);

-- ----------------------------------------------------------------------------
-- 7. BOOKINGS (Core booking record tied to user account)
-- ----------------------------------------------------------------------------
CREATE TABLE booking (
    id SERIAL PRIMARY KEY,
    booking_ref TEXT UNIQUE NOT NULL,
    confirmation_code TEXT UNIQUE,
    user_id INT NOT NULL REFERENCES user_account(id) ON DELETE RESTRICT,
    check_in DATE NOT NULL,
    check_out DATE NOT NULL,
    guests INT NOT NULL CHECK (guests > 0),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'CONFIRMED', 'COMPLETED', 'CANCELLED', 'EXPIRED')),
    payment_status TEXT NOT NULL DEFAULT 'UNPAID' CHECK (payment_status IN ('UNPAID', 'PAID', 'REFUNDED')),
    hold_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    total_amount FLOAT NOT NULL CHECK (total_amount >= 0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_booking_dates CHECK (check_out > check_in)
);

-- ----------------------------------------------------------------------------
-- 8. BOOKING ROOMS (Maps bookings to physical rooms with Exclusion Constraint)
-- ----------------------------------------------------------------------------
CREATE TABLE booking_room (
    id SERIAL PRIMARY KEY,
    booking_id INT NOT NULL REFERENCES booking(id) ON DELETE CASCADE,
    room_id INT NOT NULL REFERENCES room(id) ON DELETE RESTRICT,
    check_in DATE NOT NULL,
    check_out DATE NOT NULL,
    price_per_night FLOAT NOT NULL CHECK (price_per_night >= 0),
    blocks_inventory BOOLEAN DEFAULT TRUE NOT NULL,
    CONSTRAINT chk_booking_room_dates CHECK (check_out > check_in),
    CONSTRAINT no_room_overlap EXCLUDE USING gist (
        room_id WITH =,
        daterange(check_in, check_out, '[)') WITH &&
    ) WHERE (blocks_inventory)
);

-- ----------------------------------------------------------------------------
-- 9. BOOKING SERVICES (Selected add-ons for a booking)
-- ----------------------------------------------------------------------------
CREATE TABLE booking_service (
    id SERIAL PRIMARY KEY,
    booking_id INT NOT NULL REFERENCES booking(id) ON DELETE CASCADE,
    service_id INT NOT NULL REFERENCES service(id) ON DELETE RESTRICT,
    quantity INT NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price FLOAT NOT NULL CHECK (unit_price >= 0)
);

-- ----------------------------------------------------------------------------
-- 10. TRANSACTIONS (Financial ledger tied to user account)
-- ----------------------------------------------------------------------------
CREATE TABLE transaction (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES user_account(id) ON DELETE RESTRICT,
    booking_id INT NOT NULL REFERENCES booking(id) ON DELETE RESTRICT,
    type TEXT NOT NULL CHECK (type IN ('PAYMENT', 'REFUND')),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'SUCCEEDED', 'FAILED')),
    amount FLOAT NOT NULL CHECK (amount > 0),
    parent_transaction_id INT REFERENCES transaction(id),
    idempotency_key TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 11. NOTIFICATIONS (Transactional Outbox)
-- ----------------------------------------------------------------------------
CREATE TABLE notification (
    id SERIAL PRIMARY KEY,
    booking_id INT NOT NULL REFERENCES booking(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('CONFIRMED', 'CANCELLED', 'REFUNDED')),
    to_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    attempts INT DEFAULT 0 NOT NULL,
    last_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP WITH TIME ZONE
);

-- ----------------------------------------------------------------------------
-- 12. BOOKING OTP (Temporary email verification code for link requests)
-- ----------------------------------------------------------------------------
CREATE TABLE booking_otp (
    id SERIAL PRIMARY KEY,
    booking_id INT NOT NULL REFERENCES booking(id) ON DELETE CASCADE,
    target_email TEXT NOT NULL,
    otp_code TEXT NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_used BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 13. CHAT THREADS (User-specific chat conversation containers)
-- ----------------------------------------------------------------------------
CREATE TABLE chat_thread (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES user_account(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New Chat',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 14. CHAT MESSAGES (Relational message records tagged with role enforcement)
-- ----------------------------------------------------------------------------
CREATE TABLE chat_message (
    id SERIAL PRIMARY KEY,
    thread_id INT NOT NULL REFERENCES chat_thread(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_chat_message_role CHECK (role IN ('user', 'assistant'))
);

-- Indexes for performance enhancement and foreign key lookups
CREATE INDEX idx_user_account_email ON user_account(email);
CREATE INDEX idx_user_session_token ON user_session(session_token_hash);
CREATE INDEX idx_booking_user_id ON booking(user_id);
CREATE INDEX idx_transaction_user_id ON transaction(user_id);
CREATE INDEX idx_chat_thread_user_id ON chat_thread(user_id);
CREATE INDEX idx_chat_message_thread_id ON chat_message(thread_id);

-- ============================================================================
-- INITIAL SEED DATA: PEARL CONTINENTAL HOTEL LAHORE (FLOAT / PKR Prices)
-- ============================================================================

-- Room Types (with dynamic JSONB amenities arrays)
INSERT INTO room_type (name, description, base_price, max_guests, bed_type, amenities) VALUES
('Standard King', 'Elegant entry-level room featuring city views, central AC, electronic safe, work desk, and high-speed Wi-Fi.', 30000.00, 2, '1 King Bed', '["City View", "Free Wi-Fi", "Work Desk", "Electronic Safe", "Tea/Coffee Maker", "Central AC"]'::jsonb),
('Standard Twin', 'Comfortable double-occupancy room with twin beds, work desk, electronic safe, and garden/pool views.', 30000.00, 2, '2 Twin Beds', '["City/Pool View", "Free Wi-Fi", "Work Desk", "Electronic Safe", "24-hr Room Service"]'::jsonb),
('Deluxe King', 'Upgraded room with generous layout, sumptuous king bed, sitting area, premium marble bathroom, and smart TV.', 38000.00, 2, '1 King Bed', '["Seating Area", "Marble Bathroom", "Flat-screen TV", "Minibar", "City View", "Free Wi-Fi"]'::jsonb),
('Executive King', 'Refined room tailored for business executives, offering complimentary access to the 5th-floor Executive Lounge and breakfast.', 48000.00, 2, '1 King Bed', '["Executive Lounge Access", "Complimentary Breakfast", "City View", "Work Desk", "Minibar"]'::jsonb),
('Business Suite', 'Spacious suite featuring a master bedroom with king bed, separate living and working area, and Executive Lounge privileges.', 75000.00, 3, '1 King Bed + Living Room', '["Executive Lounge Access", "Separate Living & Working Area", "Dining Table", "Airport Shuttle Included"]'::jsonb),
('Presidential Suite', 'The premiere accommodation at PC Lahore featuring 2 master bedrooms, expansive living/dining space, private jacuzzi, and dedicated butler service.', 180000.00, 4, '2 King Beds', '["Top Floor", "Dedicated Butler Service", "Expansive Living Area", "Master Jacuzzi", "Free Airport Pickup"]'::jsonb);

-- Physical Rooms
INSERT INTO room (room_type_id, room_number, floor, is_active) VALUES
(1, '201', 2, TRUE), (1, '202', 2, TRUE), (1, '203', 2, TRUE), (1, '204', 2, TRUE), (1, '205', 2, TRUE),
(1, '206', 2, TRUE), (1, '207', 2, TRUE), (1, '208', 2, TRUE), (1, '209', 2, TRUE), (1, '210', 2, TRUE),
(2, '211', 2, TRUE), (2, '212', 2, TRUE), (2, '213', 2, TRUE), (2, '214', 2, TRUE), (2, '215', 2, TRUE),
(2, '216', 2, TRUE), (2, '217', 2, TRUE), (2, '218', 2, TRUE), (2, '219', 2, TRUE), (2, '220', 2, TRUE);

INSERT INTO room (room_type_id, room_number, floor, is_active) VALUES
(3, '301', 3, TRUE), (3, '302', 3, TRUE), (3, '303', 3, TRUE), (3, '304', 3, TRUE), (3, '305', 3, TRUE),
(3, '306', 3, TRUE), (3, '307', 3, TRUE), (3, '308', 3, TRUE), (3, '309', 3, TRUE), (3, '310', 3, TRUE);

INSERT INTO room (room_type_id, room_number, floor, is_active) VALUES
(4, '401', 4, TRUE), (4, '402', 4, TRUE), (4, '403', 4, TRUE), (4, '404', 4, TRUE), (4, '405', 4, TRUE),
(4, '406', 4, TRUE), (4, '407', 4, TRUE), (4, '408', 4, TRUE), (4, '409', 4, TRUE), (4, '410', 4, TRUE);

INSERT INTO room (room_type_id, room_number, floor, is_active) VALUES
(5, '501', 5, TRUE), (5, '502', 5, TRUE), (5, '503', 5, TRUE), (5, '504', 5, TRUE), (5, '505', 5, TRUE),
(6, '509', 5, TRUE), (6, '510', 5, TRUE);

-- Add-on Services
INSERT INTO service (name, description, price, pricing_unit) VALUES
('Continental Buffet Breakfast', 'Daily buffet served at Marco Polo Restaurant featuring Pakistani, Continental, and Oriental cuisines.', 4500.00, 'per_guest'),
('VIP Airport Shuttle Service', 'Private chauffeur transfer between Allama Iqbal International Airport and PC Hotel Lahore.', 7000.00, 'per_booking'),
('Extra Rollaway Bed', 'Additional bedding setup including linens, pillows, and hypoallergenic bedding.', 6000.00, 'per_night'),
('Laundry & Pressing Service', 'Express laundering and pressing service.', 3500.00, 'per_booking');

-- ============================================================================
-- VERIFY SETUP
-- ============================================================================
SELECT 'SUCCESS: PC Lahore database tables and seed data loaded successfully with JSONB support!' AS result;