# Submitting Yearbirder to the Microsoft Store

**Verified in Partner Center on 2026-09-19** (account rtrinkner@icloud.com):

- The developer account is **enrolled** — Account settings → Identifiers shows
  Windows publisher ID `CN=E6F8B083-B39A-48F6-89D9-2B9B2585BC32`, which is where
  the manifest's value came from.
- The app **is now reserved**: "Yearbirder", MSIX or PWA app, status *In draft*.
  (It was not reserved before; the earlier attempt stopped at enrolment.)
- Partner Center assigned **Package/Identity/Name = `RichardTrinkner.Yearbirder`**
  — it prefixes the reserved name with the publisher display name. The manifest
  has been corrected to match. Do not change it back.
- Store ID: `9PKH7PL7F5G2`.  PFN: `RichardTrinkner.Yearbirder_5cnfkv8ek8hyr`.

The point of all this: the Store signs the package. An unsigned MSIX cannot be
installed by anyone — the whole reason the `.msix` has been useless for eight
releases. Nothing else about the package needs fixing: v2.17 was self-signed and
installed on the Windows 11 ARM VM, and the app ran correctly (web content,
photos, preferences).

---

## What you already have

| Needed | Status |
|---|---|
| Partner Center account | Yes — you have the login |
| Reserved app identity | Yes — `RichardTrinkner.Yearbirder`, Store ID 9PKH7PL7F5G2 |
| A built MSIX | Yes — CI produces `Yearbirder_Setup_vX.YY.msix` every push |
| Package tested | Yes — v2.17 installs and runs when signed |
| Privacy policy URL | Yes — https://yearbirder.org/privacy |
| Support contact | Yes — support@yearbirder.org (iCloud+ custom domain, live 2026-09-20) |
| Screenshots | Yes — reuse `web/images/demo_*.png` (1366x768 minimum) |
| Description text | Yes — adapt `web/index.html` or the BirdForum post |

So the work tomorrow is navigation and form-filling, not production.

---

## Step 1 — Identity (DONE, but re-check after any manifest edit)

Partner Center → the Yearbirder app → **Product management → Product Identity**.
These three must match `yearbirder.appxmanifest` exactly:

| Partner Center | Manifest |
|---|---|
| `RichardTrinkner.Yearbirder` | `<Identity Name=...>` |
| `CN=E6F8B083-B39A-48F6-89D9-2B9B2585BC32` | `<Identity Publisher=...>` |
| `Richard Trinkner` | `<PublisherDisplayName>` |

All three verified matching on 2026-09-19. Partner Center is authoritative and
cannot be edited — if they ever diverge, change the manifest.

## Step 2 — Check the account is ready to publish

Under **Account settings → Account details**, confirm the account is verified,
and under **Payout and tax** that the tax profile is complete. Microsoft blocks
publishing on an unverified account, and individual verification can take days —
so check this *before* preparing everything else.

Free apps still require the tax forms.

## Step 3 — Build the package to submit

Nothing new to write; use the CI artifact.

1. `gh run list --branch master --limit 3` — find the most recent successful
   *Build Windows Installer* run.
2. `gh run download <run-id> -n Yearbirder-Windows-MSIX -D ~/Downloads/msix`
3. That file is what you upload. Do **not** sign it yourself — the Store signs
   it, and a self-signed package is rejected.

If the version needs bumping first, cut the release as usual (`RELEASING.md`);
the MSIX version comes from `versionNumber` in `src/code_MainWindow.py`.

## Step 4 — Create the submission

In the app's dashboard: **Start new submission** (or **Submissions → New**).
Four sections need attention:

**Pricing and availability**
- Price: **Free**
- Markets: all, or restrict if you prefer
- Visibility: **Public**
- Device families: **Desktop** only (the manifest targets `Windows.Desktop`)

**Properties**
- Category: *Utilities & tools*, or *Education* — Utilities is the better fit
- Privacy policy URL: `https://yearbirder.org/privacy` (**required**, and a real
  policy — yours qualifies)
- Support contact info: `support@yearbirder.org`
- Website: `https://yearbirder.org`

**Age ratings**
A questionnaire, not a choice. Answer honestly: no user-generated content shared
between users, no ads, no data collection, no purchases. It will come out as
everyone/3+.

**Packages**
Upload the `.msix` from step 3. Errors here are almost always identity
mismatches — re-check step 4's three values against the manifest.

## Step 5 — Store listing

The part that takes the longest. Per language (en-us only, per the manifest):

- **Description** (up to 10,000 chars). Adapt the BirdForum post — it is already
  written for readers who do not know the app. Lead with what it does for a
  birder, not a feature list.
- **What's new in this version**: paste the current release's entry from
  `web/history.html`.
- **Screenshots**: 1–10, minimum 1366x768. `web/images/demo_AppMain.png` and
  friends are 4608x2592 and will downscale fine. Choose the visually distinctive
  ones — the maps, a photo grid, a spectrogram — rather than tables.
- **Short description** (up to 500 chars) — used in search results, so make the
  first sentence answer "what is this?".
- **Search terms**: eBird, birding, bird photography, life list, birdwatching,
  checklist, spectrogram.
- **Copyright**: © 2026 Richard Trinkner. **License terms**: GNU GPL v3, or link
  to https://www.gnu.org/licenses/gpl-3.0.html.

## Step 6 — Submit and wait

Certification usually takes a few hours to a couple of days. Failures come back
with a specific policy citation; the common ones for a package like this are a
missing or unreachable privacy policy, and screenshots that do not match the app.

On approval the Store publishes a signed package — that signature is the thing
you have been missing.

---

## After it is live

- Add a Store badge/link to `web/download.html` as a third Windows option,
  alongside the direct `.exe`.
- Decide whether the Store becomes the *recommended* Windows route. It would
  sidestep the SmartScreen warning the `.exe` shows every user, which is the
  most off-putting thing in the current Windows experience.
- Re-enable the MSIX attach step in `.github/workflows/build-windows.yml` only
  if you still want the raw package on GitHub releases; Store users never need
  it.
- Store submissions repeat per release: new version, new package upload, and the
  "What's new" text. Worth adding to `RELEASING.md` once the first one is done.

## Things that will waste your time if you forget them

- **Never create a second app reservation.** Identity mismatch is the single
  most common cause of rejected uploads.
- **Do not sign the package yourself** before uploading.
- **Account verification gates everything**, and is slow — check it first.
- **The version must increase** with every submission; the Store refuses a
  version it has seen before, even if the previous submission failed.
- **ProcessorArchitecture is x64.** ARM machines run it emulated, which is
  expected and fine, but do not promise ARM-native support in the listing.
