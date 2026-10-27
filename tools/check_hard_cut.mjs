import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";

const source = fs.readFileSync(new URL("../custom_nodes/ComfyUI-H3-SeedHunter/web/seedhunter_projects.js", import.meta.url), "utf8");
const accept = source.slice(source.indexOf("async function acceptRenderedClip("), source.indexOf("\nasync function saveCurrentProjectState("));
const project = { type: "H3SeedHunterProject", properties: { seedhunter_project: { project_token: "project:1", next_clip_index: 2 } }, widgets: [{ name: "project_name", value: "Test" }] };
const start = { type: "H3SeedHunterSourceVideoFFmpeg", widgets: [{ name: "start_mode", value: "new clip" }] };
const save = { type: "MiniMaxH3MotionContextSaveLatent", title: "SAVE SINGLE PASS CONTEXT" };
const nodes = [project, start, save];
let payload;
const context = {
    TYPE: project.type, SINGLE_PASS_CONTEXT_PREFIX: "single/clip", FINAL_PASS_CONTEXT_PREFIX: "final/clip",
    findNode: (predicate) => nodes.find(predicate),
    widget: (node, name) => node?.widgets?.find((w) => w.name === name),
    singlePassIsActive: () => true,
    resolvedOutput: async () => ({ path: "render.mp4" }),
    valueOfNode: (type) => type === "PrimitiveFloat" ? 10 : type === "H3SeedHunterAVContext" ? 39 : "",
    validH3Frames: () => 243, collectProjectSettings: () => ({}),
    fetch: async (_, options) => { payload = JSON.parse(options.body); return { ok: true, json: async () => ({ next_clip_index: 3 }) }; },
    applySnapshot() {}, notify() {},
};
vm.createContext(context);
vm.runInContext(accept, context);
const output = { title: "HYBRID PREVIEW 1", widgets: [] };
await context.acceptRenderedClip(output);
assert.equal(payload.transition_mode, "hard_cut");
assert.equal(payload.overlap_frames, 0);
start.widgets[0].value = "extend video";
await context.acceptRenderedClip(output);
assert.equal(payload.transition_mode, "continuation");
assert.equal(payload.overlap_frames, 39);
project.properties.seedhunter_project.next_clip_index = 1;
await context.acceptRenderedClip(output);
assert.equal(payload.transition_mode, "hard_cut");
assert.equal(payload.overlap_frames, 0);
console.log("PASS: new clip records a hard cut; extension records overlap; clip 1 has zero overlap.");
