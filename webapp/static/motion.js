// Progressive enhancement only. Without this file (or under reduced motion, or
// before this runs), all content is fully visible — reveals just enhance an
// already-visible page and never gate visibility.
(function () {
  "use strict";
  var reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  var items = Array.prototype.slice.call(document.querySelectorAll("[data-reveal]"));

  function show(el) { el.classList.add("in"); }
  function showAll() { items.forEach(show); }

  // Reduced motion or no IntersectionObserver: reveal immediately, no animation.
  if (reduced || !("IntersectionObserver" in window) || !items.length) {
    showAll();
    return;
  }

  // Anything already in (or near) the first viewport reveals right away, so the
  // top of the page is never animated-from-blank; only below-fold items wait.
  var vh = window.innerHeight || 800;
  items.forEach(function (el) {
    if (el.getBoundingClientRect().top < vh * 1.1) show(el);
  });

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      var el = entry.target;
      var siblings = Array.prototype.slice.call(el.parentElement.querySelectorAll(":scope > [data-reveal]"));
      var i = Math.max(0, siblings.indexOf(el));
      el.style.transitionDelay = Math.min(i * 80, 320) + "ms";
      show(el);
      io.unobserve(el);
    });
  }, { rootMargin: "0px 0px 0px 0px", threshold: 0 });

  items.forEach(function (el) { if (!el.classList.contains("in")) io.observe(el); });

  // Failsafes: never leave content hidden if scroll never happens or IO stalls.
  // First scroll = reveal everything below the fold immediately, so a fast
  // scroller (or a snapshot/full-page capture) never catches a blank band.
  window.addEventListener("scroll", showAll, { once: true, passive: true });
  setTimeout(showAll, 1500);
})();
