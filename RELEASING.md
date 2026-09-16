# Releasing Yearbirder

This describes how to cut a release so you can **test the Windows installer before
the public website goes live**.

## Why a release branch

A push to `master` triggers two independent things at once:

1. **GitHub Actions** (`.github/workflows/build-windows.yml`) builds `Yearbirder_Setup.exe`.
2. **Cloudflare Pages** redeploys the production site (`yearbirder.org`) — this only
   happens for the production branch, `master`.

The Windows binary is never published automatically either: the workflow uploads
`Yearbirder_Setup.exe` to the GitHub **Release** for the matching tag, and only if
that release already exists. No release, no public download. So the only thing that
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
   in `web/download.html`, plus any new screenshots. (The Windows button points at
   `releases/latest/download/Yearbirder_Setup.exe`, which always resolves to the newest
   release, so it needs no edit. GitHub still counts downloads per release even though
   the file name never changes — which is the point: it is the only per-version count
   the Windows installer has.)

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

6. **When the installer passes**, keep that downloaded artifact. You attach it to the
   Release in step 8 — which is what makes it public, and guarantees you ship the exact
   bytes you tested.

7. **Publish.** Merge the branch to `master`:

   ```
   git checkout master
   git merge --no-ff release/vX.YY
   git push
   ```

   This is the go-live: Cloudflare Pages redeploys `yearbirder.org`.

8. **Tag / GitHub Release — immediately after the merge.** Both download buttons now
   point at the Release, so both 404 between the merge and this step. Do not leave a gap.

   ```
   git tag vX.YY
   git push origin vX.YY
   gh release create vX.YY --title "Yearbirder vX.YY" --notes-file <notes> \
       dist/Yearbirder_vX.YY.dmg <the tested Yearbirder_Setup.exe>
   ```

   Attaching the tested `.exe` yourself closes the window where the release exists but
   the Windows asset does not. The master build re-uploads `Yearbirder_Setup.exe` and
   `.msix` with `--clobber` when it finishes (~8 minutes), which is harmless: identical
   code, and the `.msix` arrives that way.

## Ship exactly what you tested

The installer built from the branch and the one built after merging come from
identical code, so promoting the tested artifact is safe. Attaching the branch-built
artifact in step 8 ships the exact bytes you tested; the master build then overwrites
that asset with its own copy. If you want the tested bytes to be the ones that stay,
re-upload them after CI finishes:

```
gh release upload vX.YY <the tested Yearbirder_Setup.exe> --clobber
```

## The R2 bucket

`downloads.yearbirder.org` (R2 bucket `yearbirder-downloads`) served the Windows
installer until v2.16. Nothing advertises it now, but old links and anything written
about the app before then may still point at it, so the bucket is kept as a fallback —
refresh it when convenient rather than as a release step, or redirect the hostname to
`releases/latest/download/Yearbirder_Setup.exe` at the Cloudflare edge.

Why the move: R2 serves one fixed URL, so the file and the page advertising it went
stale independently, and the manual upload had to happen *before* the merge or the site
promised a version the bucket did not have. It also produced no usable download count —
requests there are dominated by `.env` scanners (204 requests, 200 of them 404s, in a
sampled 24 hours), while a GitHub release counts each asset download per version.
