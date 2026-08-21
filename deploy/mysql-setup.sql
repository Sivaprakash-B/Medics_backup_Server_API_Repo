-- =============================================================
--  MySQL setup for the API gateway
--  Run as root on the MySQL server BEFORE deploying the API.
-- =============================================================

-- 1. Create the database
CREATE DATABASE IF NOT EXISTS dbname
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- 2. Create a dedicated API user, locked to the API server's IP
--    Replace 'STRONG_PASSWORD_HERE' and '10.0.0.5' with real values.
CREATE USER IF NOT EXISTS 'api_user'@'10.0.0.5'
    IDENTIFIED BY 'STRONG_PASSWORD_HERE';

-- 3. Grant ONLY the operations the API actually needs
--    (no DROP, ALTER, GRANT, FILE, etc.)
GRANT SELECT, INSERT, UPDATE, DELETE
    ON dbname.*
    TO 'api_user'@'10.0.0.5';

FLUSH PRIVILEGES;

-- 4. Verify (optional)
SHOW GRANTS FOR 'api_user'@'10.0.0.5';
