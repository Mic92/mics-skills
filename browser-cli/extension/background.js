/// <reference types="firefox-webext-browser" />

/**
 * Background script for Browser CLI Controller
 * Manages native messaging connection and message routing
 *
 * @typedef {object} NativeMessage
 * @property {boolean} [ready] - Whether the native messaging bridge is ready
 * @property {string} [socket_path] - Path to the Unix socket
 * @property {string} [command] - The command to execute
 * @property {CommandParams} [params] - Command parameters
 * @property {string} [id] - Unique message ID
 * @property {string} [tabId] - Target tab ID for the command
 * @property {FileChunk} [chunk] - One slice of a streamed file (read-files)
 *
 * @typedef {object} FileChunk
 * @property {number} file - Index into the requested paths array
 * @property {string} name - Basename of the file
 * @property {string} mime - Best-guess content type
 * @property {string} data - Base64 slice (3-byte-aligned, joinable)
 *
 * @typedef {object} Message
 * @property {string} command - The command to execute
 * @property {CommandParams} params - Command parameters
 * @property {string} id - Unique message ID
 * @property {string} [tabId] - Target tab ID for the command
 *
 * @typedef {object} CommandParams
 * @property {string} [url] - URL for navigation or new tab
 * @property {string} [tabId] - Tab ID for close-tab
 * @property {string} [code] - JavaScript code to execute
 * @property {string} [output_path] - Output path for screenshot
 * @property {string} [filename] - Filename for download
 */

/** @type {browser.runtime.Port|undefined} Native messaging port */
let nativePort;

/** @type {Record<string, {resolve: Function, reject: Function, chunk?: (c: FileChunk) => void}>} Message handlers from content scripts */
const messageHandlers = {};

/** @type {Map<string, {tabId: number, url: string, title: string}>} Map of managed tabs with short IDs */
const managedTabs = new Map();

/** @type {string|undefined} Currently active managed tab ID */
let activeTabId;

/** @type {number} Next sequential tab ID */
let nextTabId = 1;

/**
 * Generate a sequential numeric ID for tabs.
 * @returns {string}
 */
function generateTabId() {
  let id;
  do {
    id = String(nextTabId++);
  } while (managedTabs.has(id));
  return id;
}

/**
 * Connect to native messaging host
 */
function connectNativeHost() {
  if (nativePort) {
    return;
  }

  console.log("Connecting to native messaging host...");

  try {
    nativePort = browser.runtime.connectNative(
      "io.thalheim.browser_cli.bridge",
    );

    nativePort.onMessage.addListener(async (msg) => {
      const message = /** @type {NativeMessage} */ (msg);
      // Chunks can be 700KB each; logging them floods devtools and
      // pins memory until the console is cleared.
      if (!message.chunk) {
        console.log("Received from native host:", message);
      }

      if (message.ready && message.socket_path) {
        console.log(
          "Native messaging bridge ready, socket at:",
          message.socket_path,
        );
        return;
      }

      // Handle responses to our requests (e.g., save-screenshot, read-files)
      if (message.id && messageHandlers[message.id]) {
        const handler = messageHandlers[message.id];
        // Chunked transfers (read-files) send N chunk messages followed
        // by a final non-chunk completion. Keep the handler alive until
        // that final message arrives.
        if (message.chunk && handler.chunk) {
          handler.chunk(message.chunk);
          return;
        }
        delete messageHandlers[message.id];
        handler.resolve(message);
        return;
      }

      if (message.command) {
        await handleCommand(/** @type {Message} */ (message));
      }
    });

    nativePort.onDisconnect.addListener(() => {
      console.log("Native messaging disconnected");
      if (browser.runtime.lastError) {
        console.error("Native messaging error:", browser.runtime.lastError);
      }
      nativePort = undefined;
      setTimeout(connectNativeHost, 5000);
    });
  } catch (error) {
    console.error("Failed to connect to native messaging host:", error);
    nativePort = undefined;
  }
}

/**
 * Send response back to native host
 * @param {object} response
 */
