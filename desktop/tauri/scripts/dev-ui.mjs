import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const tauriRoot = resolve(__dirname, "..");
const rootDir = join(tauriRoot, "dist-ui");
const port = 1420;

const mimeTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};

const server = createServer((req, res) => {
  const urlPath = req.url === "/" ? "/index.html" : req.url || "/index.html";
  const resolvedPath = normalize(join(rootDir, urlPath));

  if (!resolvedPath.startsWith(rootDir) || !existsSync(resolvedPath) || statSync(resolvedPath).isDirectory()) {
    res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Not found");
    return;
  }

  const extension = extname(resolvedPath);
  res.writeHead(200, {
    "Cache-Control": "no-store",
    "Content-Type": mimeTypes[extension] || "application/octet-stream",
  });
  createReadStream(resolvedPath).pipe(res);
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Tauri UI dev server listening on http://127.0.0.1:${port}`);
});
