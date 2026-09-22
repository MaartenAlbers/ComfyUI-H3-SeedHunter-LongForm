import { app } from "/scripts/app.js";

const TYPE = "H3SeedHunterSinglePassControl";
const NORMAL = 0;
const BYPASS = 4;
const PREVIEW_OUTPUTS = ["HYBRID PREVIEW 1", "HYBRID PREVIEW 2", "HYBRID PREVIEW 3"];
const CONTROLLED_GROUPS = ["SELECT PREVIEW 1", "SELECT PREVIEW 2", "SELECT PREVIEW 3", "HYBRID FINAL UPSCALE PASS"];
const SINGLE_PASS_CONTEXT_SAVE = "SAVE SINGLE PASS CONTEXT";
const FINAL_PASS_CHOOSER = "CHOOSE PREVIEW FOR FINAL PASS";
const ASPECT_RATIOS = {
    "1:1 (Square)": [1, 1],
    "2:3 (Portrait Photo)": [2, 3],
    "3:2 (Photo)": [3, 2],
    "3:4 (Portrait Standard)": [3, 4],
    "4:3 (Standard)": [4, 3],
    "9:16 (Portrait Widescreen)": [9, 16],
    "16:9 (Widescreen)": [16, 9],
    "21:9 (Ultrawide)": [21, 9],
};
const LEGACY_UI_WIDGETS = new Set(["CURRENT MODE", "TURN ON SINGLE PASS", "RESTORE PREVIEW MODE"]);

const widget = (node, name) => node?.widgets?.find((item) => item.name === name);
const findNode = (part) => (app.graph?._nodes || []).find((node) => (node.title || "").includes(part));

function notify(message) {
    app.extensionManager?.toast?.add?.({severity: "success", summary: "SeedHunter", detail: message, life: 5000});
}

function groupBounds(group) {
    const value = group?._bounding || group?.bounding;
    if (Array.isArray(value) && value.length >= 4) return value.slice(0, 4).map(Number);
    if (group?.pos && group?.size) return [...group.pos, ...group.size].map(Number);
    return null;
}

function nodesInControlledGroups() {
    const found = new Map();
    for (const group of app.graph?._groups || []) {
        if (!CONTROLLED_GROUPS.some((part) => (group.title || "").includes(part))) continue;
        const bounds = groupBounds(group);
        if (!bounds) continue;
        const [x, y, width, height] = bounds;
        for (const node of app.graph?._nodes || []) {
            const cx = Number(node.pos?.[0] || 0) + Number(node.size?.[0] || 0) / 2;
            const cy = Number(node.pos?.[1] || 0) + Number(node.size?.[1] || 0) / 2;
            if (cx >= x && cx <= x + width && cy >= y && cy <= y + height) found.set(String(node.id), node);
        }
    }
    return [...found.values()];
}

function controlledNodes() {
    const found = new Map();
    for (const title of PREVIEW_OUTPUTS) {
        const node = findNode(title);
        if (node) found.set(String(node.id), node);
    }
    for (const node of nodesInControlledGroups()) found.set(String(node.id), node);
    const seamless = findNode("FULL SEAMLESS VIDEO");
    if (seamless) found.set(String(seamless.id), seamless);
    return [...found.values()];
}

function setMode(node, mode) {
    node.mode = Number(mode);
    node.setDirtyCanvas?.(true, true);
}

function previewOutputNodes() {
    return PREVIEW_OUTPUTS.map(findNode).filter(Boolean);
}

function selectedPreviewNumber() {
    const selected = (app.graph?._nodes || []).find((node) =>
        /^PREVIEW [123] SELECTED$/.test(node.title || "") && Number(node.mode ?? NORMAL) !== BYPASS
    );
    const match = (selected?.title || "").match(/PREVIEW ([123]) SELECTED/);
    return match ? Number(match[1]) : null;
}

