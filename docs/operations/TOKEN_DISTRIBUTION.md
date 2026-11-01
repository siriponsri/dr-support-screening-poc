# Personal access to the team AI server: accounts and tokens

Owner approval: 31 October 2026 (personal tokens, restricted SSH accounts, private
network invitations; no devices added yet). Only public or consented images may be
sent to dr-train. Nothing here is done automatically by the app or by Claude Code.

## What each person gets

| Item | Who makes it | Where it lives | Never |
| --- | --- | --- | --- |
| SSH key pair | the person, on their own PC (`ssh-keygen -t ed25519`) | private key stays on their PC | send the private key to anyone |
| Restricted dr-train account `drgw-<name>` | dr-train administrator | dr-train | give it a shell or sudo |
| Personal model token | operator on dr-train | the person's `%LOCALAPPDATA%\DRScreening\M1PrivateConfig\personal-token.txt` | paste it in chat, email body, Git, logs or screenshots |
| Private network invitation | owner | Tailscale admin console | allow anything except dr-train SSH |

## Steps

1. **Person:** creates a key pair and sends only the public key (`id_ed25519.pub`) to the
   administrator.
2. **Administrator (on dr-train, with sudo):**
   `sudo sh scripts/model-server/admin/create-restricted-user.sh drgw-ann /tmp/ann.pub`
   The account can only forward a local port to `127.0.0.1:7860`.
3. **Operator (on dr-train, the project account):**
   ```bash
   P=/home/siripon/projects/dr-model-api-qa; D=$P/deployments/<current deployment>
   $P/environments/prism-qa-torch213/bin/python -I -B $D/scripts/model-server/regular_service.py \
     principal-add --principals $P/config/private/regular-principals.json --name ann --workstation ann-laptop
   ```
   The token is shown once in the operator's terminal. The running gateway reads the change
   on the next request (no restart). The file keeps only the token's SHA-256, the name and the allowed workstation IDs.
4. **Hand-over:** give the token in person or through a password manager's secure share,
   never by chat or email body. The person saves it as `personal-token.txt` in the private
   folder above (only their own Windows account can read that folder).
5. **Owner:** invites the person's device to the private network with a rule that allows
   only dr-train port 22 (when devices are added; none are added yet).
6. **Person:** in `demo.env` sets `DR_HOST=drgw-ann@<dr-train address>`,
   `DR_KEY=<path to their private key>`, `DR_TOKEN_FILE=<path to personal-token.txt>`,
   `DR_WORKSTATION=ann-laptop`, then uses the desktop button. With a personal token the
   launcher does not try to start the gateway; the operator keeps it running.

## Revoke

- Token: `regular_service.py principal-revoke --principals ... --name ann` (takes effect on the next request).
- Account: `sudo userdel --remove drgw-ann` (administrator).
- Device: remove it in the Tailscale admin console (owner).

## Notes

- Each person's tickets are recorded under `user:<name>`; one person cannot see or cancel
  another person's tickets. The owner's shared token keeps working for the owner only.
- Personal setups still need the M1 workspace setup on that PC (workspace, sign-in
  accounts, PRISM pins copy); see `docs/operations/TEAM_ACCESS_DR_TRAIN.md`.
- A personal token reaches only the service paths (status, tickets, grading, PRISM) and only from its
  listed workstations.
- Status: code and tests ready, running on dr-train since deployment `regular-20261031-r05`; no account,
  token or device has been created yet.
