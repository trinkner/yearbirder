# Releasing Yearbirder

This describes how to cut a release so you can **test the Windows installer before
the public website goes live**.

## Why a release branch

A push to `master` triggers two independent things at once:

1. **GitHub Actions** (`.github/workflows/build-windows.yml`) builds `Yearbirder_Setup.exe`.
2. **Cloudflare Pages** redeploys the production site (`yearbirder.org`) — this only
   happens for the production branch, `master`.

The Windows binary is never published automatically: `downloads.yearbirder.org/Yearbirder_Setup.exe`
only changes when **you upload it by hand** to Cloudflare. So the only thing that
goes public on its own is the website, and only on `master`.

By doing all release work on a `release/**` branch, the production site stays frozen
while you build and test. Cloudflare gives the branch a **preview URL** (a private
`*.pages.dev` address) instead of touching `yearbirder.org`, and GitHub Actions still
builds a fresh installer artifact (pushes to `release/**` build too — see the
workflow's `on:` triggers). The final **merge to `master`** is the one deliberate
"go live" step.

## Steps

1. **Create a release branch** off `master`:

   ```
   git checkout -b release/vX.YY
   ```

2. **Bump the version.** Update **both** fields in `src/code_MainWindow.py`
   (currently around lines 477–478):

   ```python
   versionNumber = "X.YY"
   versionDate   = "Month D, YYYY"
   ```

3. **Update the website** in `web/` — e.g. the version text and the macOS DMG link
   in `web/download.html`, plus any new screenshots. (The Windows button points at the
   stable `downloads.yearbirder.org/Yearbirder_Setup.exe` URL, so it needs no edit.)

4. **Commit and push the branch:**

   ```
   git push -u origin release/vX.YY
   ```

   The push auto-builds the Windows installer. (Or trigger it manually:
   Actions → **Build Windows Installer** → **Run workflow** → branch `release/vX.YY`.)

5. **Test in private, in parallel:**
   - **Installer:** open the workflow run → download the `Yearbirder-Windows-Setup`
     artifact → install and test the `.exe` on Windows.
   - **Website:** open the Cloudflare Pages **preview URL** for the branch and review
     the updated pages. Production is untouched.

6. **When the installer passes**, upload the tested `Yearbirder_Setup.exe` to Cloudflare
   (your normal manual step). The binary is now live; the site still shows the old
   version — that's expected.

7. **Publish.** Merge the branch to `master`:

   ```
   git checkout master
   git merge --no-ff release/vX.YY
   git push
   ```

   This is the go-live: Cloudflare Pages redeploys `yearbirder.org`.

8. **Tag / GitHub Release.** Create the `vX.YY` Release so the macOS DMG link resolves
   and the workflow attaches the built assets:

   ```
   git tag vX.YY
   git push origin vX.YY
   ```

   Then create the GitHub Release for that tag (the workflow's "Attach to Release"
   steps upload `Yearbirder_Setup.exe` and `.msix` once the release exists).

## Ship exactly what you tested

The installer built from the branch and the one built after merging come from
identical code, so promoting the tested artifact is safe. If you want to be strict
about shipping the exact bytes you tested, upload the **branch-built** artifact in
step 6 and don't rebuild after the merge.
