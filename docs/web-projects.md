# Web projects and deployment

The hosted editors, the shared model server and the Voyager extension, with the
deployment pipeline and its limits. The [README](../README.md#live-sites) keeps the summary.

On narrow or portrait screens, header controls sit above the title and the side
panel starts collapsed. Open it with the yellow arrow to use Play or Input; it
fits within the screen. The editor remains primarily a desktop workspace.

| Project | Website | Role |
|---|---|---|
| **TheArtist-DAW — hackathon demo** | [artist-daw.pearlleestudio.co](https://artist-daw.pearlleestudio.co) | AI arrangement workspace: score/sketch → harmony and form → accompaniment → DAW |
| TheArtist — public release | [artist.pearlleestudio.co](https://artist.pearlleestudio.co) | Separately deployed release editor |
| **TheVoyager — project extension** | [voyager.pearlleestudio.co](https://voyager.pearlleestudio.co) | Travel globe, stories and photographs accompanied by generated music |

TheVoyager extends the music service into a travel experience: its Python adapter
requests a song through MCP `build_song` (or explicitly selected REST), then its
own rendering pipeline turns the arrangement into audio. The published Voyager
currently plays pre-generated WAV files; browser-triggered generation is not yet
connected. Voyager's application source and personal travel data are not bundled
in this repository. Its existing travel experience and model assets are separate
from the event contributions recorded in [HACKATHON.md](../HACKATHON.md).

The websites are published on Cloudflare Pages. Both Artist editors share one
Docker backend serving **all 18 released model choices** on DigitalOcean through
`https://music-api.pearlleestudio.co`. Actual generation passed for every model;
API checks on both editor domains passed vector-PDF import, streamed generation
and MIDI export.
Bounded Meta planning is enabled with a server-only key.
See [deployment, measurements and limits](../deploy/vps.md).
Public Git pushes update Pages automatically. The shared model server also polls
this repository's `main` branch and deploys runtime changes with health checks
and rollback; see [automatic deployment](../deploy/autodeploy.md).

Hosted **Open in Logic Pro** uses the [local Mac bridge](midi-input.md#open-a-hosted-score-in-logic-pro)
to deliver the generated MIDI to the user's Mac. The cloud server does not launch
desktop applications. Download MIDI remains available without the helper.

```text
Local edit → commit + push → public TheArtist-DAW/main
  ├─ Cloudflare Pages build → artist-daw.pearlleestudio.co
  └─ DigitalOcean checks Git → Docker build + health checks → music-api.pearlleestudio.co

Public TheArtist/main → Cloudflare Pages build → artist.pearlleestudio.co
Both Artist websites → /api/* → the shared model API above
```

Docker packages the server code, libraries and all 18 model choices. The API key
and persistent cost ledger stay outside the image. The server checks Git about
once a minute; documentation-only and frontend-only pushes do not restart it. Runtime replacement
briefly interrupts the API while models load. The release frontend follows its
own reviewed public snapshot; hackathon code is not automatically merged into it.

The Docker image includes MCP code, but public-host mode does not expose its MCP
endpoint. [Voyager's API/MCP deployment path](mcp.md#voyager-on-a-shared-host)
distinguishes the existing adapter from the remaining hosted integration.
