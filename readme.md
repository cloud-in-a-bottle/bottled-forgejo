# bottled-forgejo

[Forgejo](https://codeberg.org/forgejo/forgejo) is a self-hosted Git forge
(code hosting, issues, pull requests, wikis). This repository packages it as a
Cloud in a Bottle app.

## What you get

- Forgejo running on `https://forgejo.<zone>/`.
- Public landing page: anyone can browse public repos and the explore page.
- Owner logged in as admin automatically via Cloud in a Bottle SSO.
- Invited users log in with Forgejo-local passwords (accounts created by the
  admin).
- Walk-in registration disabled. New accounts require admin action.
- Git over SSH on port 2222 with SSH keys, or HTTPS with personal access tokens.
- Issues, pull requests, releases, wikis, webhooks, organizations.

## Usage

Open `https://forgejo.<zone>/`. As the Cloud in a Bottle owner you are logged
in automatically as the admin user. Your Forgejo username matches your Cloud in
a Bottle username.

To invite collaborators:

1. Go to Site Administration, User Accounts, Create User Account.
2. Set a temporary password and hand it to the user out of band.
3. They log in at `/user/login` and change the password in their settings.

For Git over HTTPS, create a personal access token under Settings,
Applications, then use it as the password when cloning or pushing.

### Git over SSH

Add your public SSH key under Settings, SSH / GPG Keys, then copy the SSH clone
URL from your repository. For example:

```sh
git clone ssh://git@forgejo.<zone>:2222/your-username/your-repository.git
```

SSH authenticates with your Forgejo account's keys and repository permissions.
The SSH username is always `git`, including for the Cloud in a Bottle owner.
Port 2222 connects directly to the app's OpenSSH server; the instance's
administrative SSH remains on port 22. The SSH server's host keys and your
registered keys persist across app updates and restarts.

The instance must accept inbound TCP connections on port 2222. HTTP-only
tunnels do not carry SSH traffic. If you change the published `ssh` port when
installing the app, set `FORGEJO__server__SSH_PORT` to the same number in
`$OPENHOST_APP_DATA_DIR/openhost.env` and reload the app so its clone URLs match.

## Caveats

- Port 2222 must be available on the instance for the default SSH mapping.
- No SMTP configured. Email features (activation links, password reset,
  notification delivery) do not work without adding SMTP settings.
- Walk-in registration returns 403. Accounts must be admin-created.

## Data

All persistent data lives under `$OPENHOST_APP_DATA_DIR/`:

- `gitea/forgejo.db`: SQLite database (users, repos, issues, settings)
- `gitea/conf/app.ini`: effective configuration
- `git/repositories/`: bare git repos
- `git/.ssh/authorized_keys`: registered SSH keys with restricted Git commands
- `ssh/`: SSH server host keys
- `.secret_key`: generated on first boot, persisted

## Resources

About 512 MB RAM and 0.5 CPU cores.

## License

Forgejo is licensed under the GNU General Public License v3.0 (GPL-3.0). The
container image built from this repo is distributed under that license. The
packaging files original to this repository are additionally available under the
MIT License. See LICENSE and NOTICE for details.
