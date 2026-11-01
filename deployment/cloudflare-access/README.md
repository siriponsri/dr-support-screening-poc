# Share the demo with invited team members (Cloudflare Tunnel + Access)

Team members open one link on your Cloudflare domain, for example `https://dr-demo.<your-domain>/app/`.
Cloudflare first asks for their e-mail and sends them a one-time code; only the e-mails you invited get in.
Then the DR Screening app asks for its own sign-in as usual. Nothing on your computer is opened to the
internet: `cloudflared` makes an outgoing connection to Cloudflare, and only while you share.

**Hospital rule: only public or synthetic demo images may be shared this way. Never patient images, not
even with consent.** The start script asks you to confirm this once, and it refuses to share a demo that is
set to use workspace images.

Uses the free Cloudflare Zero Trust plan (up to 50 users). Replace `<your-domain>` everywhere with the
domain you already have on Cloudflare.

## What runs where

```text
Team member's browser --HTTPS--> Cloudflare Access (e-mail code) --> Cloudflare Tunnel
   --> cloudflared on your PC --> http://127.0.0.1:8010  (the one-click demo app, its own sign-in)
```

The tunnel points at the one-click demo app (`DR Screening Demo` desktop button, started by
`scripts/demo/start-dr-train-demo.sh`), **not** at the Docker web app. See "Technical note" below.

## One-time setup in the Cloudflare dashboard

Open <https://one.dash.cloudflare.com/> and choose your account. Menu names can move slightly between
dashboard versions; the newer name is given in brackets.

### A. Turn on the e-mail code sign-in

1. **Settings > Authentication** (or **Integrations > Identity providers**).
2. Under **Login methods**, if **One-time PIN** is not listed: **Add new > One-time PIN > Save**.

### B. Create the tunnel (do not run Cloudflare's install command)

1. **Networks > Tunnels** (or **Networks > Connectors > Cloudflare Tunnels**) > **Create a tunnel**.
2. Choose **Cloudflared** > **Next**. Name: `dr-demo` > **Save tunnel**.
3. Choose environment **Windows**. The page shows a command like
   `cloudflared.exe service install <long token>`. Copy the whole command into the clipboard, but **do not
   run it** (it would install a service that shares all the time). `start-tunnel.bat` asks for it later
   and keeps only the token, privately.
4. **Next**. Add a **Public hostname** (or **Published application route**):
   - Subdomain: `dr-demo`
   - Domain: `<your-domain>`
   - Path: empty
   - Service type: `HTTP`
   - URL: `127.0.0.1:8010` (write `127.0.0.1`, not `localhost`)
   - **Additional application settings > HTTP Settings > HTTP Host Header**: leave **empty**.
5. **Save tunnel**.

### C. Allow only invited e-mails (do this before the first share)

1. **Access > Applications** (or **Access controls > Applications**) > **Add an application** >
   **Self-hosted**.
2. Application name: `DR Screening demo`. Session duration: `24 hours`.
3. **Add public hostname**: subdomain `dr-demo`, domain `<your-domain>`, path empty.
4. **Policies > Add a policy** (or **Create new policy**):
   - Policy name: `Invited team`
   - Action: **Allow**
   - **Include**: selector **Emails**, value: each invited e-mail address (one per entry)
5. **Login methods**: tick **One-time PIN** only (untick others if shown).
6. **Save** (go through the remaining pages with **Next** and keep the defaults).

Check: open `https://dr-demo.<your-domain>/` in a private browser window. Cloudflare must ask for an
e-mail first. If it shows anything else, do not share; fix step C.

### Add or remove a person

- **Add**: Access > Applications > `DR Screening demo` > **Configure** > **Policies** > `Invited team` >
  add the e-mail under **Include > Emails** > **Save**. Then create their DR Screening account on the
  Admin page of the app (they choose their own password at the first sign-in).
- **Remove**: the same place, delete the e-mail > **Save**. To end a session that is already open:
  **My Team > Users** (or **Team & Resources > Users**) > the person > **Revoke session**. Also disable or
  remove their DR Screening account on the Admin page.

## On your Windows PC

1. Install cloudflared once: open PowerShell and run `winget install --id Cloudflare.cloudflared`.
   (The start script never downloads anything itself; it only tells you this.)
2. In the demo settings file `%LOCALAPPDATA%\DRScreening\M1PrivateConfig\demo.env`, set
   `DR_IMAGES=public-samples` (or `public-folder` with `DR_PUBLIC_FOLDER` pointing at a folder of public
   images). The start script refuses `workspace`.
3. Start the demo with the **DR Screening Demo** desktop button and wait until it is ready.
4. Double-click `deployment\cloudflare-access\start-tunnel.bat`.
   - First time only: read the demo-data rule and type `YES`; paste the command copied in step B3
     (typing is hidden). The token is saved in `%LOCALAPPDATA%\DRScreening\cloudflare-tunnel.token`,
     readable only by your Windows account, and is never shown.
   - Keep the window open while the team uses the demo.
5. To stop sharing: close that window, or double-click `stop-tunnel.bat`. The demo app keeps running.

If the token ever leaks (for example in a screenshot or chat): in the dashboard delete the tunnel and
create a new one (step B), delete `%LOCALAPPDATA%\DRScreening\cloudflare-tunnel.token`, then double-click
`start-tunnel.bat` and paste the new command.

## Technical note: why the tunnel points at `http://127.0.0.1:8010`

The review app refuses any write (POST, PUT, ...) whose browser `Origin` differs from the address the app
believes it is served at (`same_origin` middleware in `dr_support/api/_factory.py`, comparing `Origin`
with `request.base_url`). Sign-in is a POST to `/v1/auth/login`, so this decides whether anyone can sign in.

- **Demo app on `http://127.0.0.1:8010` (chosen).** It runs under uvicorn with the default proxy settings
  (`scripts/qa/m1_server_app.py`: `uvicorn.run(app, host='127.0.0.1', ...)`), which trust
  `X-Forwarded-Proto` from `127.0.0.1`. cloudflared on the same PC connects from `127.0.0.1`, keeps the
  public `Host` (when the HTTP Host Header setting is empty) and passes Cloudflare's
  `X-Forwarded-Proto: https`. The app therefore sees `https://dr-demo.<your-domain>/`, which equals the
  browser's Origin, and accepts sign-in. No code or setting change is needed.
- **Docker web app behind Caddy (not used).** Caddy's site address there is `localhost`, so a request for
  `dr-demo.<your-domain>` is not routed to the app unless the tunnel rewrites the Host to `localhost`, and
  then the app sees `https://localhost/` and refuses the `https://dr-demo.<your-domain>` Origin with
  `403 Cross-origin mutation rejected`. Making it work would need a different `DR_SITE_ADDRESS` and
  cloudflared TLS options for the internal certificate; not set up or tested.

Proof: `tests/test_install_kits.py` starts the real review app under uvicorn on `127.0.0.1` with the same
arguments as the demo launcher and sends `POST /v1/auth/login` with `Host: dr-demo.example.test`,
`X-Forwarded-Proto: https` and `Origin: https://dr-demo.example.test`: sign-in and a following sign-out are
accepted. Without `X-Forwarded-Proto`, or with the Host rewritten to `localhost`, the same request gets 403.

Use `127.0.0.1`, not `localhost`, as the tunnel URL: the demo app listens on IPv4 only.
