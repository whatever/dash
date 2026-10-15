// Copies the prebuilt ES modules out of node_modules into dist/ (served at /static/vendor/).
// Named *.js so every static server sends a JavaScript MIME type.
import { copyFileSync, mkdirSync } from "node:fs";

const files = {
  "marked/lib/marked.esm.js": "marked.esm.js",
  "dompurify/dist/purify.es.mjs": "purify.es.js",
};

mkdirSync("dist", { recursive: true });
for (const [from, to] of Object.entries(files)) copyFileSync(`node_modules/${from}`, `dist/${to}`);
