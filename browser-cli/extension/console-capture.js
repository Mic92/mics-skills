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
          return original.apply(pageConsole, args);
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
