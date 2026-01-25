/// <reference types="firefox-webext-browser" />

// Mozilla Readability library (injected before content.js)
declare class Readability {
  constructor(
    doc: Document,
    options?: {
      debug?: boolean;
      maxElemsToParse?: number;
      nbTopCandidates?: number;
      charThreshold?: number;
      classesToPreserve?: string[];
      keepClasses?: boolean;
      disableJSONLD?: boolean;
      serializer?: (el: Element) => string;
      allowedVideoRegex?: RegExp;
      linkDensityModifier?: number;
    },
  );
  parse(): {
    title: string;
    content: string;
    textContent: string;
    length: number;
    excerpt: string;
    byline: string | null;
    dir: string | null;
    siteName: string | null;
    lang: string | null;
    publishedTime: string | null;
  } | null;
}
