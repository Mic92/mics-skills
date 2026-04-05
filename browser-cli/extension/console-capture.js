/// <reference types="firefox-webext-browser" />

/**
 * Early console capture — runs at document_start on every page.
 *
 * Patches the PAGE's console (not the content-script isolated world's)
 * via wrappedJSObject + exportFunction. This bypasses CSP because no
 * DOM <script> is injected, and catches logs emitted during page load
 * because it runs before any page script.
 *
 * Logs are buffered on the isolated-world window so that content.js
 * (injected later via tabs.executeScript) can read them. Both scripts
 * share the same isolated world for a given page.
 */

// Guard against double-injection (bfcache restore, SPA soft navigation)
// @ts-ignore - custom property
if (!window.__browserCliConsoleCapture) {
  /**
   * @typedef {object} ConsoleLog
   * @property {string} type
   * @property {string} message
   * @property {string} timestamp
   */

  /** @type {ConsoleLog[]} */
  const buffer = [];
  const MAX_LOGS = 1000;

  // Expose buffer to later-injected content.js via the shared isolated world.
  // @ts-ignore - custom property
  window.__browserCliConsoleCapture = buffer;

  /**
   * Serialize an argument the way DevTools would show it. Runs with
   * page-world values, so wrap in try/catch — hostile getters, proxies
   * and cyclic structures are all possible.
   * @param {unknown} arg
   * @returns {string}
   */
  function serialize(arg) {
    try {
      if (arg === null) {
        return "null";
      }
      if (arg === undefined) {
        return "undefined";
      }
      if (typeof arg === "object") {
        // Error objects have non-enumerable message/stack, so
        // JSON.stringify gives "{}". DevTools shows them via String().
        // Object.prototype.toString sees through Xray and matches
        // page-world Error/DOMException without instanceof games.
        const tag = Object.prototype.toString.call(arg);
        if (tag === "[object Error]" || tag === "[object DOMException]") {
          return String(arg);
        }
        return JSON.stringify(arg);
      }
      return String(arg);
    } catch {
      try {
        return String(arg);
      } catch {
        return "[unserializable]";
      }
    }
  }

  /**
   * @param {string} method
   * @param {unknown[]} args
   */
  function record(method, args) {
    buffer.push({
      type: method,
      message: args.map((a) => serialize(a)).join(" "),
      timestamp: new Date().toISOString(),
    });
    if (buffer.length > MAX_LOGS) {
      buffer.shift();
    }
  }

  // wrappedJSObject gives us the page-world globals without injecting
  // a <script>, so CSP never sees us. exportFunction is required to
  // hand a content-script function to page-world code without Xray
  // wrappers getting in the way.
  //
  // Both are Firefox-only. If we ever port to Chrome this whole file
  // needs the MAIN-world injection approach instead.
  const pageWindow = /** @type {any} */ (window).wrappedJSObject;
  if (pageWindow && typeof exportFunction === "function") {
    const pageConsole = pageWindow.console;

    for (const method of ["log", "error", "warn", "info", "debug"]) {
      const original = pageConsole[method];
      if (typeof original !== "function") {
        continue;
      }

      exportFunction(
        function (/** @type {unknown[]} */ ...args) {
          record(method, args);
          // `args` is a content-script-compartment Array. As of Firefox 149
          // page-world Function.prototype.apply can no longer read .length
          // on it through the Xray wrapper ("Permission denied to access
          // property 'length'"). The throw escapes to the page caller and
          // halts top-level script eval, which is how YouTube ended up
          // stuck on its skeleton page. Copy into a page-compartment Array
          // first; individual values pass through Xray fine even when they
          // are not structured-cloneable (functions, DOM nodes).
          const pageArgs = new pageWindow.Array();
          for (const arg of args) {
            pageArgs.push(arg);
          }
          return original.apply(pageConsole, pageArgs);
        },
        pageConsole,
        { defineAs: method },
      );
    }

    // Uncaught errors and promise rejections are the things you most
    // want when debugging, and they never go through console.* at all.
    pageWindow.addEventListener(
      "error",
      exportFunction(
        /** @param {ErrorEvent} e */
        function (e) {
          // capture:true also delivers <img>/<script>/<link> load failures.
          // Those events target the element rather than window and carry
          // no message/filename — uBlock alone produces dozens per page,
          // each one previously logging as "Uncaught undefined (...)".
          // e.message is the reliable discriminator; e.target identity
          // checks fail because pageWindow is Xray-unwrapped and event
          // targets come back wrapped.
          if (e.message === undefined) {
            const t = /** @type {any} */ (e.target);
            record("error", [
              `Resource load failed: <${t?.tagName?.toLowerCase()}> ${t?.src || t?.href || ""}`,
            ]);
            return;
          }
          record("error", [
            `Uncaught ${e.message} (${e.filename}:${e.lineno}:${e.colno})`,
          ]);
        },
        pageWindow,
      ),
      true,
    );

    pageWindow.addEventListener(
      "unhandledrejection",
      exportFunction(
        /** @param {PromiseRejectionEvent} e */
        function (e) {
          record("error", [`Unhandled rejection: ${serialize(e.reason)}`]);
        },
        pageWindow,
      ),
    );
  }
}
