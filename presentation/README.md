# Team presentation

Double-click `PRESENT.cmd` in the project root (or open `presentation/index.html`) to show the 25-slide deck
in the default browser; it works offline. Keys (reveal.js): Right, Space or PageDown for the next step, Left
or PageUp to go back, Home and End, F for fullscreen, O or Esc for the slide overview, S for the speaker view
with the Thai notes (the speaker window may need the deck served from a local web server, for example
`python -m http.server` in this folder); the address ends in `#/N` for slide N. To edit, change the text
inside each `<section>` in `index.html`: `data-h="n"` is the headline shown at step n, `data-step="n"`
appears at step n, `data-in` appears when the slide opens, `data-cam` moves the diagram camera per step,
`data-fill` on a `.jbar` fills the 12-step journey bar, and `.pkt` circles travel along the path named in
`data-path`; `deck.js` turns these attributes into GSAP timelines, `deck.css` holds the colours and type.
Libraries are copied unmodified into `vendor/` with their licences: reveal.js 6.0.2 (MIT), GSAP 3.15.0
(GreenSock standard no-charge licence), Prompt and Anuphan fonts (SIL Open Font License, embedded as data
URIs). The retina pictures are illustrations; never add patient images.