function sendResponse(response) {
  if (nativePort) {
    try {
      nativePort.postMessage(response);
    } catch (error) {
      console.error("Failed to send response:", error);
    }
  }
}

/**
 * Get the browser tab ID to use for a command
 * @param {string} [targetTabId]
 * @returns {Promise<number>}
 */
async function getTargetTab(targetTabId) {
  if (targetTabId) {
    const managedTab = managedTabs.get(targetTabId);
    if (!managedTab) {
      throw new Error(
        `Tab ${targetTabId} not found. Use 'browser-cli --list' to see managed tabs.`,
      );
    }
    return managedTab.tabId;
  }
  // Fall back to active tab, but validate it still exists — activeTabId
  // can go stale after browser restart or when onRemoved didn't fire.
  if (activeTabId) {
    const managedTab = managedTabs.get(activeTabId);
    if (managedTab) {
      return managedTab.tabId;
    }
    activeTabId = undefined;
  }
  throw new Error(
    "No managed tab. Open one with 'browser-cli --go URL' or click the extension icon.",
  );
}

/** @type {number} Monotonic counter to disambiguate messages sent in the same millisecond. */
let contentMessageCounter = 0;

/**
 * Send command to content script
 * @param {string} command
 * @param {object} [params={}]
 * @param {string} [targetTabId]
 * @returns {Promise<object>}
 */
async function sendToContentScript(command, params = {}, targetTabId) {
  const tabId = await getTargetTab(targetTabId);

  return new Promise((resolve, reject) => {
    const messageId = `${Date.now()}_${++contentMessageCounter}`;
    messageHandlers[messageId] = { resolve, reject };

    browser.tabs.sendMessage(tabId, { command, params, messageId });

    setTimeout(() => {
      if (messageHandlers[messageId]) {
        delete messageHandlers[messageId];
        reject(new Error("Content script timeout"));
      }
    }, 30_000);
  });
}

// ============================================================================
// Browser-level commands (require background script)
// ============================================================================

/** URL schemes that content scripts cannot be injected into.
 *  executeScript() throws "Missing host permission" on these even with
 *  <all_urls> — they're hard-excluded by the WebExtension security model. */
const PRIVILEGED_URL_PREFIXES = [
  "about:",
  "moz-extension:",
  "chrome:",
  "resource:",
  "javascript:",
  "data:",
  "view-source:",
];

/**
 * Navigate a managed tab to a new URL and wait for load
 * @param {string} url - URL to navigate to
 * @param {string} [tabId] - Tab ID (defaults to active tab)
 * @returns {Promise<{url: string, tabId: string}>}
 */
