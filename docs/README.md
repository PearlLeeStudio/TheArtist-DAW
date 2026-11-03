# TheArtist arrangement documentation

TheArtist connects score or chord-sketch input, harmonic revision, song form,
accompaniment and editable DAW delivery. Start with the
[arrangement workflow](arrangement-workflow.md) for the complete editor path.

| Task | Guide |
|---|---|
| Watch the hackathon demo | [TheArtist — From Chord Sketch to Your Own Music](https://youtu.be/wC-dkLfot-c) |
| Prepare the demo's cards and English captions | [Current demo copy](demo-subtitles.md) |
| Refer to the original timed version | [Original timeline](demo-timeline.md), [Original English SRT](demo-subtitles.en.srt) |
| Arrange from source material through DAW export | [Arrangement workflow](arrangement-workflow.md) |
| Look up a control, its limits and provenance rules | [Editor reference](editor-reference.md), [screenshots](walkthrough.md) |
| Read the recorded evaluation numbers and their conditions | [Evaluation evidence](evidence.md) |
| Compare local, Meta and hybrid on Reharmonize and Import | [Three-way model comparison: scores, costs and current-code limits](model-comparison.md) |
| See how the editor, backend and models fit together | [Architecture and module layout](architecture.md) |
| Check the served checkpoints, training data and theory sources | [Models, training data and theory sources](models.md) |
| Deploy the complete app with Docker, HTTPS and custom domains | [Web projects and deployment](web-projects.md#from-docker-to-the-public-domains) |
| Call the song service from Voyager or another client | [Voyager API quick start](voyager-api.md) |
| Review imported harmony, sections and source-data handling | [Score analysis](score-analysis.md) |
| Change selected harmony while preserving context | [Reharmonize: up to four changed chords](reharmonization.md) |
| Enter played chords or open a hosted arrangement in Logic | [MIDI input and Mac bridge](midi-input.md) |
| Understand related theory excerpts | [Theory retrieval](theory-retrieval.md) |
| Connect another client | [REST API](https://github.com/PearlLeeStudio/TheArtist-DAW/blob/6ed1b50914c78c205ee7aabdde924c648caf292d/API_SPEC.md), [MCP contracts](mcp.md) |
| Run the application | [Local setup](https://github.com/PearlLeeStudio/TheArtist-DAW/blob/6ed1b50914c78c205ee7aabdde924c648caf292d/README.md#getting-started), [backend](../backend/README.md), [hosting](../deploy/README.md) |
| Use the Logic MIDI FX export | [Logic Scripter](../plugin/logic-scripter/README.md) |
| Assess results and limits | [Evaluation](evaluation.md), [Reharmonization comparisons](reharmonization-evaluation.md), [score-reader comparisons](score-reader-comparison.md) |
| Verify an editing-to-DAW change | [Manual checks](manual-checks.md), [REST contracts](https://github.com/PearlLeeStudio/TheArtist-DAW/blob/6ed1b50914c78c205ee7aabdde924c648caf292d/API_SPEC.md), [MCP contracts](mcp.md) |

The product uses the author's Music Transformer and Meta models for harmonic
proposals, reading and decisions. Accompaniment patterns, voicings and file
rendering use application code. The [hackathon record](../HACKATHON.md)
distinguishes event work from the existing editor, trained models and research.
Historical experiments retain their original tasks and conditions; chord
prediction accuracy is evidence about a component, not a complete arrangement
quality score.
