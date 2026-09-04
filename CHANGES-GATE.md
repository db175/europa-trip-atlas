# Passphrase gate

Added 4 September 2026, on top of M3. Cache version `v4` → `v5`.

The site now asks for a passphrase before it opens. The passphrase is `123`,
set by `PASSPHRASE` at the top of `app.js`.

## Read this before relying on it

**This is a curtain, not access control.** It stops someone you hand the link
to from idly browsing 76 nights of your whereabouts. It protects nothing.

Three specific holes, all of them asserted in the test suite on purpose so this
cannot quietly be mistaken for security later:

1. **The repository is public**, so `app.js` is readable on github.com and the
   line `const PASSPHRASE = '123';` is right there.
2. **`data/trip-data.json` is served directly** at
   `https://db175.github.io/europa-trip-atlas/data/trip-data.json`. All 406
   places come back in one request that never loads `index.html` and never sees
   the gate. `data/my-places.json` is the same.
3. **The service worker has already cached both files** in the browser of
   anyone who has opened the site once.

A passphrase check implemented only in browser-side JavaScript exposes both the
check and the protected assets to the visitor. If the data ever needs actual
protection, the fix is an authenticating host in front of every file, such as
Cloudflare Pages with Cloudflare Access. GitHub's own Pages access control is
not an option here: private publication requires GitHub Enterprise Cloud, and
a private source repository does not make the published site private
(<https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/changing-the-visibility-of-your-github-pages-site>).

## How it behaves

- The **boot is gated, not the display.** `data/trip-data.json` is not
  requested at all until the passphrase is entered, so the curtain is not
  merely painted over content that already loaded.
- Unlock is stored in **`sessionStorage`, not `localStorage`**, so a reload in
  the same tab does not re-ask but closing the tab re-locks.
- **Deep links survive.** Opening `#city/ghent` shows the gate first, then
  lands on Ghent once unlocked.
- **Storage failures fail closed, not broken.** Private browsing can throw on
  `sessionStorage`; the gate then asks every time rather than locking you out.
- **Missing gate markup fails open.** If an old `index.html` is still cached
  and `#gate` is absent, `app.js` logs one warning and loads the site, rather
  than locking you out of your own plan on the day you need it.

## Changing or removing it

Change the passphrase: edit `PASSPHRASE` in `app.js`, bump `VERSION` in `sw.js`
and the `?v=` query strings in `index.html` and `SHELL_FILES`, then redeploy.
Without the bump the old service worker keeps serving the old `app.js`.

Remove it entirely: delete the `#gate` block from `index.html`. `app.js` treats
missing markup as "no gate" and boots straight through.

## One bug this caught

The first version had `.gate { display: flex }` with no `.gate[hidden]` rule.
`[hidden]` sets `display: none` at user-agent level, but an author rule beats
it, so the dismissed gate stayed invisible and full-screen and swallowed every
click on the page. Fixed, and there is now an assertion that the centre of the
page is clickable after unlocking.

## Verification

25 assertions for the gate, plus the M3 suite re-run at 82 of 82 with the gate
in the way. Covers: the gate holding on a fresh session, no data request before
unlock, a wrong passphrase clearing the field and showing an error, unlock
persisting across a reload, a new session re-locking, deep links honoured after
unlock, `sessionStorage` throwing, and the dismissed overlay not intercepting
clicks. The final two assertions fetch `data/trip-data.json` and `app.js`
directly over HTTP with no passphrase and confirm both come back, which is the
point of the warning above.
