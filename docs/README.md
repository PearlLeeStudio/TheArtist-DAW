# TheArtist arrangement documentation

TheArtist connects score or chord-sketch input, harmonic revision, song form,
accompaniment and editable DAW delivery. Start with the
[arrangement workflow](arrangement-workflow.md) for the complete editor path.

| Task | Guide |
|---|---|
| Arrange from source material through DAW export | [Arrangement workflow](arrangement-workflow.md) |
| Review imported chords, note evidence and sections | [Score analysis](score-analysis.md) |
| Change selected harmony while preserving context | [Reharmonize: up to four changed chords](reharmonization.md) |
| Enter played chords or open a hosted arrangement in Logic | [MIDI input and Mac bridge](midi-input.md) |
| Understand related theory excerpts | [Theory retrieval](theory-retrieval.md) |
| Connect another client | [REST API](../API_SPEC.md), [MCP contracts](mcp.md) |
| Run the application | [Local setup](../README.md#getting-started), [backend](../backend/README.md), [hosting](../deploy/README.md) |
| Use the Logic MIDI FX export | [Logic Scripter](../plugin/logic-scripter/README.md) |
| Assess results and limits | [Evaluation](evaluation.md), [Reharmonization comparisons](reharmonization-evaluation.md), [score-reader comparisons](score-reader-comparison.md) |
| Verify an editing-to-DAW change | [Manual checks](manual-checks.md), [repository contracts](repository-checks.md) |

The product uses the author's Music Transformer and Meta models for harmonic
proposals, reading and decisions. Accompaniment patterns, voicings and file
rendering use application code. The [hackathon record](../HACKATHON.md)
distinguishes event work from the existing editor, trained models and research.
Historical experiments retain their original tasks and conditions; chord
prediction accuracy is evidence about a component, not a complete arrangement
quality score.
