import { portable } from "./titan-protobuf.mjs";
import { createBindings } from "./bridge.mjs";

export async function run(context) {
  const image = await context.image("build_browser/app.mjs");
  const rawBindings = createBindings();
  context.assert(
    rawBindings &&
      typeof rawBindings.transform_wire === "function" &&
      typeof rawBindings.reject_plain === "function" &&
      typeof rawBindings.inspect_error === "function",
    "bridge.mjs createBindings() must return transform_wire, reject_plain, and inspect_error"
  );

  let transformCalls = 0;
  let rejectCalls = 0;
  let inspectCalls = 0;
  let capturedDesc = null;
  let capturedPeerError = null;
  let capturedErrorReport = null;

  const wrappedBindings = {
    transform_wire(desc, encoded) {
      transformCalls += 1;
      context.assert(typeof desc === "string" && desc.length > 0, "desc must be non-empty string");
      context.assert(encoded instanceof Uint8Array, "encoded wire must be Uint8Array");
      capturedDesc = desc;

      // Independently decode Titan -> JS payload to verify exact wire values
      const refCodec = portable(desc);
      const [inReading, inNote] = refCodec.decode(encoded);
      context.assert(
        inReading instanceof refCodec.types["codec.Reading"],
        "input reading must decode as codec.Reading instance"
      );
      context.assert(inReading.sensor === "roof", `unexpected input sensor: ${inReading.sensor}`);
      context.assert(
        inReading.sample === 9007199254740993n,
        `expected 64-bit BigInt 9007199254740993n, got ${String(inReading.sample)}`
      );
      context.equalBytes(
        inReading.payload,
        new Uint8Array([0x72, 0x61, 0x77, 0x00, 0xff]),
        "input raw payload bytes"
      );
      context.assert(
        inNote instanceof refCodec.types["codec.Note"] && inNote.tag === "live",
        "input extra must be codec.Note('live')"
      );

      // Call subject's bridge implementation
      const outWire = rawBindings.transform_wire(desc, encoded);
      context.assert(outWire instanceof Uint8Array, "transform_wire must return Uint8Array");

      // Independently verify JS -> Titan wire response
      const [outReading, outNote] = refCodec.decode(outWire);
      context.assert(outReading.sensor === "roof:ack", `unexpected output sensor: ${outReading.sensor}`);
      context.assert(
        outReading.sample === 9007199254740994n,
        `expected BigInt 9007199254740994n, got ${String(outReading.sample)}`
      );
      context.equalBytes(
        outReading.payload,
        new Uint8Array([0x72, 0x61, 0x77, 0x00, 0xff, 0x7e]),
        "output raw payload bytes"
      );
      context.assert(
        outNote instanceof refCodec.types["codec.Note"] && outNote.tag === "live:js",
        "output extra must be codec.Note('live:js')"
      );
      return outWire;
    },

    reject_plain(desc) {
      rejectCalls += 1;
      try {
        rawBindings.reject_plain(desc);
      } catch (err) {
        context.assert(
          err instanceof TypeError && err.code === "type_mismatch" && err.path === "$[1]",
          `expected TypeError type_mismatch at $[1], got ${err} (code=${err?.code}, path=${err?.path})`
        );
        capturedPeerError = err;
        throw err;
      }
      throw new Error("reject_plain failed to throw peer TypeError");
    },

    inspect_error(thrown) {
      inspectCalls += 1;
      context.assert(
        thrown === capturedPeerError,
        "inspect_error must receive the exact BrowserError.thrown handle"
      );
      const report = rawBindings.inspect_error(thrown);
      capturedErrorReport = report;
      return report;
    },
  };

  const instance = image.create({
    locateFile: image.locateFile,
    stdout: context.stdout,
    stderr: context.stderr,
    requireTrace: true,
    bindings: wrappedBindings,
  });

  try {
    await instance.initialize();
    const result = await instance.run([]);
    context.assert(
      (result.kind === "returned" || result.kind === "exit") && result.status === 0,
      `browser app exited unexpectedly: ${JSON.stringify(result)}`
    );
  } finally {
    await instance.dispose();
  }

  context.assert(transformCalls === 1, `expected 1 transform_wire call, got ${transformCalls}`);
  context.assert(rejectCalls === 1, `expected 1 reject_plain call, got ${rejectCalls}`);
  context.assert(inspectCalls === 1, `expected 1 inspect_error call, got ${inspectCalls}`);
  context.assert(
    capturedErrorReport === "type_mismatch:$[1]",
    `unexpected error report: ${capturedErrorReport}`
  );
  context.assert(capturedDesc !== null, "codec description was never sent");
}
