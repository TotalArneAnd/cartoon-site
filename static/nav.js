// nav.js — keyboard arrows and touch swipe to move between cartoons.
// The Previous/Next buttons themselves are rendered server-side as
// <a class="arrow arrow-prev/next" href="..."> (or a .is-off span when
// there is nowhere to go). This script only wires the keyboard and
// swipe gestures to those existing links. No framework, no globals.

(function () {
  "use strict";

  function hrefOf(selector) {
    var a = document.querySelector(selector);
    return a && a.getAttribute("href");
  }

  function go(href) {
    if (href) window.location.href = href;
  }

  // Keyboard arrows. Ignore when a modifier is held or a field is focused.
  document.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    var tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.target.isContentEditable) return;
    if (e.key === "ArrowLeft") go(hrefOf("a.arrow-prev"));
    else if (e.key === "ArrowRight") go(hrefOf("a.arrow-next"));
  });

  // Touch swipe on the cartoon stage. Swipe left -> newer, swipe right -> older.
  var stage = document.querySelector(".stage");
  if (!stage) return;
  var startX = 0, startY = 0, tracking = false;

  stage.addEventListener("touchstart", function (e) {
    if (e.touches.length !== 1) { tracking = false; return; }
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    tracking = true;
  }, { passive: true });

  stage.addEventListener("touchend", function (e) {
    if (!tracking) return;
    tracking = false;
    var t = e.changedTouches[0];
    var dx = t.clientX - startX;
    var dy = t.clientY - startY;
    // Need a clear horizontal swipe, larger than the vertical drift.
    if (Math.abs(dx) < 45 || Math.abs(dx) <= Math.abs(dy)) return;
    if (dx < 0) go(hrefOf("a.arrow-next"));
    else go(hrefOf("a.arrow-prev"));
  }, { passive: true });
})();
