import fs from "node:fs";
import path from "node:path";
import { checkResult } from "../results.mjs";
import { canonicalHref, htmlAttributes, localTarget, metaContent, outputForUrl, readJson, sha256, titleText, visibleText, walk, posix } from "../files.mjs";
import { verifyContractReceipts } from "../contracts.mjs";

const result = (checkId, subject, ok, details = {}) => checkResult({
  checkId,
  subject,
  status: ok ? "pass" : (details.status ?? "fail"),
  severity: ok ? "info" : (details.severity ?? "critical"),
  contractIds: details.contractIds ?? [],
  evidenceRefs: details.evidenceRefs ?? [],
  expected: details.expected ?? true,
  actual: details.actual ?? ok,
  message: ok ? (details.passMessage ?? `${checkId} passed`) : details.message,
  artifacts: details.artifacts ?? [],
});

export const contractChecks = (contracts) => {
  const errors = verifyContractReceipts(contracts);
  const idGroups = [
    contracts.routes.map((item) => item.contract_id), contracts.assets.map((item) => item.asset_id),
    contracts.seo.map((item) => item.contract_id), contracts.redirects.map((item) => item.contract_id),
    contracts.capabilities.map((item) => item.capability_id), contracts.parity.map((item) => item.row_id),
    contracts.legacyEvidence.map((item) => item.contract_id),
  ];
  if (idGroups.some((ids) => new Set(ids).size !== ids.length)) errors.push("duplicate contract ID");
  const expectedParity = new Set([
    ...contracts.routes.filter((item) => item.public).map((item) => `route:${item.contract_id}`),
    ...contracts.capabilities.map((item) => `capability:${item.capability_id}`),
  ]);
  const actualParity = contracts.parity.map((item) => item.subject_type === "route" ? `route:${item.route_contract_id}` : `capability:${item.capability_id}`);
  if (new Set(actualParity).size !== actualParity.length || actualParity.some((item) => !expectedParity.has(item)) || [...expectedParity].some((item) => !actualParity.includes(item))) errors.push("parity coverage mismatch");
  const resolutionIds = new Set((contracts.index.evidence_resolutions ?? []).map((item) => item.evidence_id));
  const collectEvidence = (value, found = []) => {
    if (Array.isArray(value)) value.forEach((item) => collectEvidence(item, found));
    else if (value && typeof value === "object") {
      if (typeof value.evidence_id === "string") found.push(value.evidence_id);
      Object.values(value).forEach((item) => collectEvidence(item, found));
    }
    return found;
  };
  const unresolved = collectEvidence([contracts.sourceManifest, contracts.siteSpec, contracts.routes, contracts.assets, contracts.seo, contracts.redirects, contracts.capabilities, contracts.legacyEvidence, contracts.parity]).filter((id) => !resolutionIds.has(id));
  if (unresolved.length) errors.push(`unresolved evidence lineage ${[...new Set(unresolved)].slice(0, 3).join(",")}`);
  return [result("contract.integrity", contracts.sourceManifest.bundle_id, errors.length === 0, {
    contractIds: [contracts.sourceManifest.manifest_id], evidenceRefs: [".moltex/contracts/contract-index.json"],
    expected: { checksum_errors: 0 }, actual: { checksum_errors: errors.length },
    message: `Contract integrity failed: ${errors.join(", ")}`, passMessage: "All indexed contracts match their committed receipts",
  })];
};

