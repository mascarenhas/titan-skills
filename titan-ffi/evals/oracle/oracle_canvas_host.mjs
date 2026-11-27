import { createBindings } from "./bindings.mjs";

function approx(a, b) {
  return Math.abs(a - b) < 1e-6;
}

export async function run(context) {
  const image = await context.image("build_browser/timeline_app.mjs");

  const ops = [];
  let failNextFillText = false;
  const ctx2d = {
    fillStyle: "",
    clearRect(x, y, w, h) {
      ops.push({ op: "clearRect", x, y, w, h });
    },
    fillRect(x, y, w, h) {
      ops.push({ op: "fillRect", x, y, w, h, fillStyle: this.fillStyle });
    },
    fillText(text, x, y) {
      if (failNextFillText) {
        failNextFillText = false;
        throw new Error("font unavailable");
      }
      ops.push({ op: "fillText", text, x, y });
    },
  };

  const listeners = new Map();
  let addCount = 0;
  let removeCount = 0;
  const eventTarget = {
    addEventListener(type, fn) {
      addCount += 1;
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(fn);
    },
    removeEventListener(type, fn) {
      removeCount += 1;
      listeners.get(type)?.delete(fn);
    },
    dispatch(type, ev) {
      for (const fn of [...(listeners.get(type) ?? [])]) {
        fn(ev);
      }
    },
    activeCount(type) {
      return listeners.get(type)?.size ?? 0;
    },
  };

  const selections = [];
  let getStateFn = null;
  let closeFn = null;
  const hooks = {
    onSelection(id, seq, errCount) {
      selections.push({ id, seq, errCount });
    },
    onRegisterApi(getState, closeChart) {
      getStateFn = getState;
      closeFn = closeChart;
    },
  };

  const bindings = createBindings(ctx2d, eventTarget, hooks);
  for (const key of ["clear_rect", "fill_rect", "fill_text", "on_pointer", "report_selection", "register_api"]) {
    context.assert(typeof bindings[key] === "function", `bindings.mjs must provide function '${key}'`);
  }

  const instance = image.create({
    locateFile: image.locateFile,
    stdout: context.stdout,
    stderr: context.stderr,
    requireTrace: true,
    bindings,
  });

  try {
    await instance.initialize();
    const res = await instance.run([]);
    context.assert(
      (res.kind === "returned" || res.kind === "exit") && res.status === 0,
      `timeline_app main failed: ${JSON.stringify(res)}`
    );

    context.assert(addCount === 1 && eventTarget.activeCount("pointerdown") === 1,
      `expected 1 active pointerdown listener, got add=${addCount} active=${eventTarget.activeCount("pointerdown")}`);
    context.assert(getStateFn && typeof getStateFn.call === "function" && typeof getStateFn.release === "function",
      "register_api must receive a Titan callable wrapper for get_state");
    context.assert(closeFn && typeof closeFn.call === "function" && typeof closeFn.release === "function",
      "register_api must receive a Titan callable wrapper for close_chart");

    // Verify initial frame primitives: 1 clearRect, 3 fillRect, 3 fillText.
    const initClears = ops.filter(o => o.op === "clearRect");
    const initRects = ops.filter(o => o.op === "fillRect");
    const initTexts = ops.filter(o => o.op === "fillText");
    context.assert(initClears.length === 1 && approx(initClears[0].w, 520) && approx(initClears[0].h, 120),
      `unexpected initial clearRect: ${JSON.stringify(initClears)}`);
    context.assert(initRects.length === 3, `expected 3 initial fillRects, got ${initRects.length}`);
    context.assert(approx(initRects[0].x, 10) && approx(initRects[0].y, 10) && approx(initRects[0].w, 100) && initRects[0].fillStyle === "#3366cc",
      `unexpected rect 0: ${JSON.stringify(initRects[0])}`);
    context.assert(approx(initRects[1].x, 110) && approx(initRects[1].y, 40) && approx(initRects[1].w, 200) && initRects[1].fillStyle === "#33aa66",
      `unexpected rect 1: ${JSON.stringify(initRects[1])}`);
    context.assert(approx(initRects[2].x, 310) && approx(initRects[2].y, 70) && approx(initRects[2].w, 200) && initRects[2].fillStyle === "#aa44aa",
      `unexpected rect 2: ${JSON.stringify(initRects[2])}`);
    context.assert(initTexts.length === 3 && initTexts.map(t => t.text).join(",") === "lex,parse,emit",
      `unexpected initial labels: ${JSON.stringify(initTexts)}`);

    // 1. Click inside "parse" span (x=150, y=50, seq=1n).
    ops.length = 0;
    eventTarget.dispatch("pointerdown", { x: 150, y: 50, seq: 1n });
    await instance.drain();

    const r1 = ops.filter(o => o.op === "fillRect");
    const t1 = ops.filter(o => o.op === "fillText");
    context.assert(r1.length === 3 && r1[1].fillStyle === "#ff9900" && r1[0].fillStyle === "#3366cc",
      `expected parse highlighted #ff9900, got ${JSON.stringify(r1)}`);
    context.assert(t1.length === 3 && t1[1].text === "parse *",
      `expected 'parse *' label, got ${JSON.stringify(t1)}`);
    context.assert(selections.length === 1 && selections[0].id === "parse" &&
      selections[0].seq === 1n && selections[0].errCount === 0n,
      `unexpected selection 1 (BigInt required): ${JSON.stringify(selections, (_, v) => typeof v === "bigint" ? `${v}n` : v)}`);

    // 2. Click in empty space (x=5, y=5, seq=2n) -> clears selection.
    ops.length = 0;
    eventTarget.dispatch("pointerdown", { x: 5, y: 5, seq: 2n });
    await instance.drain();

    const r2 = ops.filter(o => o.op === "fillRect");
    context.assert(r2.length === 3 && r2.every(r => r.fillStyle !== "#ff9900"),
      `expected selection cleared, got ${JSON.stringify(r2)}`);
    context.assert(selections.length === 2 && selections[1].id === "" &&
      selections[1].seq === 2n && selections[1].errCount === 0n,
      `unexpected selection 2: ${JSON.stringify(selections[1], (_, v) => typeof v === "bigint" ? `${v}n` : v)}`);

    // 3. Inject BrowserError on fillText during render, verify caught & closed without poisoning.
    ops.length = 0;
    failNextFillText = true;
    eventTarget.dispatch("pointerdown", { x: 40, y: 20, seq: 3n });
    await instance.drain();

    context.assert(selections.length === 3 && selections[2].id === "lex" &&
      selections[2].seq === 3n && selections[2].errCount === 1n,
      `expected BrowserError caught & errCount=1n, got ${JSON.stringify(selections[2], (_, v) => typeof v === "bigint" ? `${v}n` : v)}`);

    // 4. Query state through exported Titan callable wrapper.
    const stateStr = await getStateFn.call();
    context.assert(stateStr === "lex:1", `expected get_state() === 'lex:1', got ${JSON.stringify(stateStr)}`);

    // 5. Explicit teardown through exported close callable breaks JS<->Lua cycle & unsubscribes listener.
    await closeFn.call();
    context.assert(removeCount === 1 && eventTarget.activeCount("pointerdown") === 0,
      `expected listener unsubscribed after close, remove=${removeCount} active=${eventTarget.activeCount("pointerdown")}`);
  } finally {
    if (getStateFn) getStateFn.release();
    if (closeFn) closeFn.release();
    await instance.dispose();
  }
}