function armFinalPass(chooser) {
    const selected = selectedPreviewNumber();
    if (!selected) throw new Error("Choose Preview 1, 2, or 3 first.");
    chooser.properties ||= {};
    chooser.properties.seedhunter_preview_output_modes = Object.fromEntries(
        previewOutputNodes().map((node) => [String(node.id), Number(node.mode ?? NORMAL)])
    );
    for (const node of previewOutputNodes()) setMode(node, BYPASS);
    const finalOutput = findNode("FINAL SELECTED CLIP");
    if (!finalOutput) throw new Error("The final selected clip output was not found.");
    setMode(finalOutput, NORMAL);
    chooser.title = `FINAL PASS ARMED — PREVIEW ${selected} ONLY`;
    chooser.color = "#c16d18";
    chooser.bgcolor = "#3d2715";
    chooser.setDirtyCanvas?.(true, true);
    notify(`Final Pass armed. Only Preview ${selected} can be evaluated.`);
}

function restorePreviewOutputs(chooser) {
    const saved = chooser.properties?.seedhunter_preview_output_modes || {};
    for (const node of previewOutputNodes()) {
        setMode(node, Object.prototype.hasOwnProperty.call(saved, String(node.id)) ? saved[String(node.id)] : NORMAL);
    }
    chooser.properties ||= {};
    chooser.properties.seedhunter_preview_output_modes = {};
    chooser.title = FINAL_PASS_CHOOSER;
    chooser.color = "#f66744";
    chooser.bgcolor = "#181414";
    chooser.setDirtyCanvas?.(true, true);
    notify("Preview output nodes restored.");
}

function installFinalPassControl(node) {
    const title = node.title || "";
    if ((!title.includes(FINAL_PASS_CHOOSER) && !title.includes("FINAL PASS ARMED")) || widget(node, "ARM FINAL PASS")) return;
    const arm = node.addWidget("button", "ARM FINAL PASS", null, () => {
        try { armFinalPass(node); } catch (error) { alert(`SeedHunter: ${error.message}`); }
    }, {serialize: false});
    const restore = node.addWidget("button", "RESTORE PREVIEW OUTPUTS", null, () => {
        try { restorePreviewOutputs(node); } catch (error) { alert(`SeedHunter: ${error.message}`); }
    }, {serialize: false});
    arm.serializeValue = () => undefined;
    restore.serializeValue = () => undefined;
    node.size[0] = Math.max(Number(node.size?.[0] || 0), 450);
    node.size[1] = Math.max(Number(node.size?.[1] || 0), 180);
}

function aspectRatio(control) {
    const value = String(widget(control, "aspect_ratio")?.value || "16:9 (Widescreen)");
    return ASPECT_RATIOS[value] ? value : "16:9 (Widescreen)";
}

function dimensions(aspect, megapixels, multiple=32) {
    const [wr, hr] = ASPECT_RATIOS[aspect];
    const scale = Math.sqrt(Number(megapixels) * 1024 * 1024 / (wr * hr));
    return [Math.round(wr * scale / multiple) * multiple, Math.round(hr * scale / multiple) * multiple];
}

function setFinalResolution(control) {
    const node = findNode("SeedHunter 3D latent upscale");
    if (!node) throw new Error("The final 3D latent upscaler was not found.");
    const mp = Number(widget(control, "final_pass_megapixels")?.value || 1.5);
    const aspect = aspectRatio(control);
    if (!Number.isFinite(mp) || mp <= 0) throw new Error("Enter a valid final-pass resolution.");
    const [width, height] = dimensions(aspect, mp, 32);
    for (const [name, value] of [["mode", "target dimensions"], ["mode.width", width], ["mode.height", height], ["align", 32], ["keep_proportion", false]]) {
        const field = widget(node, name);
        if (field) {
            field.value = value;
            field.callback?.(value, app.canvas, node, app.canvas?.graph_mouse, {});
        }
    }
    node.title = `SeedHunter 3D latent upscale — ${aspect.split(" ")[0]} / ${mp} MP / ${width}×${height}`;
    node.setDirtyCanvas?.(true, true);
}

function setResolution(control, value) {
    const node = (app.graph?._nodes || []).find((item) => item.type === "ResolutionSelector");
    const field = widget(node, "megapixels");
    if (!node || !field) throw new Error("PREVIEW RESOLUTION was not found.");
    const aspect = aspectRatio(control);
    const aspectField = widget(node, "aspect_ratio");
    if (aspectField) {
        aspectField.value = aspect;
        aspectField.callback?.(aspect, app.canvas, node, app.canvas?.graph_mouse, {});
    }
    field.value = Number(value);
    field.callback?.(field.value, app.canvas, node, app.canvas?.graph_mouse, {});
    node.title = "INTERNAL — generation dimensions (managed by FORMAT)";
    node.flags ||= {};
    node.flags.collapsed = true;
    node.setDirtyCanvas?.(true, true);
}

