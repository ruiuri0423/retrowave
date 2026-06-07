# RetroWave — Project Profile (for directories, SignPath, listings)

> Reusable English copy for submission forms (SignPath Foundation, software directories,
> award/OSS listings). Keep version-specific details out of the Description.

## Tagline

> A zero-dependency digital timing diagram editor with a retro Windows look — draw, group,
> annotate, and export publication-ready waveforms.

## Description

> RetroWave is an open-source (MIT) digital timing diagram editor for hardware engineers,
> educators, and students. You draw clock, logic-level, bus, and high-impedance waveforms
> directly on a period grid; organize signals into arbitrarily nested, collapsible groups;
> annotate timing relationships with measurement arrows; and export the result as crisp
> vector graphics (SVG/EPS), high-resolution raster images (PNG), or the WaveDrom
> interchange format. The application is written in pure Python on the standard library's
> Tk toolkit, so it runs from source with no third-party dependencies. Internally it follows
> a strictly layered architecture — document core, command/undo transfer layer, headless
> rendering, and a thin UI shell — documented in a full design specification and enforced
> by an automated test suite. Windows binaries are built reproducibly from tagged releases
> by GitHub Actions; code signing lets those binaries reach end users without SmartScreen
> friction.

## Reputation (evidence list — update links as they materialize)

Honest framing for a young project: lead with verifiable engineering quality, then add
community traction links as they accumulate.

- **Public development**: full history, issues, and CI at
  <https://github.com/ruiuri0423/retrowave>
- **Quality gates**: 100+ automated tests (unit + GUI-gesture + architecture-boundary)
  run in CI on every tagged release *before* binaries are built —
  <https://github.com/ruiuri0423/retrowave/actions>
- **Documentation**: a complete, language-agnostic design specification
  (`docs/RetroWave_Design.md`) covering the data model, invariants, rendering
  algorithms, a UI↔core command protocol, and a per-version changelog
- **License & integrity**: MIT; releases ship `SHA256SUMS.txt`; binaries built only by
  GitHub Actions from public source — <https://github.com/ruiuri0423/retrowave/releases>
- **Interoperability**: exports the de-facto community WaveDrom JSON format
- *(add after posting)* community threads: Show HN, r/FPGA, r/Python, EEVblog forum
- *(add as they grow)* GitHub stars/forks insights, release download counts

## Outreach checklist (turns assets into reputation)

1. README hero image + animated demo (already in place: `assets/hero.png`, `assets/demo.gif` —
   both produced by RetroWave's own export pipeline, which is itself proof of the product's capability)
2. Publish the first GitHub Release (including exe + zip + checksums)
3. Show HN ("Show HN: RetroWave – a retro-style digital timing diagram editor in pure
   Python/Tk"), Reddit r/FPGA, r/Python, EEVblog; add the thread links to the list above
4. Submit an interoperability entry to WaveDrom-related discussions / awesome-lists
5. After accumulating 2–3 external links and some initial download numbers, submit the SignPath application (higher approval rate)