async function navigate(url, tabId) {
  const blocked = PRIVILEGED_URL_PREFIXES.find((p) => url.startsWith(p));
  if (blocked) {
    throw new Error(
      `Cannot inject into ${blocked} URLs (browser security policy). Use http(s):// or file://`,
    );
  }

  let targetId = tabId;
  if (!targetId) {
    // Validate activeTabId before using it — it can go stale.
    if (activeTabId && managedTabs.has(activeTabId)) {
      targetId = activeTabId;
    } else {
      activeTabId = undefined;
      // No usable tab: create one. This makes `browser-cli --go URL`
      // work without requiring the user to first open a tab manually.
      const created = await createNewTab(url);
      return { url: created.url, tabId: created.tabId };
    }
  }

  const managedTab = managedTabs.get(targetId);
  if (!managedTab) {
    throw new Error(
      `Tab ${targetId} not found. Use 'browser-cli --list' to see managed tabs.`,
    );
  }

  const browserTabId = managedTab.tabId;

  // Navigate the tab
  await browser.tabs.update(browserTabId, { url });

  // Wait for page to load
  /** @type {Promise<void>} */
  const loadPromise = new Promise((resolve) => {
    /**
     * @param {number} updatedTabId
     * @param {{status?: string}} changeInfo
     */
    function listener(updatedTabId, changeInfo) {
      if (updatedTabId === browserTabId && changeInfo.status === "complete") {
        browser.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }
    browser.tabs.onUpdated.addListener(listener);

    // Timeout after 30 seconds
    setTimeout(() => {
      browser.tabs.onUpdated.removeListener(listener);
      resolve();
    }, 30_000);
  });

  await loadPromise;

  // Update stored URL
  managedTab.url = url;

  // Re-inject content script
  await enableOnTab(browserTabId, targetId);

  // Always include tabId so the CLI can print it even on the
  // existing-tab path (TAB=$(browser-cli --go ...) must always work).
  return { url, tabId: targetId };
}

/**
 * Navigate back
 * @param {string} [tabId]
 * @returns {Promise<{message: string}>}
 */
async function goBack(tabId) {
  const browserTabId = await getTargetTab(tabId);
  await browser.tabs.goBack(browserTabId);
  return { message: "Navigated back" };
}

/**
 * Navigate forward
 * @param {string} [tabId]
 * @returns {Promise<{message: string}>}
 */
async function goForward(tabId) {
  const browserTabId = await getTargetTab(tabId);
  await browser.tabs.goForward(browserTabId);
  return { message: "Navigated forward" };
}

/**
 * Take a screenshot
 * @param {string} [tabId]
 * @returns {Promise<{screenshot: string}>}
 */
async function takeScreenshot(tabId) {
  const browserTabId = await getTargetTab(tabId);
  await browser.tabs.update(browserTabId, { active: true });
  const dataUrl = await browser.tabs.captureVisibleTab();
  return { screenshot: dataUrl };
}

/**
 * Save screenshot by sending it through native messaging to the Python bridge
 * @param {string} dataUrl - The base64 data URL of the screenshot
 * @param {string} outputPath - The file path to save to
 * @returns {Promise<{screenshot_path: string, message: string}>}
 */
async function saveScreenshotToFile(dataUrl, outputPath) {
  if (!nativePort) {
    throw new Error(
      "Native messaging not connected - cannot save screenshot to file",
    );
  }

  // Send screenshot save request through native messaging
  const messageId = `screenshot_save_${Date.now()}`;

  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      delete messageHandlers[messageId];
      reject(new Error("Screenshot save timeout"));
    }, 30_000);

    messageHandlers[messageId] = {
      /** @param {{success?: boolean, result?: {screenshot_path: string, message: string}, error?: string}} response */
      resolve: (response) => {
        clearTimeout(timeout);
        if (response.success && response.result) {
          resolve(response.result);
        } else {
          reject(new Error(response.error || "Failed to save screenshot"));
        }
      },
      /** @param {Error} error */
      reject: (error) => {
        clearTimeout(timeout);
        reject(error);
      },
    };

    if (!nativePort) {
      reject(new Error("Native messaging disconnected"));
      return;
    }

    nativePort.postMessage({
      command: "save-screenshot",
      params: {
        screenshot: dataUrl,
        output_path: outputPath,
      },
      id: messageId,
    });
  });
}

/**
 * Read local files via the native bridge so content scripts can populate
 * <input type=file> without a user gesture. The extension itself has no
 * filesystem access; the Python bridge does the actual disk I/O.
 *
 * Native messaging caps app→extension messages at 1MB, so the bridge
 * streams files in chunks. We reassemble here per file index.
 *
 * @param {string[]} paths - Absolute paths on the local filesystem
 * @returns {Promise<{name: string, mime: string, data: string}[]>}
 */
