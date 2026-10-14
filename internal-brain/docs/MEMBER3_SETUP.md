# Member 3: accounts only Punya can create

Three things need a human: a question to the organizers, a Tencent Cloud account for the live URL,
and Google accounts for live Drive (L07). Console labels change over time; if a label below does not
match exactly, look for the closest one and note the difference here.

Never paste a password, API key, token or private key into chat or a commit. Secrets go in
`internal-brain/.env` or `internal-brain/deploy/.env` (both gitignored) and nowhere else.

## 1. Message to the organizers (G15)

Send through the official hackathon channel (Discord / email / WeChat group, whichever the organizers use):

> Hi, we are team YieldGPT in the Aspire FinTech track ("The Internal Brain"). Two quick questions
> before we deploy:
> 1. Which Tencent Cloud services, if any, must a submission use? For example, must the live URL run on
>    Tencent Cloud (CVM / Lighthouse), must the model be Tencent Hunyuan, and must any storage or
>    database be a Tencent service (COS, TencentDB, VectorDB)?
> 2. Are participants given Tencent Cloud credits or vouchers, and if so, how do we claim them?
> Thank you!

When the answer arrives, give the agent the exact text (or a screenshot) plus the date and the sender.
It goes into `docs/TENCENT_REQUIREMENTS.md` word for word. Until then that file says **pending**.

## 2. Tencent Cloud account (live URL)

1. Open https://www.tencentcloud.com and click **Sign up** (top right). Use an email you control
   (the NTU email is fine). Verify the email with the code you are sent.
2. In the console, finish **Identity verification** as an individual
   (Account Center > Identity Verification). Deployment features stay locked until this is done.
3. Add a payment method under **Billing Center > Payment Methods**, or redeem organizer credits there
   if question 2 above gets a yes. Do this yourself; the agent never enters payment details.
4. Optional but recommended: **Billing Center > Budget** and set an alert, e.g. USD 10.
5. Create the server: open **Lighthouse** in the console (search "Lighthouse"), then **Create**:
   - Region: **Singapore**
   - Image: **System image > Ubuntu 22.04 LTS** (or the Docker CE app image if offered)
   - Plan: the smallest with **2 vCPU / 2 GB RAM** or more
   - Login: choose **SSH key pair > Create key pair**, download the `.pem` file, then move it to
     `~/.ssh/yieldgpt-lighthouse.pem` and run `chmod 600 ~/.ssh/yieldgpt-lighthouse.pem`
   - Name: `yieldgpt-demo`
6. After it starts, open the instance > **Firewall** tab > **Add rule**: allow TCP **80** and TCP **443**
   from all sources (`0.0.0.0/0`). Keep 22 (SSH) open; you may restrict it to your own IP.
7. Tell the agent the instance's **public IP** and that the key is at `~/.ssh/yieldgpt-lighthouse.pem`.
   The agent deploys with `deploy/docker-compose.yml` in demo mode (no real company data), with secrets
   generated on the server by `deploy/make_env.py`.

## 3. Google Cloud project and test accounts (live Drive, L07)

L07 needs a **shared drive**, which only exists in Google Workspace, plus an account outside the
domain for the external-share case.

**Decision for Punya first:** which Workspace domain to use. Options:
- a Google Workspace **Business Starter free trial** (14 days, needs a domain you own; a cheap new
  domain such as `yieldgpt-demo.xyz` works), or
- an existing test Workspace you already administer.

Do not use the NTU tenant or any company tenant: the test creates, shares, edits and deletes files.

### 3a. Workspace and accounts
1. Go to https://workspace.google.com > **Get started**, choose the trial, enter the demo domain and
   verify it (the wizard shows a TXT record to add at your domain registrar).
2. In https://admin.google.com > **Directory > Users > Add new user**, create two users:
   `drive-bot@<domain>` (ingestion, read only) and `jdoe@<domain>` (the asking persona).
3. Also have one ordinary **@gmail.com** account ready (Punya's gmail) to receive the external share.
4. In Admin console > **Apps > Google Workspace > Drive and Docs > Sharing settings**, allow sharing
   outside the organization (needed for the external-share step).

### 3b. Google Cloud project and OAuth client
1. Sign in to https://console.cloud.google.com as the Workspace admin. Top bar project picker >
   **New project**, name `yieldgpt-drive`, then **Create**.
2. **APIs & Services > Library**, search **Google Drive API**, then **Enable**.
3. **APIs & Services > OAuth consent screen** (now called **Google Auth Platform**): user type
   **Internal**, app name `YieldGPT Drive test`, your email as the support and developer contact, **Save**.
4. **Data access** (or **Scopes**): add `https://www.googleapis.com/auth/drive.readonly`. Save.
5. **Clients > Create client**: type **Web application**, name `oauth-playground`, and under
   **Authorized redirect URIs** add `https://developers.google.com/oauthplayground`. **Create**.
   Keep the client ID and secret in your password manager, not in chat.

### 3c. Short-lived tokens (repeat whenever they expire, about 1 hour)
1. Open https://developers.google.com/oauthplayground, click the **gear** (top right), tick
   **Use your own OAuth credentials**, and paste the client ID and secret.
2. In **Step 1**, enter `https://www.googleapis.com/auth/drive.readonly` and click **Authorize APIs**.
   Sign in as `drive-bot@<domain>`. In **Step 2**, click **Exchange authorization code for tokens**.
3. Copy the **Access token** into `internal-brain/.env` as `DRIVE_BOT_TOKEN=...` yourself.
4. Repeat steps 2 and 3 signed in as `jdoe@<domain>` and save it as `DRIVE_TOKEN_JDOE=...`.
5. Tell the agent "tokens are in .env". The agent writes the `IB_DRIVE_CONFIG` JSON (no secrets in it)
   and gives you the browser steps for the lifecycle test: shared drive, personal drive, folder
   inheritance, file share, external share, edit, delete and revoke.
