# Free services — what you set up by hand

Everything here is free (free tiers, test numbers, open source). Limits were checked on the official pages on
7 October 2026; re-check them before relying on them. **Put every value in `C:\PawGuard\.env` (git-ignored). Never
paste passwords, tokens or keys into chat, issues or commits.** The keys are listed in `.env.example`.

In demo mode every message goes to *your* test recipients (`PAWGUARD_DEMO_NOTIFY_EMAIL`,
`PAWGUARD_DEMO_NOTIFY_WHATSAPP`), never to the fictional `@example.org` demo accounts.

## 1. Email — Gmail SMTP with an app password (about 10 minutes)

1. Use a **personal** Gmail account (work/school accounts can't create app passwords). A new Gmail just for
   PawGuard is best.
2. Turn on **2-Step Verification**: <https://myaccount.google.com/security> → 2-Step Verification. Use your phone or
   an authenticator app — app passwords are not available if 2-Step Verification uses security keys only, or if
   Advanced Protection is on.
3. Create an **app password**: <https://myaccount.google.com/apppasswords> → name it `PawGuard` → copy the
   16-character password (shown once).
4. Add to `.env`:
   ```
   PAWGUARD_SMTP_USER=yourname@gmail.com
   PAWGUARD_SMTP_PASSWORD=the16characterpassword   (no spaces)
   PAWGUARD_EMAIL_FROM=PawGuard 360 demo <yourname@gmail.com>
   PAWGUARD_DEMO_NOTIFY_EMAIL=the-inbox-where-you-want-demo-emails@example.com
   ```
5. To switch it off later: remove the app password on the same page.

**Limits (Google help page):** a personal account may hit an error after "more than 500 recipients in a single email
and or more than 500 emails sent in a day"; sending usually works again "within 1 to 24 hours". PawGuard caps itself
at `PAWGUARD_EMAIL_DAILY_CAP` (default 100/day) and holds the rest until the next day.

## 2. Web Push — nothing to sign up for (2 minutes)

1. Add `PAWGUARD_VAPID_CONTACT=mailto:yourname@gmail.com` to `.env` (push services may use it to contact you).
2. The keys are generated for you: `pawguard-admin push keys` writes `PAWGUARD_VAPID_PUBLIC_KEY` and
   `PAWGUARD_VAPID_PRIVATE_KEY`.
3. On a phone, open the app over **HTTPS** (the public link) and tap "Turn on notifications".
   - **Android (Chrome):** works in the browser.
   - **iPhone/iPad:** needs iOS/iPadOS 16.4 or later, and the app added to the Home Screen (Share → Add to Home
     Screen), then opened from that icon.

## 3. WhatsApp — Meta Cloud API test number (20–30 minutes)

1. Go to <https://developers.facebook.com>, log in with Facebook and register as a developer (verify your phone/email).
2. **My Apps → Create app** → choose the WhatsApp / "connect with customers" use case → name it `PawGuard 360` →
   create. If asked, create a (free) Business portfolio.
3. In the app: **WhatsApp → API Setup**. Meta creates a **test business phone number** for you. Note the
   **Phone number ID** shown there.
4. In the **To** field choose **Manage phone number list** → add your WhatsApp number (`+91…`) → enter the code Meta
   sends to it on WhatsApp. Add your team's numbers the same way (the plan you shared says up to 5; the current docs
   don't state the number — the dashboard shows the limit).
5. Click **Send message**: you should receive the `hello_world` template on WhatsApp.
6. **Reply "hi" from your phone.** That opens the 24-hour "customer service window" in which the app may send you
   normal (non-template) reminder messages. Repeat whenever you want to test after a 24-hour gap.
7. Copy into `.env`:
   ```
   PAWGUARD_WHATSAPP_TOKEN=the temporary access token   (expires in under 24 hours)
   PAWGUARD_WHATSAPP_PHONE_NUMBER_ID=the phone number id
   PAWGUARD_WHATSAPP_APP_SECRET=App settings → Basic → App secret → Show
   PAWGUARD_WHATSAPP_VERIFY_TOKEN=any long random text you choose (used later for the webhook)
   PAWGUARD_DEMO_NOTIFY_WHATSAPP=+91XXXXXXXXXX   (one of the numbers you verified in step 4)
   ```
8. **Optional — reminders outside the 24-hour window:** WhatsApp Manager → Message templates → Create → category
   **Utility** → name `pet_vaccination_reminder` → English → body
   `Reminder from {{1}}: {{2}}'s {{3}} vaccination is due on {{4}}.` → submit. Approval can take minutes to hours.
   When approved, set `PAWGUARD_WHATSAPP_TEMPLATE=pet_vaccination_reminder`.
9. **Optional — a token that doesn't expire daily:** Business settings → Users → System users → Add (admin) → assign
   the app and the WhatsApp account → Generate token with `whatsapp_business_messaging` and
   `whatsapp_business_management`. Replace `PAWGUARD_WHATSAPP_TOKEN` with it.
10. **Webhook (only for delivery status and replies)** needs a public HTTPS address. The free tunnel address changes
    on every restart, so you'll re-enter it in Meta's dashboard each time; the app shows the exact URL to paste.

**What the docs say:** test numbers "have relaxed messaging limits and don't require a payment method on file in
order to send template messages"; the temporary token "expires in less than 24 hours"; non-template messages are
allowed only inside the 24-hour window that starts when the recipient messages you.

## 4. AI assistant — Gemini API free tier (5 minutes), or Ollama (fully local)

**Gemini**
1. Go to <https://aistudio.google.com> (you must be 18 or older) → **Get API key** → Create API key (new project) → copy.
2. Open <https://aistudio.google.com/rate-limit> and pick a model that shows free quota (a Flash or Flash-Lite model).
3. Add to `.env`:
   ```
   PAWGUARD_LLM_PROVIDER=gemini
   PAWGUARD_GEMINI_API_KEY=the key
   PAWGUARD_GEMINI_MODEL=the model code from step 2
   ```
**Important (Gemini terms, free tier):** Google may use free-tier prompts and responses to improve its products and
"human reviewers may read, annotate, and process your API input and output". The terms say: "Do not submit
sensitive, confidential, or personal information to the Unpaid Services." PawGuard therefore sends no owner names,
phone numbers, addresses or photos to Gemini, and the free tier is for the demo only. The terms also say the
service must not be part of an app "directed towards or … likely to be accessed by individuals under the age of 18".

**Ollama (alternative, nothing leaves your laptop; needs about 16 GB RAM)**
1. Install from <https://ollama.com>, then run `ollama pull qwen2.5:3b`.
2. `.env`: `PAWGUARD_LLM_PROVIDER=ollama` (and `PAWGUARD_OLLAMA_MODEL` if you pulled a different model).

## Later parts (steps will be added when built)
- Twilio trial (optional real calls to verified numbers only), Brevo (optional email alternative), Oracle Cloud
  Always Free + DuckDNS + Let's Encrypt, or Vercel + Supabase free tier.
- Not possible for free: SMS to Indian users (needs paid, DLT-registered SMS). Not built; noted in the roadmap.