async function readLocalFiles(paths) {
  if (!nativePort) {
    throw new Error("Native messaging not connected - cannot read files");
  }

  const messageId = `read_files_${Date.now()}`;
  /** @type {{name: string, mime: string, parts: string[]}[]} */
  const buffers = paths.map(() => ({ name: "", mime: "", parts: [] }));

  return new Promise((resolve, reject) => {
    // Timeout is sliding: any chunk arrival resets it. A 100MB file at
    // 700KB/chunk is ~150 messages; we don't want a fixed deadline.
    /** @type {ReturnType<typeof setTimeout>} */
    let timeout;
    const arm = () => {
      clearTimeout(timeout);
      timeout = setTimeout(() => {
        delete messageHandlers[messageId];
        reject(new Error("File read timeout (no data for 30s)"));
      }, 30_000);
    };
    arm();

    messageHandlers[messageId] = {
      /** @param {{file: number, name: string, mime: string, data: string}} c */
      chunk: (c) => {
        arm();
        const buf = buffers[c.file];
        buf.name = c.name;
        buf.mime = c.mime;
        buf.parts.push(c.data);
      },
      /** @param {{success?: boolean, error?: string}} response */
      resolve: (response) => {
        clearTimeout(timeout);
        if (response.success) {
          resolve(
            buffers.map((b) => ({
              name: b.name,
              mime: b.mime,
              data: b.parts.join(""),
            })),
          );
        } else {
          reject(new Error(response.error || "Failed to read files"));
        }
      },
      /** @param {Error} error */
      reject: (error) => {
        clearTimeout(timeout);
        reject(error);
      },
    };

    if (!nativePort) {
      reject(new Error("Native messaging disconnected"));
      return;
    }

    nativePort.postMessage({
      command: "read-files",
      params: { paths },
      id: messageId,
    });
  });
}

/**
 * List all managed tabs
 * @returns {Promise<{tabs: Array<{id: string, tabId: number, url: string, title: string, active: boolean}>}>}
 */
async function listTabs() {
  const tabs = [];
  const activeBrowserTab = await browser.tabs.query({
    active: true,
    currentWindow: true,
  });
  const activeBrowserTabId = activeBrowserTab[0]?.id;

  for (const [shortId, tab] of managedTabs) {
    try {
      const browserTab = await browser.tabs.get(tab.tabId);
      tabs.push({
        id: shortId,
        tabId: tab.tabId,
        url: browserTab.url || "",
        title: browserTab.title || "Untitled",
        active: browserTab.id === activeBrowserTabId,
      });
    } catch {
      managedTabs.delete(shortId);
      if (activeTabId === shortId) {
        activeTabId = undefined;
      }
    }
  }

  return { tabs };
}

/**
 * Create a new managed tab
 * @param {string} [url]
 * @returns {Promise<{tabId: string, url: string}>}
 */
async function createNewTab(url) {
  const shortId = generateTabId();
  const tabUrl = url || "about:blank";
  const tab = await browser.tabs.create({ url: tabUrl, active: true });

  if (tab.id === undefined) {
    throw new Error("Failed to create tab");
  }

  managedTabs.set(shortId, {
    tabId: tab.id,
    url: tabUrl,
    title: tab.title || "New Tab",
  });

  activeTabId = shortId;
  await enableOnTab(tab.id, shortId);

  return { tabId: shortId, url: tabUrl };
}

/**
 * Close a managed tab
 * @param {string} [tabId]
 * @returns {Promise<{message: string}>}
 */
async function closeTab(tabId) {
  const targetId = tabId || activeTabId;
  if (!targetId) {
    throw new Error("No tab to close");
  }

  const managedTab = managedTabs.get(targetId);
  if (!managedTab) {
    throw new Error(`Tab ${targetId} not found`);
  }

  await browser.tabs.remove(managedTab.tabId);
  managedTabs.delete(targetId);

  if (activeTabId === targetId) {
    activeTabId = managedTabs.keys().next().value;
  }

  return { message: `Closed tab ${targetId}` };
}

/**
 * Download a file
 * @param {string} url - URL to download
 * @param {string} [filename] - Filename (relative to downloads folder)
 * @returns {Promise<{downloaded: string, path: string}>}
 */
