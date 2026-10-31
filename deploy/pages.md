# Cloudflare Pages

Connect the public `PearlLeeStudio/TheArtist-DAW` GitHub repository:

- Production branch: `main`
- Root directory: `frontend`
- Build command: `npm run build`
- Build output: `dist`
- Build variable: `NODE_VERSION=25.9.0`
- Custom domain: `artist.pearlleestudio.co`

The built editor is static. `public/_worker.js` forwards only `/api` requests
to the Python server configured by the Pages runtime variable `BACKEND_ORIGIN`,
an HTTPS origin without a path. The default is an explicit HTTP 503 until a
server is connected. No model inference runs inside Pages.

Deploy the Python server following [the server instructions](README.md), then
set `BACKEND_ORIGIN` and redeploy Pages. Keep Meta credentials on that server,
never in the frontend or Pages build variables. Streaming responses and session
budget headers pass through; browser cookies and credentials do not.

Check both `/` and `/api/health` through the custom domain. A working editor
alone does not verify AI generation. Test an actual F1 generation after the
server is connected.

To switch to the post-hackathon public release, prepare and verify a separate
Git-connected Pages project from `PearlLeeStudio/TheArtist`, then move the custom
domain to it. Keep the current deployment available until that check passes.

Routing follows Cloudflare's [advanced mode](https://developers.cloudflare.com/pages/functions/advanced-mode/)
and [route configuration](https://developers.cloudflare.com/pages/functions/routing/).
