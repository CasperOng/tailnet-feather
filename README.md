# tailnet feed

An AltStore/Feather source for unsigned **tailnet** builds.

The app repository builds an unsigned IPA on every push to `main` and keeps it at
a stable URL. `scripts/update_feed.py` pulls that IPA, reads its Info.plist, and
rewrites `apps.json`, `ipas/` and `LATEST-BUILD.md`.

## A private feed cannot be subscribed to by Feather

Feather fetches over plain HTTPS with no credentials, so it **cannot** read a
private repository. Two ways to use this:

1. **Download and sign locally** (works today, repo stays private):

   ```bash
   gh release download latest -R CasperOng/tailnet -p "*-unsigned.ipa"
   ```

   then open the IPA in Feather and sign it there.

2. **Make this repository public** so Feather can subscribe to
   `https://raw.githubusercontent.com/CasperOng/tailnet-feather/main/apps.json`.
   The apps and the engine stay private; only the built IPA and this feed would be
   public.

## Required secret

`SOURCE_TOKEN` — a fine-grained PAT with `contents: read` on
`CasperOng/tailnet`, because the rolling release is in a private repository.
