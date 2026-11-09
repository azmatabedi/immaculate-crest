# Immaculate Crest website: landing page, bulk-order system and admin dashboard

FastAPI (Python) + MySQL + a JavaScript front end. Runs with Docker on any VPS.

## What is inside
| Path | Purpose |
|---|---|
| `static/index.html` | Public website (loads products, services, reviews, videos and Etsy links from the API) |
| `static/admin/index.html` | Admin dashboard at `/admin/` |
| `app/` | Backend: API, database models, notifications, PDF quotations |
| `docker-compose.yml`, `Dockerfile`, `Caddyfile` | App + MySQL + automatic HTTPS |
| `.env.example` | All settings and API keys (copy to `.env`) |
| `backup.sh` | Database and uploads backup |

## Deploy on a VPS (Ubuntu example)
1. Get a VPS (2 GB RAM is enough) and point your domain's **A record** to its IP address.
2. Install Docker: `curl -fsSL https://get.docker.com | sh`
3. Upload and unzip this folder, then: `cd immaculate-crest && cp .env.example .env && nano .env`
   Set `DOMAIN`, `BASE_URL`, `SECRET_KEY` (`openssl rand -hex 32`), `ADMIN_PASSWORD`, the three MySQL passwords and `ADMIN_EMAIL`.
4. Start: `docker compose up -d --build` (first start takes a few minutes).
5. Open `https://yourdomain.com` and sign in at `https://yourdomain.com/admin/` with `ADMIN_USERNAME` / `ADMIN_PASSWORD`.
   Test on your own computer first with `DOMAIN=localhost` and `BASE_URL=http://localhost`.
6. Start with the sample products and edit them in the dashboard: add photos, specifications, minimum quantity and customization options.

Shared hosting (cPanel) without Docker: use "Setup Python App", Python 3.12, `pip install -r requirements.txt`, set the `.env` values as environment variables
(`DATABASE_URL=mysql+pymysql://user:pass@localhost/dbname?charset=utf8mb4`), start command `uvicorn app.main:app`. Not every shared host allows this, a VPS is simpler.

## Email notifications
Fill in `SMTP_*`. For Gmail use `smtp.gmail.com`, port 587 and an App Password (needs 2-step verification). Until SMTP is set, emails are skipped and logged as "skipped" in the order's communication history.
Sent: customer confirmation, admin alert (with reference and file names), status-change emails, and quotation/invoice emails with the PDF attached.

## WhatsApp notifications (Meta Cloud API)
1. Create a Meta developer app, add the WhatsApp product, and a WhatsApp Business phone number. Put the permanent token in `WA_TOKEN` and the phone number ID in `WA_PHONE_ID`.
2. **Important:** WhatsApp only allows free-form messages to a customer within 24 hours of their last message to you. Messages to customers who have not messaged you first (acknowledgements, status updates, quotations) normally require **pre-approved message templates**. The code sends plain text and document messages, so it works for the admin alert after you message the business number once, and for customers inside the 24-hour window. To message customers at any time, create templates in Meta Business Manager and change `send_whatsapp()` in `app/notify.py` to send them. The site works without this: the dashboard shows each delivery status.
3. Quotation PDFs are sent as a WhatsApp document link to `BASE_URL/d/<private token>`, so `BASE_URL` must be your public https address.

## Daily use
- **Orders**: Dashboard > Orders. Open an inquiry to read the requirements, download every attachment, change the status (customer is notified), and create a quotation or invoice. Tick "Send now" to email and WhatsApp the PDF; use "Send / resend" later. Creating another quotation makes a new revision (rev 2, 3...), and the history stays.
- **Prices** entered on website cards are never shown as final. Quotation prices are whatever you type.
- **Products**: add, edit, hide, delete, upload several photos or videos per product, and set the order with the sort number.
- **Videos**: upload manufacturing-unit videos or photos. Reviews: customers submit, you approve. Stats: the numbers and charts on the homepage (shops, items, monthly sales, Instagram posts and followers). Settings: edit the Etsy store links and your business location (the Google Map on the homepage). The Dashboard shows total orders, customers, articles and products.

## Backups
Run `./backup.sh` (database dump + uploads, 14 days kept). Schedule it with cron (see the script). Copy the `backups/` folder off the server regularly.
Restore: `gunzip < backups/db_DATE.sql.gz | docker compose exec -T db mysql -uroot -pROOTPASS immaculate` and
`docker compose exec -T app tar xzf - -C /data < backups/uploads_DATE.tar.gz`.

## Security notes
- Admin login uses hashed passwords and signed tokens that expire after 8 hours; failed logins are rate-limited.
- Customer attachments are stored privately and only downloadable from the dashboard. Uploads are checked for allowed type, real file signature and size (25 MB files, 200 MB videos).
- All database access goes through SQLAlchemy (no raw SQL), all dashboard output is escaped, and secrets live in `.env` only.
- Keep the server updated, and keep `.env` private.

## Not included yet
- **Etsy API sync.** The homepage links to your Etsy shops (editable in Settings). Pulling live Etsy listings needs an Etsy API key approved by Etsy.
- Online payments, multiple admin users and password reset (the first admin comes from `.env`).
- Product page URLs for search engines: product details open in a pop-up on the homepage.