export const legacyEvidenceChecks = (contracts) => {
  const capabilityIds = new Set(contracts.capabilities.map((item) => item.capability_id));
  const decisionIds = new Set(contracts.decisions.map((item) => item.decision_id));
  const html = walk("dist").filter((file) => file.endsWith(".html")).map((file) => fs.readFileSync(file, "utf8")).join("\n");
  return contracts.legacyEvidence.flatMap((item) => {
    const acquisitionValid = item.disposition !== "acquire" || (item.payload_status === "deferred" && !item.payload_artifact && capabilityIds.has(item.capability_id));
    const dormantValid = item.classification !== "dormant" || (item.disposition === "audit" && !["included", "sampled"].includes(item.payload_status) && !item.capability_id && !item.decision_id);
    const decisionValid = item.disposition !== "decide" || (capabilityIds.has(item.capability_id) && decisionIds.has(item.decision_id));
    const disposition = result("legacy.evidence-disposition", item.contract_id, acquisitionValid && dormantValid && decisionValid, {
      contractIds: [item.contract_id, item.capability_id].filter(Boolean), evidenceRefs: [`.moltex/contracts/contracts/legacy-evidence.json#${item.contract_id}`],
      expected: "an auditable relevance and acquisition disposition", actual: { classification: item.classification, disposition: item.disposition, payload: item.payload_status },
      message: `Legacy evidence disposition is inconsistent: ${item.contract_id}`,
    });
    if (item.disposition !== "decide" || !["shortcode", "block"].includes(item.artifact_type)) return [disposition];
    const placeholder = html.includes(`data-moltex-evidence="${item.source_evidence_id}"`);
    return [disposition, result("legacy.placeholder", item.contract_id, placeholder, {
      contractIds: [item.contract_id, item.capability_id].filter(Boolean), evidenceRefs: [`.moltex/contracts/contracts/legacy-evidence.json#${item.contract_id}`],
      expected: item.source_evidence_id, actual: placeholder, message: `Referenced orphan has no localized generated placeholder: ${item.contract_id}`,
    })];
  });
};

export const buildChecks = (contracts) => {
  const expected = new Set(contracts.expectations.routes.map((route) => route.output));
  expected.add("404.html");
  const actual = new Set(walk("dist").filter((file) => file.endsWith(".html")).map((file) => posix(path.relative("dist", file))));
  const missing = [...expected].filter((item) => !actual.has(item)).sort();
  const unexpected = [...actual].filter((item) => !expected.has(item)).sort();
  const sensitive = walk("dist").filter((file) => /\.(?:html|css|js|json|xml|txt)$/i.test(file)).flatMap((file) => {
    const value = fs.readFileSync(file, "utf8");
    return /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|\bsk-[a-z0-9_-]{20,}\b|(?:password|api[_-]?key)\s*[=:]\s*[^\s"']{8,}/i.test(value) ? [posix(path.relative("dist", file))] : [];
  });
  return [result("build.output-inventory", "dist", missing.length === 0 && unexpected.length === 0 && sensitive.length === 0, {
    contractIds: contracts.publishedRoutes.map((route) => route.contract_id),
    evidenceRefs: [".moltex/verification/baseline-expectations.json"], expected: [...expected].sort(), actual: [...actual].sort(),
    message: `Build integrity differs; missing=${missing.join(",") || "none"}; unexpected=${unexpected.join(",") || "none"}; sensitive=${sensitive.join(",") || "none"}`,
    artifacts: [".moltex/reports/built-route-inventory.json"], passMessage: `Build contains exactly ${actual.size} expected HTML outputs`,
  })];
};

export const routeAndContentChecks = (contracts) => contracts.publishedRoutes.flatMap((route) => {
  const file = path.join("dist", ...route.output_path.split("/"));
  const exists = fs.existsSync(file);
  const html = exists ? fs.readFileSync(file, "utf8") : "";
  const article = html.match(/<article\b[^>]*>([\s\S]*?)<\/article>/i)?.[1] ?? "";
  const text = visibleText(article);
  const missingMarkers = route.required_content_markers.filter((marker) => !text.includes(visibleText(marker)));
  return [
    result("route.expected-output", route.target_url, exists, {
      contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`],
      expected: { status: route.expected_status, output: route.output_path }, actual: { output_exists: exists, output: route.output_path },
      message: `Expected route output is missing: ${route.output_path}`,
    }),
    result("content.required-marker", route.target_url, exists && missingMarkers.length === 0, {
      status: exists ? "fail" : "blocked", contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`],
      expected: route.required_content_markers, actual: { missing: missingMarkers },
      message: exists ? `Missing required markers: ${missingMarkers.join(", ")}` : "Marker check blocked by missing route output",
    }),
  ];
});

