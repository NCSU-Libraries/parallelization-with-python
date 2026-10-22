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
 *
 * Autoplay, off by default. The A key turns it on and off (so does {type: "autoplay-toggle"} from the current slide's
 * frame: anim.js posts it when G is pressed inside the iframe), and ?autoplay turns it on for the whole visit;
 * ?autoplay=2500 also sets the pause in ms (default 1500). While it is on, an animation slide steps itself: when the
 * frame says {type: "beat-done", n} for the beat that is on screen, wait the pause, then show the next fragment.
 * It never changes slides: at the last step it stops and the presenter moves on. Arriving at an animation slide, or
 * turning autoplay on there, starts the chain after the pause (beat 0 is already on screen, so no beat-done comes). A
 * manual step backward pauses it for that slide until the slide changes. A pill, "▶ autoplay", sits at the bottom right
 * (where the logo is, on slides that show it) while autoplay is on and the slide is an animation.
 */
(function () {
  "use strict";

  const watched = new WeakSet();                       // iframes that already have a load listener
  let current = 0;                                     // the beat of the current slide

  let on = false;                                      // autoplay mode: it lasts across slides
  let pause = 1500;                                    // ms from a settled beat to the next fragment
  let timer = 0;                                       // the pending "next fragment"
  let held = null;                                     // the slide where a manual step backward paused autoplay
  let pill = null;

  // ?autoplay (on), ?autoplay=2500 (on, 2.5 s pause); ?autoplay=0, false, off or no is off.
  (function () {
    const q = new URLSearchParams(location.search);
    if (!q.has("autoplay")) return;
    const v = (q.get("autoplay") || "").trim().toLowerCase();
    if (v === "0" || v === "false" || v === "off" || v === "no") return;
    const ms = parseInt(v, 10);
    if (ms > 0) pause = ms;
    on = true;
  })();

  const visibleFragments = slide => (slide ? slide.querySelectorAll(".fragment.visible").length : 0);
  const hasHidden = slide => !!slide && !!slide.querySelector(".fragment:not(.visible)");
  const isAnim = slide => !!slide && /^anim\//.test(slide.getAttribute("data-background-iframe") || "");

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

  // ---- autoplay ----------------------------------------------------------------------------------------------------
  const clearTimer = () => { clearTimeout(timer); timer = 0; };

  // Wait the pause, then show the slide's next fragment if it has one. Each beat-done calls this again; changing the
  // slide, stepping by hand and turning autoplay off clear the wait.
  function arm(slide) {
    clearTimer();
    if (!on || held === slide || !isAnim(slide) || slide !== Reveal.getCurrentSlide() || !hasHidden(slide)) return;
    let busy = false;                                  // a beat still moving: its beat-done will call arm
    try { const f = frameOf(slide); busy = !!(f && f.contentWindow.__anim && f.contentWindow.__anim.busy); } catch (e) {}
    if (busy) return;
    timer = setTimeout(() => {
      timer = 0;
      if (on && held !== slide && slide === Reveal.getCurrentSlide() && hasHidden(slide)) Reveal.nextFragment();
    }, pause);
  }

  function updatePill() {
    if (pill) pill.hidden = !(on && isAnim(Reveal.getCurrentSlide()));
  }

  function toggle(e) {
    if (e && e.repeat) return;                         // a held key
    on = !on;
    held = null;
    clearTimer();
    updatePill();
    if (on) arm(Reveal.getCurrentSlide());
  }

  // The page draws its own title in the same place as the slide's h2, so the h2 stays for the outline and for screen
  // readers but is not drawn. (Remove this rule to show the deck's h2 instead and hide the page's .title.)
  // The autoplay pill uses the deck's palette (pale red, deep red) and the logo's corner (slides.scss).
  const style = document.createElement("style");
  style.textContent = '.reveal .slides section[data-background-iframe^="anim/"] > h2 { position: absolute !important; ' +
    'width: 1px !important; height: 1px !important; margin: -1px !important; padding: 0 !important; border: 0 !important; ' +
    'overflow: hidden !important; clip: rect(0 0 0 0) !important; white-space: nowrap !important; }' +
    '#autoplay-pill { position: fixed; right: 18px; bottom: 14px; z-index: 1100; padding: 3px 10px; border-radius: 999px; ' +
    'background: #FBE3E0; border: 1px solid #F2C4BE; color: #8A0000; ' +
    'font: 600 13px/1.4 Inter, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; letter-spacing: 0.02em; ' +
    'pointer-events: none; user-select: none; white-space: nowrap; }';
  document.head.appendChild(style);

  // A click inside an animation gives its iframe the keyboard, and anim.js forwards the keys to reveal. When reveal
  // leaves the slide it unloads that iframe, and a focused iframe with nothing in it swallows every key. Hand the
  // keyboard back to the deck.
  function releaseFocus() {
    const a = document.activeElement;
    if (a && a.tagName === "IFRAME" && a.closest(".slide-background")) a.blur();
  }

  function start() {
    pill = document.createElement("div");
    pill.id = "autoplay-pill";
    pill.setAttribute("role", "status");
    pill.hidden = true;
    pill.innerHTML = '<span aria-hidden="true">▶</span> autoplay';
    document.body.appendChild(pill);

    Reveal.on("slidechanged", e => { releaseFocus(); sync(e.currentSlide); held = null; updatePill(); arm(e.currentSlide); });
    Reveal.on("fragmentshown", () => { sync(); clearTimer(); });      // a step by hand: the next beat-done re-arms
    Reveal.on("fragmenthidden", () => { sync(); held = Reveal.getCurrentSlide(); clearTimer(); });
    Reveal.on("resize", () => { const f = frameOf(Reveal.getCurrentSlide()); if (f) try { f.contentWindow.postMessage(boxIn(f), "*"); } catch (e) {} });
    Reveal.addKeyBinding({ keyCode: 65, key: "A", description: "Autoplay the animation steps (toggle)" }, toggle);   // A, not G: G is reveal's "jump to slide"
    addEventListener("message", e => {
      const d = e.data;
      if (!d || typeof d !== "object") return;           // reveal's own messages are strings
      if (d.type === "anim-ready") {
        for (const slide of Reveal.getSlides()) {
          const frame = frameOf(slide);
          if (frame && frame.contentWindow === e.source) {
            const fragments = slide.querySelectorAll(".fragment").length;
            if (fragments !== d.beats) console.warn(`deck-sync: slide #${slide.id} has ${fragments} fragments but ${frame.getAttribute("src") || frame.dataset.src} has ${d.beats} beats`);
            post(frame, slide);
            return;
          }
        }
      } else if (d.type === "beat-done" || d.type === "autoplay-toggle") {
        const slide = Reveal.getCurrentSlide(), frame = frameOf(slide);
        if (!frame || frame.contentWindow !== e.source) return;          // only the slide on screen
        if (d.type === "autoplay-toggle") toggle();
        else if (on && isAnim(slide) && Number(d.n) === visibleFragments(slide)) arm(slide);
      }
    });
    window.DeckSync = { get beat() { return current; }, get autoplay() { return on; }, toggleAutoplay: toggle, sync };      // for debugging
    sync();
    updatePill();
    arm(Reveal.getCurrentSlide());                       // ?autoplay: start on the slide the deck opened at
  }

  if (window.Reveal && Reveal.isReady && Reveal.isReady()) start();
  else if (window.Reveal) Reveal.on("ready", start);
  else addEventListener("load", () => { if (window.Reveal) (Reveal.isReady() ? start() : Reveal.on("ready", start)); });
})();