function syncActiveResolution(control) {
    const single = control.properties?.seedhunter_mode === "single";
    const source = widget(control, single ? "single_pass_megapixels" : "preview_megapixels");
    const value = Number(source?.value);
    if (Number.isFinite(value) && value > 0) setResolution(control, value);
    setFinalResolution(control);
}

function bindResolutionWidget(control, name, activeMode) {
    const field = widget(control, name);
    if (!field || field.seedhunterBound) return;
    const original = field.callback;
    field.callback = function(value, ...args) {
        original?.call(this, value, ...args);
        if ((control.properties?.seedhunter_mode || "preview") === activeMode) {
            setResolution(control, value);
            setStatus(control, activeMode);
        }
    };
    field.seedhunterBound = true;
}

function bindFormatWidgets(control) {
    for (const name of ["aspect_ratio", "final_pass_megapixels"]) {
        const field = widget(control, name);
        if (!field || field.seedhunterBound) continue;
        const original = field.callback;
        field.callback = function(value, ...args) {
            const locked = control.properties?.seedhunter_project_aspect_locked;
            if (name === "aspect_ratio" && locked && String(value) !== String(locked)) {
                field.value = locked;
                alert(`SeedHunter: This project is locked to ${locked} because it already has accepted clips.`);
                return;
            }
            original?.call(this, value, ...args);
            syncActiveResolution(control);
            setStatus(control, control.properties?.seedhunter_mode === "single" ? "single" : "preview");
        };
        field.seedhunterBound = true;
    }
}

function setStatus(control, mode) {
    control.properties ||= {};
    control.properties.seedhunter_mode = mode;
    const label = mode === "single" ? "SINGLE PASS" : "PREVIEW";
    const mp = Number(widget(control, mode === "single" ? "single_pass_megapixels" : "preview_megapixels")?.value);
    const aspect = aspectRatio(control).split(" ")[0];
    const finalMp = Number(widget(control, "final_pass_megapixels")?.value || 1.5);
    control.title = `FORMAT: ${aspect} — ${label} ${mp} MP — FINAL ${finalMp} MP`;
    control.color = mode === "single" ? "#c16d18" : "#7f9431";
    control.bgcolor = mode === "single" ? "#3d2715" : "#343b22";
    control.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
    window.dispatchEvent(new CustomEvent("seedhunter-mode-changed", {detail: {mode}}));
}

function normalizeFormatWidgets(control) {
    const resolution = (app.graph?._nodes || []).find((item) => item.type === "ResolutionSelector");
    const resolutionAspect = String(widget(resolution, "aspect_ratio")?.value || "");
    const aspectField = widget(control, "aspect_ratio");
    if (aspectField && !ASPECT_RATIOS[String(aspectField.value)]) {
        aspectField.value = ASPECT_RATIOS[resolutionAspect] ? resolutionAspect : "16:9 (Widescreen)";
    }
    const finalField = widget(control, "final_pass_megapixels");
    const finalValue = Number(finalField?.value);
    if (finalField && (!Number.isFinite(finalValue) || finalValue <= 0)) finalField.value = 1.5;
}

function installButtons(node) {
    // v1.3 saved frontend-only status/buttons positionally. Remove those legacy
    // widgets so they cannot be mistaken for the new aspect/final inputs.
    node.widgets = (node.widgets || []).filter((item) => !LEGACY_UI_WIDGETS.has(item.name));
    const singleButton = node.addWidget("button", "TURN ON SINGLE PASS", null, () => {
        try { enableSinglePass(node); } catch (error) { alert(`SeedHunter: ${error.message}`); }
    }, {serialize: false});
    const previewButton = node.addWidget("button", "RESTORE PREVIEW MODE", null, () => {
        try { restorePreview(node); } catch (error) { alert(`SeedHunter: ${error.message}`); }
    }, {serialize: false});
    singleButton.serializeValue = () => undefined;
    previewButton.serializeValue = () => undefined;
}