async function downloadFile(url, filename) {
  /** @type {browser.downloads._DownloadOptions} */
  const downloadOptions = {
    url,
    saveAs: false,
    filename: filename || undefined,
  };

  const downloadId = await browser.downloads.download(downloadOptions);

  // Wait for download to complete
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      browser.downloads.onChanged.removeListener(listener);
      reject(new Error("Download timeout"));
    }, 60_000);

    /**
     * @param {browser.downloads._OnChangedDownloadDelta} delta
     */
    function listener(delta) {
      if (delta.id !== downloadId) {
        return;
      }

      if (delta.state?.current === "complete") {
        clearTimeout(timeout);
        browser.downloads.onChanged.removeListener(listener);
        browser.downloads.search({ id: downloadId }).then((downloads) => {
          const path = downloads[0]?.filename || filename || "unknown";
          resolve({ downloaded: url, path });
        });
      } else if (delta.error) {
        clearTimeout(timeout);
        browser.downloads.onChanged.removeListener(listener);
        reject(new Error(delta.error.current));
      }
    }

    browser.downloads.onChanged.addListener(listener);
  });
}

// ============================================================================
// Command handling
// ============================================================================

/**
 * Handle commands from CLI
 * @param {Message} message
 */
async function handleCommand(message) {
  const { command, params, id, tabId } = message;

  try {
    let result;

    switch (command) {
      // Browser-level commands
      case "navigate": {
        result = await navigate(params.url || "", tabId);
        break;
      }
      case "back": {
        result = await goBack(tabId);
        break;
      }
      case "forward": {
        result = await goForward(tabId);
        break;
      }
      case "screenshot": {
        result = await takeScreenshot(tabId);
        break;
      }
      case "list-tabs": {
        result = await listTabs();
        break;
      }
      case "go": {
        if (!params.url) {
          throw new Error("go requires a URL");
        }
        result = await navigate(params.url, tabId);
        break;
      }
      case "close-tab": {
        result = await closeTab(params.tabId || tabId);
        break;
      }

      case "download": {
        result = await downloadFile(params.url || "", params.filename);
        break;
      }

      // Execute JavaScript in content script
      case "exec": {
        result = await sendToContentScript("exec", params, tabId);
        break;
      }

      default: {
        throw new Error(`Unknown command: ${command}`);
      }
    }

    sendResponse({ id, result, success: true });
  } catch (error) {
    sendResponse({
      id,
      error: error instanceof Error ? error.message : String(error),
      success: false,
    });
  }
}

// ============================================================================
// Tab management
// ============================================================================

/**
 * Enable extension on a specific tab
 * @param {number} tabId
 * @param {string} shortId
 */
async function enableOnTab(tabId, shortId) {
  // Inject Readability.js first, then content.js
  await browser.tabs.executeScript(tabId, { file: "Readability.js" });
  await browser.tabs.executeScript(tabId, { file: "content.js" });

  // Mark tab with title prefix instead of injecting a banner
  await browser.tabs.executeScript(tabId, {
    code: `(${function (/** @type {string} */ id) {
      if (!document._browserCliOriginalTitle) {
        document._browserCliOriginalTitle = document.title;
      }
      document.title = "🤖 " + id + " | " + document._browserCliOriginalTitle;
    }})('${shortId}')`,
  });

  connectNativeHost();
}

/**
 * Disable extension on a specific tab
 * @param {number} tabId
 * @param {string} shortId
 */
async function disableOnTab(tabId, shortId) {
  managedTabs.delete(shortId);
  if (activeTabId === shortId) {
    activeTabId = undefined;
  }

  await browser.tabs.executeScript(tabId, {
    code: `(${function () {
      if (document._browserCliOriginalTitle) {
        document.title = document._browserCliOriginalTitle;
        delete document._browserCliOriginalTitle;
      }
    }})()`,
  });
}

// ============================================================================
// Event listeners
// ============================================================================

