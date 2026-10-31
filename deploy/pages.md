# Cloudflare Pages

Connect the public `PearlLeeStudio/TheArtist-DAW` GitHub repository:

- Production branch: `main`
- Root directory: `frontend`
- Build command: `npm run build`
- Build output: `dist`
- Build variable: `NODE_VERSION=26.13.0` (LTS)
- Custom domain: `artist-daw.pearlleestudio.co`

The built editor is static. `public/_worker.js` forwards only `/api` requests
to the Python server configured by the Pages runtime variable `BACKEND_ORIGIN`,
an HTTPS origin without a path. The default is an explicit HTTP 503 until a
server is connected. No model inference runs inside Pages.

Deploy the Python server following [the server instructions](README.md), then
set `BACKEND_ORIGIN` and redeploy Pages. Keep Meta credentials on that server,
never in the frontend or Pages build variables. Streaming responses and session
budget headers pass through; browser cookies and credentials do not.

Both production Pages projects use
`BACKEND_ORIGIN=https://music-api.pearlleestudio.co` and **Fail closed**. The
setting is saved separately for `theartist-daw` and `theartist`; each was
redeployed with the new value. Both custom-domain API health checks, vector-PDF
import, streamed generation and MIDI download passed.

Check both `/` and `/api/health` through the custom domain. A working editor
alone does not verify AI generation. Test an actual F1 generation after the
server is connected.

Git pushes automatically rebuild the corresponding Pages frontend. Independently,
the model server polls this public repository's `main` branch about once a minute
and deploys runtime changes through Docker with health checks and rollback.
See [automatic model-server deployment](autodeploy.md). The public Artist release
repository updates only its own frontend; it does not replace the shared backend.

For command-line API checks, send a descriptive application `User-Agent`, such
as `TheArtistDeploymentCheck/1.0`. Cloudflare's Pages integrity check can reject
Python urllib's default agent with error 1010 before the API is reached.
[Cloudflare's 1010 guidance](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/).

Deploy the public release in a separate Git-connected Pages project from
`PearlLeeStudio/TheArtist` at `artist.pearlleestudio.co`. Keep its deployment
independent of this hackathon project. Retiring the hackathon deployment must
not remove the public release's domain or resources.

Routing follows Cloudflare's [advanced mode](https://developers.cloudflare.com/pages/functions/advanced-mode/)
and [route configuration](https://developers.cloudflare.com/pages/functions/routing/).
