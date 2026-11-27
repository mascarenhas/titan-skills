import defaultImports, { createHostImports } from "./wasm_imports.mjs";

function jsCrc32Update(prevCrc, bytes) {
  let c = (prevCrc ^ 0xffffffff) >>> 0;
  for (let i = 0; i < bytes.length; i += 1) {
    c = (c ^ bytes[i]) >>> 0;
    for (let b = 0; b < 8; b += 1) {
      c = ((c >>> 1) ^ (c & 1 ? 0xedb88320 : 0)) >>> 0;
    }
  }
  return (c ^ 0xffffffff) >>> 0;
}

function u32ToLe(v) {
  const u = v >>> 0;
  return new Uint8Array([u & 0xff, (u >>> 8) & 0xff, (u >>> 16) & 0xff, (u >>> 24) & 0xff]);
}

function computeExpectedCrc(chunks) {
  let acc = jsCrc32Update(0, new TextEncoder().encode("123456789"));
  if (acc !== 0xcbf43926) {
    throw new Error("internal oracle CRC-32 sanity check failed");
  }
  for (const ch of chunks) {
    if (ch.len === 0) {
      continue;
    }
    const transformed = ((ch.crc ^ ch.len) >>> 0);
    acc = jsCrc32Update(acc, u32ToLe(transformed));
  }
  return acc >>> 0;
}

function assertPlainObject(context, val, label) {
  context.assert(
    val !== null && typeof val === "object" && !Array.isArray(val) &&
      !(val instanceof Map) && !(val instanceof Set) && typeof val.then !== "function",
    `${label} must be a plain object (not Array/Map/Promise)`
  );
  const proto = Object.getPrototypeOf(val);
  context.assert(proto === Object.prototype || proto === null, `${label} must have plain or null prototype`);
}

export async function run(context) {
  // 1. Validate wasm_imports.mjs exports and reserved-namespace hygiene.
  context.assert(typeof defaultImports === "function", "wasm_imports.mjs default export must be a sync factory function");
  context.assert(typeof createHostImports === "function", "wasm_imports.mjs must export createHostImports(chunks, onReport)");

  const probeTable = { get: () => () => 0 };
  const probeObj = defaultImports({
    table: probeTable,
    readCString: () => "",
    readBytes: () => new Uint8Array(0),
    writeBytes: () => {},
  });
  assertPlainObject(context, probeObj, "default import object");
  context.assert(!("wasi_snapshot_preview1" in probeObj), "imports must never override wasi_snapshot_preview1");
  assertPlainObject(context, probeObj.env, "imports.env");
  for (const key of Object.keys(probeObj.env)) {
    context.assert(
      !key.startsWith("titan_browser_") && !key.startsWith("titan_mco_"),
      `imports.env must never override reserved symbol ${key}`
    );
  }
  context.assert(typeof probeObj.env.host_feed_chunks === "function", "imports.env.host_feed_chunks missing");
  context.assert(typeof probeObj.env.host_report_crc === "function", "imports.env.host_report_crc missing");

  // 2. Run compiled browser image with custom chunk vector exercising both OK and TITAN_ERROR (empty chunk) callbacks.
  const chunks = [
    { crc: 0x10203040, len: 4 },
    { crc: 0x00000000, len: 0 }, // triggers Titan raise inside titan_browser_call_sync -> TITAN_BROWSER_TITAN_ERROR
    { crc: 0x55667788, len: 8 },
    { crc: 0xabcdef01, len: 0 }, // second caught callback error -> instance must stay unpoisoned
  ];
  const expectedCrc = computeExpectedCrc(chunks);

  const reports = [];
  const customImports = createHostImports(chunks, (tag, combinedCrc, okCount, errCount) => {
    reports.push({ tag, combinedCrc: combinedCrc >>> 0, okCount, errCount });
  });

  const image = await context.image("build_browser/crc_app.mjs");
  const instance = image.create({
    locateFile: image.locateFile,
    stdout: context.stdout,
    stderr: context.stderr,
    requireTrace: true,
    imports: customImports,
  });

  try {
    await instance.initialize();
    const res = await instance.run([]);
    context.assert(
      (res.kind === "returned" || res.kind === "exit") && res.status === 0,
      `crc_app exited unexpectedly: ${JSON.stringify(res)}`
    );
  } finally {
    await instance.dispose();
  }

  context.assert(reports.length === 1, `expected exactly 1 host_report_crc call, got ${reports.length}`);
  const r = reports[0];
  context.assert(r.tag === "crc-done", `expected tag 'crc-done', got ${JSON.stringify(r.tag)}`);
  context.assert(
    r.combinedCrc === expectedCrc,
    `combined CRC mismatch: expected 0x${expectedCrc.toString(16)}, got 0x${r.combinedCrc.toString(16)}`
  );
  context.assert(r.okCount === 2, `expected okCount === 2, got ${r.okCount}`);
  context.assert(r.errCount === 2, `expected errCount === 2, got ${r.errCount}`);
}