browser.runtime.onMessage.addListener((message, sender, _sendResponse) => {
  // Handle disable CLI request
  if (message.command === "disableCLI" && sender.tab?.id !== undefined) {
    for (const [shortId, tab] of managedTabs) {
      if (tab.tabId === sender.tab.id) {
        disableOnTab(sender.tab.id, shortId);
        break;
      }
    }
    return true;
  }

  // Handle content script responses
  if (message.messageId && messageHandlers[message.messageId]) {
    const handler = messageHandlers[message.messageId];
    delete messageHandlers[message.messageId];

    if (message.error) {
      handler.reject(new Error(message.error));
    } else {
      handler.resolve(message.result);
    }
    return true;
  }

  // Handle content script requests for browser-level commands
  if (message.bgMessageId) {
    const { command, params, bgMessageId } = message;

    // Find the tab ID for this sender
    let senderTabShortId;
    if (sender.tab?.id !== undefined) {
      for (const [shortId, tab] of managedTabs) {
        if (tab.tabId === sender.tab.id) {
          senderTabShortId = shortId;
          break;
        }
      }
    }

    (async () => {
      try {
        let result;

        switch (command) {
          case "navigate": {
            result = await navigate(params.url, senderTabShortId);
            break;
          }
          case "back": {
            result = await goBack(senderTabShortId);
            break;
          }
          case "forward": {
            result = await goForward(senderTabShortId);
            break;
          }
          case "screenshot": {
            result = await takeScreenshot(senderTabShortId);
            // Save screenshot to file if path provided
            if (params.output_path && result.screenshot) {
              const dataUrl = result.screenshot;
              try {
                const saved = await saveScreenshotToFile(
                  dataUrl,
                  params.output_path,
                );
                result = saved;
              } catch (saveError) {
                result = {
                  error:
                    saveError instanceof Error
                      ? saveError.message
                      : String(saveError),
                  screenshot: dataUrl,
                };
              }
            }
            break;
          }
          case "download": {
            result = await downloadFile(params.url, params.filename);
            break;
          }
          case "read-files": {
            result = await readLocalFiles(params.paths);
            break;
          }
          default: {
            throw new Error(`Unknown background command: ${command}`);
          }
        }

        // Send response back to content script
        if (sender.tab?.id !== undefined) {
          browser.tabs.sendMessage(sender.tab.id, {
            bgMessageId,
            result,
          });
        }
      } catch (error) {
        if (sender.tab?.id !== undefined) {
          browser.tabs.sendMessage(sender.tab.id, {
            bgMessageId,
            error: error instanceof Error ? error.message : String(error),
          });
        }
      }
    })();

    return true;
  }

  return true;
});

browser.tabs.onActivated.addListener(async (activeInfo) => {
  for (const [shortId, tab] of managedTabs) {
    if (tab.tabId === activeInfo.tabId) {
      activeTabId = shortId;
      return;
    }
  }
  activeTabId = undefined;
});

browser.tabs.onRemoved.addListener((tabId) => {
  for (const [shortId, tab] of managedTabs) {
    if (tab.tabId === tabId) {
      managedTabs.delete(shortId);
      if (activeTabId === shortId) {
        activeTabId = undefined;
      }
      break;
    }
  }
});

browser.browserAction.onClicked.addListener(async (tab) => {
  // Take over the current tab instead of creating a new one
  if (tab.id === undefined) {
    // Fallback to creating a new tab if no current tab
    await createNewTab();
    return;
  }

  // Check if this tab is already managed
  for (const [shortId, managedTab] of managedTabs) {
    if (managedTab.tabId === tab.id) {
      // Already managed, just make it active
      activeTabId = shortId;
      return;
    }
  }

  // Take over this tab
  const shortId = generateTabId();
  managedTabs.set(shortId, {
    tabId: tab.id,
    url: tab.url || "about:blank",
    title: tab.title || "Untitled",
  });
  activeTabId = shortId;
  await enableOnTab(tab.id, shortId);
});

browser.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete") {
    for (const [shortId, managedTab] of managedTabs) {
      if (managedTab.tabId === tabId) {
        managedTab.url = tab.url || managedTab.url;
        managedTab.title = tab.title || managedTab.title;
        await enableOnTab(tabId, shortId);
        break;
      }
    }
  }
});

// Initialize
connectNativeHost();