function collapseResolutionHelper(node) {
    if (node.type !== "ResolutionSelector") return;
    node.title = "INTERNAL — generation dimensions (managed by FORMAT)";
    node.flags ||= {};
    node.flags.collapsed = true;
    node.setDirtyCanvas?.(true, true);
}

function enableSinglePass(control) {
    const mp = Number(widget(control, "single_pass_megapixels")?.value);
    if (!Number.isFinite(mp) || mp <= 0) throw new Error("Enter a valid single-pass resolution.");
    control.properties ||= {};
    if (control.properties.seedhunter_mode !== "single") {
        control.properties.seedhunter_saved_modes = Object.fromEntries(
            controlledNodes().map((node) => [String(node.id), Number(node.mode ?? NORMAL)])
        );
    }
    const [preview1, preview2, preview3] = PREVIEW_OUTPUTS.map(findNode);
    if (!preview1 || !preview2 || !preview3) throw new Error("The three preview output nodes were not found.");
    setResolution(control, mp);
    setFinalResolution(control);
    setMode(preview1, NORMAL);
    setMode(preview2, BYPASS);
    setMode(preview3, BYPASS);
    for (const node of nodesInControlledGroups()) setMode(node, BYPASS);
    const seamless = findNode("FULL SEAMLESS VIDEO");
    if (seamless) setMode(seamless, BYPASS);
    const contextSave = findNode(SINGLE_PASS_CONTEXT_SAVE);
    if (!contextSave) throw new Error("The single-pass context save node was not found.");
    setMode(contextSave, NORMAL);
    setStatus(control, "single");
    notify(`Single-pass mode enabled at ${mp} MP; Preview 1 and its locked-audio context save are active.`);
}

function restorePreview(control) {
    const mp = Number(widget(control, "preview_megapixels")?.value);
    if (!Number.isFinite(mp) || mp <= 0) throw new Error("Enter a valid preview resolution.");
    setResolution(control, mp);
    setFinalResolution(control);
    const saved = control.properties?.seedhunter_saved_modes || {};
    const byId = new Map((app.graph?._nodes || []).map((node) => [String(node.id), node]));
    if (Object.keys(saved).length) {
        for (const [id, mode] of Object.entries(saved)) {
            const node = byId.get(id);
            if (node) setMode(node, mode);
        }
    } else {
        for (const title of PREVIEW_OUTPUTS) {
            const node = findNode(title);
            if (node) setMode(node, NORMAL);
        }
        for (const node of nodesInControlledGroups()) setMode(node, NORMAL);
        const seamless = findNode("FULL SEAMLESS VIDEO");
        if (seamless) setMode(seamless, NORMAL);
    }
    control.properties.seedhunter_saved_modes = {};
    const contextSave = findNode(SINGLE_PASS_CONTEXT_SAVE);
    if (contextSave) setMode(contextSave, BYPASS);
    setStatus(control, "preview");
    notify(`Preview mode restored at ${mp} MP.`);
}

function install(node) {
    if (node.type !== TYPE) return;
    node.properties ||= {};
    node.properties.seedhunter_mode ||= "preview";
    normalizeFormatWidgets(node);
    installButtons(node);
    bindResolutionWidget(node, "preview_megapixels", "preview");
    bindResolutionWidget(node, "single_pass_megapixels", "single");
    bindFormatWidgets(node);
    node.size[0] = Math.max(Number(node.size?.[0] || 0), 430);
    node.size[1] = Math.max(Number(node.size?.[1] || 0), 210);
    setStatus(node, node.properties.seedhunter_mode === "single" ? "single" : "preview");
}

app.registerExtension({
    name: "SeedHunter.SinglePassControls",
    async nodeCreated(node) { collapseResolutionHelper(node); install(node); installFinalPassControl(node); },
    async loadedGraphNode(node) { collapseResolutionHelper(node); install(node); installFinalPassControl(node); },
    async afterConfigureGraph() {
        for (const node of app.graph?._nodes || []) collapseResolutionHelper(node);
        for (const node of app.graph?._nodes || []) { install(node); installFinalPassControl(node); }
        for (const node of app.graph?._nodes || []) {
            if (node.type === TYPE) {
                syncActiveResolution(node);
                setStatus(node, node.properties?.seedhunter_mode === "single" ? "single" : "preview");
            }
        }
    },
});