export const completionChecks = (contracts) => {
  const routeChecks = contracts.publishedRoutes.map((route) => {
    const file = path.join("dist", ...route.output_path.split("/"));
    const html = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
    const markers = [
      ...html.matchAll(/class=["'][^"']*\bmoltex-placeholder\b[^"']*["']/gi),
      ...html.matchAll(/data-moltex-dynamic-block=["'][^"']+["']/gi),
      ...html.matchAll(/block requires replacement|Form requires integration/gi),
    ].map((match) => match[0]);
    return result("content.no-unresolved-placeholder", route.target_url, markers.length === 0, {
      contractIds: [route.contract_id],
      evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`, file],
      expected: [], actual: markers,
      message: `Published route contains unresolved migration markers: ${markers.join(", ")}`,
      passMessage: "Published route contains no unresolved migration markers",
    });
  });
  const blocking = contracts.decisions.filter((item) => item.severity === "blocking");
  routeChecks.push(checkResult({
    checkId: "decision.resolved",
    status: blocking.length ? "needs_decision" : "pass",
    severity: blocking.length ? "critical" : "info",
    subject: "decision-queue",
    contractIds: blocking.map((item) => item.decision_id),
    evidenceRefs: [".moltex/contracts/decision-queue.json"],
    expected: [],
    actual: blocking.map((item) => item.decision_id),
    message: blocking.length ? "Blocking migration decisions remain unresolved" : "No blocking migration decisions remain",
  }));
  return routeChecks;
};

export const assetChecks = (contracts) => {
  const required = contracts.publishedAssets;
  const checks = required.flatMap((asset) => {
    const file = asset.target_path.startsWith("public/") ? path.join("dist", asset.target_path.slice(7)) : path.join("dist", asset.target_path);
    const exists = fs.existsSync(file);
    const digest = exists ? sha256(fs.readFileSync(file)) : null;
    return [
    result("asset.local-exists", asset.asset_id, exists, {
      contractIds: [asset.asset_id], evidenceRefs: [`.moltex/contracts/contracts/assets.json#${asset.asset_id}`],
      expected: asset.target_path, actual: exists ? file : null, message: `Required local asset is missing: ${asset.target_path}`,
    }),
    result("asset.checksum", asset.asset_id, exists && (!asset.checksum || digest === asset.checksum), {
      status: exists ? "fail" : "blocked", contractIds: [asset.asset_id], evidenceRefs: [`.moltex/contracts/contracts/assets.json#${asset.asset_id}`],
      expected: asset.checksum, actual: digest, message: exists ? "Local asset checksum differs from contract" : "Checksum blocked by missing asset",
    }),
    ];
  });
  const assetsById = new Map(required.map((item) => [item.asset_id, item]));
  const failures = [];
  for (const file of walk("dist").filter((item) => item.endsWith(".html"))) {
    const html = fs.readFileSync(file, "utf8");
    if (/(?:src|srcset)=["'][^"']*https?:\/\//i.test(html)) failures.push(`${posix(path.relative("dist", file))}: production hotlink`);
    for (const tag of html.match(/<img\b[^>]*>/gi) ?? []) {
      const id = tag.match(/data-asset-id=["']([^"']+)["']/i)?.[1];
      if (!id) continue;
      const asset = assetsById.get(id);
      const alt = tag.match(/\salt=["']([^"']*)["']/i)?.[1] ?? null;
      if (!asset) failures.push(`${id}: undeclared rendered asset`);
      else if (alt !== (asset.alt_text ?? "")) failures.push(`${id}: alt text differs`);
    }
  }
  const compatible = { "image/png": [".png"], "image/jpeg": [".jpg", ".jpeg"], "image/gif": [".gif"], "image/webp": [".webp"], "image/svg+xml": [".svg"] };
  for (const asset of required) {
    const extensions = compatible[asset.mime_type];
    if (extensions && !extensions.includes(path.extname(asset.target_path).toLowerCase())) failures.push(`${asset.asset_id}: MIME/extension mismatch`);
    if (asset.transform && !asset.provenance) failures.push(`${asset.asset_id}: transform lacks provenance`);
  }
  checks.push(result("asset.contract", "rendered-assets", failures.length === 0, {
    contractIds: required.map((item) => item.asset_id), evidenceRefs: [".moltex/contracts/contracts/assets.json"],
    expected: { local_only: true, contract_alt_text: true, mime_extension_compatible: true }, actual: failures,
    message: `Rendered asset policy failed: ${failures.join("; ")}`,
  }));
  return checks;
};

export const linkChecks = (contracts) => {
  const expectedPaths = new Set(contracts.publishedRoutes.map((route) => new URL(route.target_url, "https://moltex.invalid").pathname));
  expectedPaths.add("/404.html");
  const results = [];
  for (const route of contracts.publishedRoutes) {
    const file = path.join("dist", ...route.output_path.split("/"));
    if (!fs.existsSync(file)) continue;
    const html = fs.readFileSync(file, "utf8");
    for (const href of htmlAttributes(html, "a", "href")) {
      const parsed = new URL(href, "https://moltex.invalid");
      if (href.startsWith("#")) {
        const id = parsed.hash.slice(1);
        if (!id) continue;
        const exists = Boolean(id) && new RegExp(`\\sid=["']${id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}["']`, "i").test(html);
        results.push(result("link.internal-target", `${route.target_url}${parsed.hash}`, exists, {
          contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`], expected: `fragment ${parsed.hash}`, actual: exists, message: `Missing same-page fragment ${parsed.hash} from ${route.target_url}`,
        }));
        continue;
      }
      const target = localTarget(href);
      if (!target) continue;
      const exists = expectedPaths.has(target) || fs.existsSync(path.join("dist", outputForUrl(target)));
      results.push(result("link.internal-target", `${route.target_url} -> ${target}`, exists, {
        contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`],
        expected: "a public route or built output", actual: target, message: `Broken internal link ${target} from ${route.target_url}`,
      }));
    }
    for (const [element, attribute] of [["img", "src"], ["script", "src"], ["link", "href"]]) {
      for (const reference of htmlAttributes(html, element, attribute)) {
        const target = localTarget(reference);
        if (!target) continue;
        const exists = fs.existsSync(path.join("dist", target.replace(/^\//, "")));
        results.push(result("link.internal-target", `${route.target_url} -> ${target}`, exists, {
          contractIds: [route.contract_id], evidenceRefs: [`.moltex/contracts/contracts/routes.json#${route.contract_id}`], expected: "built local resource", actual: target, message: `Missing local ${element} resource ${target} from ${route.target_url}`,
        }));
      }
    }
  }
  return results.length ? results : [result("link.internal-target", "site", true, { passMessage: "No internal links require validation" })];
};

const flattenNavigation = (items, output = [], parent = null) => { for (let index = 0; index < items.length; index += 1) { const item = items[index]; output.push({ ...item, _parent: parent, _index: index }); flattenNavigation(item.children ?? [], output, item.id); } return output; };
export const navigationChecks = (contracts) => {
  const actual = flattenNavigation(readJson("src/data/navigation.json", []));
  const expected = contracts.siteSpec.global_navigation;
  const actualMap = new Map(actual.map((item) => [item.id, item]));
  const routeMap = new Map(contracts.routes.map((route) => [route.contract_id, route.target_url]));
  const expectedSiblings = new Map();
  for (const item of expected) {
    const parent = item.parent_navigation_id ?? "root";
    if (!expectedSiblings.has(parent)) expectedSiblings.set(parent, []);
    expectedSiblings.get(parent).push(item);
  }
  for (const siblings of expectedSiblings.values()) siblings.sort((a, b) => a.order - b.order || a.navigation_id.localeCompare(b.navigation_id));
  const failures = expected.filter((item) => {
    const rendered = actualMap.get(item.navigation_id);
    const expectedIndex = expectedSiblings.get(item.parent_navigation_id ?? "root").findIndex((candidate) => candidate.navigation_id === item.navigation_id);
    return !rendered || rendered.label !== item.label || rendered.href !== (routeMap.get(item.route_contract_id) ?? "#") || rendered._parent !== item.parent_navigation_id || rendered._index !== expectedIndex;
  });
  return [result("navigation.contract", "primary", failures.length === 0, {
    contractIds: expected.map((item) => item.navigation_id), evidenceRefs: [".moltex/contracts/site-spec.json", "src/data/navigation.json"],
    expected: expected.length, actual: actual.length, message: `Navigation differs for ${failures.map((item) => item.navigation_id).join(", ")}`,
  })];
};

export const seoChecks = (contracts) => contracts.publishedSeo.flatMap((seo) => {
  const route = contracts.publishedRoutes.find((item) => item.contract_id === seo.route_contract_id);
  const file = route ? path.join("dist", ...route.output_path.split("/")) : "";
  const exists = file && fs.existsSync(file);
  const html = exists ? fs.readFileSync(file, "utf8") : "";
  const ogItems = Array.isArray(seo.open_graph?.items) ? seo.open_graph.items : [seo.open_graph ?? {}];
  const ogEntries = ogItems.flatMap((item) => item && (item.property || item.name || item.key)
    ? [[item.property || item.name || item.key, item.content ?? item.value ?? ""]]
    : Object.entries(item ?? {}).filter(([key]) => key !== "items"));
  return [
    result("seo.required-title", seo.target_route, exists && titleText(html) === seo.title, {
      status: exists ? "fail" : "blocked", contractIds: [seo.contract_id, seo.route_contract_id], evidenceRefs: [`.moltex/contracts/contracts/seo.json#${seo.contract_id}`],
      expected: seo.title, actual: exists ? titleText(html) : null, message: exists ? "Rendered title differs from SEO contract" : "Title check blocked by missing route",
    }),
    result("seo.canonical", seo.target_route, exists && canonicalHref(html) === seo.canonical_url, {
      status: exists ? "fail" : "blocked", contractIds: [seo.contract_id, seo.route_contract_id], evidenceRefs: [`.moltex/contracts/contracts/seo.json#${seo.contract_id}`],
      expected: seo.canonical_url, actual: exists ? canonicalHref(html) : null, message: exists ? "Rendered canonical differs from SEO contract" : "Canonical check blocked by missing route",
    }),
    result("seo.description", seo.target_route, exists && (seo.description === null || metaContent(html, "description") === seo.description), {
      status: exists ? "fail" : "blocked", contractIds: [seo.contract_id, seo.route_contract_id], evidenceRefs: [`.moltex/contracts/contracts/seo.json#${seo.contract_id}`],
      expected: seo.description, actual: exists ? metaContent(html, "description") : null, message: exists ? "Rendered description differs from SEO contract" : "Description check blocked by missing route",
    }),
    result("seo.robots", seo.target_route, exists && metaContent(html, "robots") === seo.robots, {
      status: exists ? "fail" : "blocked", contractIds: [seo.contract_id, seo.route_contract_id], evidenceRefs: [`.moltex/contracts/contracts/seo.json#${seo.contract_id}`],
      expected: seo.robots, actual: exists ? metaContent(html, "robots") : null, message: exists ? "Rendered robots disposition differs from SEO contract" : "Robots check blocked by missing route",
    }),
    ...ogEntries.map(([key, value]) => result("seo.open-graph", `${seo.target_route}#${key}`, exists && metaContent(html, String(key).startsWith("og:") ? key : `og:${key}`) === String(value), {
      status: exists ? "fail" : "blocked", contractIds: [seo.contract_id, seo.route_contract_id], evidenceRefs: [`.moltex/contracts/contracts/seo.json#${seo.contract_id}`],
      expected: String(value), actual: exists ? metaContent(html, String(key).startsWith("og:") ? key : `og:${key}`) : null, message: exists ? `Rendered Open Graph ${key} differs from SEO contract` : "Open Graph check blocked by missing route",
    })),
  ];
}).concat((() => {
  const expected = contracts.publishedRoutes.filter((route) => route.expected_status === 200).filter((route) => {
    const seo = contracts.publishedSeo.find((item) => item.route_contract_id === route.contract_id);
    return !seo || !seo.robots.toLowerCase().includes("noindex");
  }).map((route) => route.target_url).sort();
  const actual = readJson("src/data/sitemap.json", []).sort();
  const xml = fs.existsSync("dist/sitemap.xml") ? fs.readFileSync("dist/sitemap.xml", "utf8") : "";
  const missingXml = expected.filter((route) => !xml.includes(route));
  return [result("seo.sitemap", "sitemap", JSON.stringify(actual) === JSON.stringify(expected) && missingXml.length === 0, {
    contractIds: contracts.publishedSeo.map((item) => item.contract_id), evidenceRefs: [".moltex/contracts/contracts/seo.json", "src/data/sitemap.json"],
    expected, actual: { routes: actual, missing_xml: missingXml }, message: "Sitemap entries differ from indexable route contracts",
  })];
})());

export const redirectChecks = (contracts) => {
  const active = contracts.redirects.filter((item) => !item.needs_decision);
  const graph = new Map(active.map((item) => [new URL(item.source_url, "https://moltex.invalid").pathname, new URL(item.target_url, "https://moltex.invalid").pathname]));
  const loopChecks = active.map((redirect) => {
    let cursor = new URL(redirect.source_url, "https://moltex.invalid").pathname;
    const seen = new Set();
    while (graph.has(cursor) && !seen.has(cursor)) { seen.add(cursor); cursor = graph.get(cursor); }
    const loop = seen.has(cursor);
    return result("redirect.no-loop", redirect.source_url, !loop, {
      contractIds: [redirect.contract_id], evidenceRefs: [`.moltex/contracts/contracts/redirects.json#${redirect.contract_id}`],
      expected: "acyclic redirect chain", actual: [...seen, cursor], message: `Redirect loop detected at ${cursor}`,
    });
  });
  const built = fs.existsSync("dist/_redirects") ? fs.readFileSync("dist/_redirects", "utf8").trim().split(/\r?\n/).filter(Boolean) : [];
  const observed = (contracts.expectations.observedRedirects ?? []).map((item) => {
    const source = new URL(item.sourceUrl).pathname;
    const targetUrl = new URL(item.targetUrl);
    const target = `${targetUrl.pathname}${targetUrl.search}`;
    return `${source} ${target} ${item.statusCode}`;
  });
  const expected = [...active.map((item) => `${item.source_url} ${item.target_url} ${item.status_code}`), ...observed].sort();
  const routeTargets = new Set(contracts.publishedRoutes.map((item) => new URL(item.target_url, "https://moltex.invalid").pathname));
  const missingTargets = active.filter((item) => {
    const target = new URL(item.target_url, "https://moltex.invalid");
    return target.origin === "https://moltex.invalid" && !routeTargets.has(target.pathname);
  }).map((item) => item.contract_id);
  loopChecks.push(result("redirect.contract", "redirect-manifest", JSON.stringify([...built].sort()) === JSON.stringify(expected) && missingTargets.length === 0, {
    contractIds: active.map((item) => item.contract_id), evidenceRefs: [".moltex/contracts/contracts/redirects.json", "dist/_redirects"],
    expected, actual: { rules: [...built].sort(), missing_targets: missingTargets }, message: "Built redirect rules or targets differ from redirect contracts",
  }));
  return loopChecks;
};

export const capabilityChecks = (contracts) => {
  const expectedIds = new Set(contracts.siteSpec.capability_ids ?? []);
  const actualIds = new Set(contracts.capabilities.map((item) => item.capability_id));
  const missing = [...expectedIds].filter((id) => !actualIds.has(id)).map((capabilityId) => result("capability.disposition", capabilityId, false, {
    status: "fail", contractIds: [capabilityId], evidenceRefs: [".moltex/contracts/site-spec.json", ".moltex/contracts/contracts/capabilities.json"],
    expected: "one declared capability disposition", actual: null, message: `Capability disposition is missing: ${capabilityId}`,
  }));
  const declared = contracts.capabilities.map((capability) => {
  const decided = capability.disposition !== "needs_decision" && Boolean(capability.target_behavior) && Boolean(capability.verification_method);
  return result("capability.disposition", capability.capability_id, decided, {
    status: capability.disposition === "needs_decision" ? "needs_decision" : "fail",
    contractIds: [capability.capability_id], evidenceRefs: [`.moltex/contracts/contracts/capabilities.json#${capability.capability_id}`],
    expected: "a decided disposition with target behavior and verification method", actual: capability.disposition,
    message: `Capability disposition is incomplete: ${capability.capability_id}`,
  });
  });
  return [...missing, ...declared];
};

export const taskChecks = (contracts) => {
  if (!contracts.taskGraph) return [result("task.completion-evidence", "task-graph", true, { passMessage: "No H4 task graph is present" })];
  return contracts.taskGraph.tasks.map((task) => {
    const file = `.moltex/task-evidence/${task.task_id}/execution.json`;
    const evidence = readJson(file, null);
    if (!evidence) {
      const claimed = task.state === "complete" || (fs.existsSync("EXECPLAN.md") && fs.readFileSync("EXECPLAN.md", "utf8").includes(`- [x] \`${task.task_id}\``));
      return checkResult({ checkId: "task.completion-evidence", status: claimed ? "fail" : "blocked", severity: claimed ? "critical" : "warning", subject: task.task_id, contractIds: task.contract_ids, evidenceRefs: [`.moltex/tasks/${task.task_id}.json`, file], expected: "checksummed completion evidence for every required task", actual: null, message: claimed ? `Task ${task.task_id} is claimed complete without execution evidence` : "Required migration task has no completion evidence" });
    }
    const artifactsValid = [[evidence.diff_artifact, evidence.diff_sha256], [evidence.session_artifact, evidence.session_sha256]].every(([artifact, digest]) => artifact && fs.existsSync(artifact) && sha256(fs.readFileSync(artifact)) === digest);
    const ok = evidence.task_id === task.task_id && evidence.protected_paths_unchanged && evidence.command_results.every((item) => item.exit_code === 0) && artifactsValid;
    return result("task.completion-evidence", task.task_id, Boolean(ok), {
      contractIds: task.contract_ids, evidenceRefs: [`.moltex/tasks/${task.task_id}.json`, file],
      expected: { successful_commands: true, protected_paths_unchanged: true }, actual: evidence,
      message: `Complete task ${task.task_id} lacks valid execution evidence`,
    });
  });
};

export const parityChecks = (contracts) => {
  const rows = contracts.planningParity?.rows ?? contracts.parity;
  const keys = rows.map((row) => `${row.subject_type}:${row.subject_id}`);
  const duplicates = keys.filter((item, index) => keys.indexOf(item) !== index);
  const uniqueness = result("parity.unique-subject", "parity-matrix", duplicates.length === 0, {
    contractIds: rows.map((row) => row.row_id),
    evidenceRefs: [contracts.planningParity ? ".moltex/parity-matrix.json" : ".moltex/contracts/parity-matrix.json"],
    expected: rows.length, actual: new Set(keys).size, message: `Duplicate parity subjects: ${[...new Set(duplicates)].join(", ")}`,
  });
  const reviews = rows.filter((row) => row.state !== "approved" && row.state !== "omitted").map((row) => checkResult({
    checkId: "parity.subject", status: row.state === "blocked" ? "blocked" : "review", severity: "warning", subject: row.subject_id,
    contractIds: [row.route_contract_id, row.capability_id].filter(Boolean), evidenceRefs: [".moltex/parity-matrix.json"],
    expected: "approved or explicitly omitted", actual: row.state, message: `Parity subject remains ${row.state}`,
  }));
  return [uniqueness, ...reviews];
};
