import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export const readJson = (file, fallback = undefined) => {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); }
  catch (error) {
    if (fallback !== undefined && error.code === "ENOENT") return fallback;
    throw new Error(`Cannot read JSON ${file}: ${error.message}`, { cause: error });
  }
};
export const sha256 = (data) => crypto.createHash("sha256").update(data).digest("hex");
export const posix = (value) => value.split(path.sep).join("/");
export const decodeEntities = (value) => value.replace(/&(?:#x([0-9a-f]+)|#(\d+)|(amp|lt|gt|quot|apos|nbsp));/gi, (_, hex, decimal, named) => {
  if (hex) return String.fromCodePoint(Number.parseInt(hex, 16));
  if (decimal) return String.fromCodePoint(Number.parseInt(decimal, 10));
  return { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " }[named.toLowerCase()];
});
export const visibleText = (html) => decodeEntities(String(html).replace(/<script\b[\s\S]*?<\/script>/gi, " ").replace(/<style\b[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
export const walk = (root) => !fs.existsSync(root) ? [] : fs.readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
  const item = path.join(root, entry.name);
  return entry.isDirectory() ? walk(item) : [item];
});
export const outputForUrl = (url) => {
  const pathname = new URL(url, "https://moltex.invalid").pathname;
  if (pathname === "/") return "index.html";
  if (pathname.endsWith(".html")) return pathname.slice(1);
  return `${pathname.replace(/^\//, "").replace(/\/$/, "")}/index.html`;
};
export const htmlAttributes = (html, element, attribute) => [...String(html).matchAll(new RegExp(`<${element}\\b[^>]*\\s${attribute}=["']([^"']+)["']`, "gi"))].map((match) => match[1]);
export const metaContent = (html, name) => String(html).match(new RegExp(`<meta\\b[^>]*(?:name|property)=["']${name}["'][^>]*content=["']([^"']*)["']`, "i"))?.[1] ?? null;
export const titleText = (html) => visibleText(String(html).match(/<title\b[^>]*>([\s\S]*?)<\/title>/i)?.[1] ?? "");
export const canonicalHref = (html) => String(html).match(/<link\b(?=[^>]*rel=["']canonical["'])[^>]*href=["']([^"']*)["']/i)?.[1] ?? null;
export const localTarget = (href) => {
  if (!href || href.startsWith("#") || /^(?:mailto:|tel:|data:|javascript:)/i.test(href)) return null;
  try {
    const parsed = new URL(href, "https://moltex.invalid");
    return parsed.origin === "https://moltex.invalid" ? parsed.pathname : null;
  } catch { return null; }
};
