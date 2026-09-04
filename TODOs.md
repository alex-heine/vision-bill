1. Create Make commands for scripts
2. Create an .env.scripts used in Make
3. Write a README for the scripts
    3.1. Include suggestion for using an read-only user for the DB
4. DB permission suggestion / evaluation:
    4.1. How about db users permissions? Like one user for alembic and one for the program (with a whitelist of allowed commands from pgsql side)
    4.2. Maybe a script?
        4.2.1. `CREATE ROLE readonly_user WITH LOGIN PASSWORD 'yourpassword';`
        4.2.2.
```sql
-- Remove default public schema privileges
REVOKE ALL ON SCHEMA public FROM readonly_user;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM readonly_user;

-- Grant connect + usage + select only
GRANT CONNECT ON DATABASE your_db TO readonly_user;
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;

-- Make sure this applies to future tables too
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO readonly_user;
```
        4.2.3. `ALTER ROLE readonly_user SET default_transaction_read_only = on;`
        4.2.4. `ALTER ROLE readonly_user SET statement_timeout = '5s';`
5. generate SVG icon
6. Give user some sweet "please wait" progress bar or anything that tells him the receipt is still being worked on.
7. Fix mobile layout
    7.1. Navbar is too tight on mobile
    7.2. Tags are annoying on mobile
    7.3. Images are too large for mobile screen
    7.4. New navigation bar: Search - Upload - to be discussed (Settings or List of Receipts, but then where are settings..?)
        7.4.1. Dashboard is click on logo, statistics is a button inside dashboard
        7.4.2. Upload also has a small button to list receipts
        7.4.3. Settings hides the llm test suite
8. Receipts are stored as duplicate when you verify manually (one verified and one unverified)
9. Add details to statistics
10. Add details to dashboard
11. Tags are a bit annoying on mobile
12. Add user auth system for Multi-User-Systems
    12.1. Add admin role to support benchmarks etc
    12.2. Add setting if the admin is allowed to see all receipts or each user only his own (EVAL this idea)
13. Receipts should use UUIDs as IDs
14. Switch from env vars to config file, modifyable via settings
15. Add search for product ("Schinken") to see where and when it was bought (latest-, cheapest-, avg-price)
