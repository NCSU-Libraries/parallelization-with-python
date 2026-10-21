/*
 * deck-sync.js: the deck includes this file (site/slides/index.qmd, include-after-body).
 *
 * An animation slide carries one empty fragment per beat after beat 0 and a background iframe (anim/<name>.html).
 * The current beat is the number of fragments that are visible on the current slide. On Reveal's ready, slidechanged,
 * fragmentshown and fragmenthidden events this file posts {type: "beat", n} to that slide's background iframe, and
 * anim.js there does the rest: forward one beat animates, anything else snaps.
 *
 * An iframe that has not loaded yet misses the message, so a message is posted again when the iframe loads, and when
 * the page announces itself with {type: "anim-ready"}. When the slide changes, keyboard focus goes back from the
 * animation's iframe to the deck. Each beat message is followed by {type: "box", x, y, w, h}: the slide box in the
 * iframe's pixels, for a deck opened from file:// where the iframe cannot read it from the deck.
 * It also hides (visually) the h2 of animation slides, because the page draws its own title.
 */
(function () {
  "use strict";

  const watched = new WeakSet();                       // iframes that already have a load listener
  let current = 0;                                     // the beat of the current slide

  const visibleFragments = slide => (slide ? slide.querySelectorAll(".fragment.visible").length : 0);

  function frameOf(slide) {
    const bg = slide && Reveal.getSlideBackground(slide);
    return bg ? bg.querySelector("iframe") : null;
  }

  // The slide box in the iframe's own pixels. anim.js reads it from the deck itself when it can; from file:// it cannot.
  function boxIn(frame) {
    const s = Reveal.getSlidesElement().getBoundingClientRect(), f = frame.getBoundingClientRect();
    return { type: "box", x: s.left - f.left, y: s.top - f.top, w: s.width, h: s.height };
  }

  function post(frame, slide) {
    try {
      frame.contentWindow.postMessage({ type: "beat", n: visibleFragments(slide) }, "*");
      frame.contentWindow.postMessage(boxIn(frame), "*");
    } catch (e) { /* the frame is gone */ }
  }

  function sync(slide) {
    slide = slide || Reveal.getCurrentSlide();
    current = visibleFragments(slide);
    const frame = frameOf(slide);
    if (!frame) return;
    if (!watched.has(frame)) {
      watched.add(frame);
      frame.addEventListener("load", () => post(frame, slide));      // also after reveal unloads and reloads it
    }
    post(frame, slide);
  }

  // The page draws its own title in the same place as the slide's h2, so the h2 stays for the outline and for screen
  // readers but is not drawn. (Remove this rule to show the deck's h2 instead and hide the page's .title.)
  const style = document.createElement("style");
  style.textContent = '.reveal .slides section[data-background-iframe^="anim/"] > h2 { position: absolute !important; ' +
    'width: 1px !important; height: 1px !important; margin: -1px !important; padding: 0 !important; border: 0 !important; ' +
    'overflow: hidden !important; clip: rect(0 0 0 0) !important; white-space: nowrap !important; }';
  document.head.appendChild(style);

  // A click inside an animation gives its iframe the keyboard, and anim.js forwards the keys to reveal. When reveal
  // leaves the slide it unloads that iframe, and a focused iframe with nothing in it swallows every key. Hand the
  // keyboard back to the deck.
  function releaseFocus() {
    const a = document.activeElement;
    if (a && a.tagName === "IFRAME" && a.closest(".slide-background")) a.blur();
  }

  function start() {
    Reveal.on("slidechanged", e => { releaseFocus(); sync(e.currentSlide); });
    Reveal.on("fragmentshown", () => sync());
    Reveal.on("fragmenthidden", () => sync());
    Reveal.on("resize", () => { const f = frameOf(Reveal.getCurrentSlide()); if (f) try { f.contentWindow.postMessage(boxIn(f), "*"); } catch (e) {} });
    addEventListener("message", e => {
      if (!e.data || e.data.type !== "anim-ready") return;
      for (const slide of Reveal.getSlides()) {
        const frame = frameOf(slide);
        if (frame && frame.contentWindow === e.source) {
          const fragments = slide.querySelectorAll(".fragment").length;
          if (fragments !== e.data.beats) console.warn(`deck-sync: slide #${slide.id} has ${fragments} fragments but ${frame.getAttribute("src") || frame.dataset.src} has ${e.data.beats} beats`);
          post(frame, slide);
          return;
        }
      }
    });
    window.DeckSync = { get beat() { return current; }, sync };      // for debugging
    sync();
  }

  if (window.Reveal && Reveal.isReady && Reveal.isReady()) start();
  else if (window.Reveal) Reveal.on("ready", start);
  else addEventListener("load", () => { if (window.Reveal) (Reveal.isReady() ? start() : Reveal.on("ready", start)); });
})();
