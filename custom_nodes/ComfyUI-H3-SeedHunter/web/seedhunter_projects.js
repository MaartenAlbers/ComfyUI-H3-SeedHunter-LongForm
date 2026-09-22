import { app } from "/scripts/app.js";

const TYPE = "H3SeedHunterProject";
const SINGLE_PASS_CONTEXT_PREFIX = "h3_resume/seedhunter_v14/single/clip";
const FINAL_PASS_CONTEXT_PREFIX = "h3_resume/seedhunter_v14/final/clip";

function widget(node, name) {
    return node?.widgets?.find((item) => item.name === name);
}

function setWidget(node, name, value) {
    const item = widget(node, name);
    if (!item) return;
    item.value = value;
    item.callback?.(value, app.canvas, node, app.canvas?.graph_mouse, {});
    // Some primitive widgets rebuild their displayed value in the callback.
    // Assign once more so the authoritative project state wins visibly too.
    item.value = value;
    node.setDirtyCanvas?.(true, true);
}

function findNode(predicate) {
    return (app.graph?._nodes || []).find(predicate);
}

function ensureSourcePreview(source) {
    source.properties ||= {};
    if (source.seedhunterSourceVideoElement) return source.seedhunterSourceVideoElement;
    if (typeof source.addDOMWidget !== "function") return null;
    const video = document.createElement("video");
    video.controls = true;
    video.preload = "metadata";
    video.playsInline = true;
    video.style.width = "100%";
    video.style.maxHeight = "360px";
    video.style.background = "#111";
    video.style.borderRadius = "6px";
    video.style.display = "none";
    source.addDOMWidget("PROJECT SOURCE PREVIEW", "video", video, {
        serialize: false,
        hideOnZoom: false,
        getMinHeight: () => video.style.display === "none" ? 0 : 260,
    });
    source.seedhunterSourceVideoElement = video;
    return video;
}

function updateClipDisplay(snapshot) {
    const display = findNode((item) => item.type === "H3SeedHunterProjectClipIndex");
    if (!display) return;
    let status = widget(display, "CURRENT PROJECT CLIP");
    if (!status) {
        status = display.addWidget(
            "text", "CURRENT PROJECT CLIP", "not loaded", () => {}, { serialize: false }
        );
    }
    status.value = String(snapshot.next_clip_index);
    display.title = `CURRENT PROJECT CLIP — ${snapshot.next_clip_index} (MANIFEST CONTROLLED)`;
    display.color = "#346b6d";
    display.bgcolor = "#203b3c";
    display.size[0] = Math.max(Number(display.size?.[0] || 0), 530);
    display.size[1] = Math.max(Number(display.size?.[1] || 0), 100);
    display.setDirtyCanvas?.(true, true);
}

function notify(message) {
    app.extensionManager?.toast?.add?.({
        severity: "success", summary: "SeedHunter Project", detail: message, life: 5000,
    });
}

async function requestProject(action, projectName) {
    const response = await fetch(`/seedhunter/project/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_name: projectName }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `Could not ${action} project.`);
    return result;
}

async function checkoutProject(node, recordId) {
    const project = node.properties?.seedhunter_project;
    if (!project?.project_token) throw new Error("Load a project first.");
    const response = await fetch("/seedhunter/project/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            project_name: String(widget(node, "project_name")?.value || ""),
            project_token: project.project_token,
            record_id: recordId,
        }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not change the active timeline.");
    applySnapshot(node, result);
    notify(`Active head changed; project now expects clip ${result.next_clip_index}.`);
}

function updateContinuationSelector(node, snapshot) {
    const clips = Array.isArray(snapshot.clip_choices) ? snapshot.clip_choices : [];
    const entries = [{ label: "Start from beginning", record_id: "" }, ...clips.map((clip) => ({
        label: `${clip.label} · ${String(clip.record_id).slice(0, 8)}`,
        record_id: clip.record_id,
    }))];
    const labels = entries.map((entry) => entry.label);
    node.properties ||= {};
    node.properties.seedhunter_clip_choice_map = Object.fromEntries(
        entries.map((entry) => [entry.label, entry.record_id])
    );
    let selector = widget(node, "CONTINUE FROM CLIP");
    if (!selector) {
        selector = node.addWidget("combo", "CONTINUE FROM CLIP", labels[0], async (value) => {
            if (selector.seedhunterUpdating) return;
            const recordId = node.properties?.seedhunter_clip_choice_map?.[value];
            if (recordId === undefined) return;
            const current = node.properties?.seedhunter_project?.active_head_id || "";
            if (recordId === current) return;
            const proceed = window.confirm(
                `Set '${value}' as the active continuation point? Later clips remain stored.`
            );
            if (!proceed) {
                updateContinuationSelector(node, node.properties.seedhunter_project);
                return;
            }
            try { await checkoutProject(node, recordId); }
            catch (error) { alert(`SeedHunter Project: ${error.message}`); }
        }, { values: labels, serialize: false });
    } else {
        selector.options ||= {};
        selector.options.values = labels;
    }
    const selected = entries.find((entry) => entry.record_id === (snapshot.active_head_id || ""));
    selector.seedhunterUpdating = true;
    selector.value = selected?.label || labels[0];
    selector.seedhunterUpdating = false;
}

async function fetchProjects() {
    const response = await fetch("/seedhunter/projects");
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not list projects.");
    return Array.isArray(result.projects) ? result.projects : [];
}

async function refreshProjectSelector(node, selectName = null) {
    const projects = await fetchProjects();
    const names = projects.map((item) => item.name);
    const choices = names.length ? names : ["(no projects found)"];
    let selector = widget(node, "AVAILABLE PROJECTS");
    if (!selector) {
        selector = node.addWidget("combo", "AVAILABLE PROJECTS", choices[0], (value) => {
            if (!names.includes(value)) return;
            setWidget(node, "project_name", value);
            perform(node, "load").catch((error) => {
                alert(`SeedHunter Project: ${error.message}`);
            });
        }, { values: choices, serialize: false });
    } else {
        selector.options ||= {};
        selector.options.values = choices;
    }

    const current = selectName || String(widget(node, "project_name")?.value || "");
    selector.value = names.includes(current) ? current : choices[0];
    node.properties ||= {};
    node.properties.seedhunter_project_names = names;
    node.setDirtyCanvas?.(true, true);
    return projects;
}

function latestOutput(node) {
    const preview = node?.widgets?.find((item) => item.name === "videopreview");
    const params = preview?.value?.params || preview?.options?.params;
    if (!params?.filename && !params?.fullpath) return null;
    const relative = params.subfolder ? `${params.subfolder}/${params.filename}` : params.filename;
    return {
        path: params.fullpath || relative,
        filename: params.filename,
        subfolder: params.subfolder || "",
    };
}

async function resolvedOutput(node) {
    const visible = latestOutput(node);
    if (visible) return visible;
    const filenamePrefix = widget(node, "filename_prefix")?.value;
    if (!filenamePrefix) throw new Error("No rendered output was found.");
    const response = await fetch("/seedhunter/latest_output", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename_prefix: filenamePrefix }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not find the latest output.");
    return result;
}

function validH3Frames(seconds) {
    const requested = Math.max(5, Math.round(Number(seconds) * 24));
    return requested + ((5 - (requested % 17)) % 17);
}

function collectProjectSettings() {
    const control = findNode((item) => item.type === "H3SeedHunterSinglePassControl");
    return {
        clip_seconds: Number(valueOfNode("PrimitiveFloat", "Number of seconds clip", "value")),
        audio_mode: String(valueOfNode("H3SeedHunterAudioRouter", "AUDIO MODE", "audio_mode") || ""),
        context_frames: Number(valueOfNode("H3SeedHunterAVContext", "PREVIEW", "context_length") || 39),
        preview_megapixels: Number(widget(control, "preview_megapixels")?.value || 0.5),
        single_pass_megapixels: Number(widget(control, "single_pass_megapixels")?.value || 1.5),
        run_mode: control?.properties?.seedhunter_mode === "single" ? "single" : "preview",
    };
}

function applyProjectSettings(snapshot) {
    const settings = snapshot?.workflow_settings;
    if (!settings || !Object.keys(settings).length) return;
    const duration = findNode((item) =>
        item.type === "PrimitiveFloat" && (item.title || "").includes("Number of seconds clip")
    );
    if (settings.clip_seconds !== undefined) setWidget(duration, "value", Number(settings.clip_seconds));

    const router = findNode((item) => item.type === "H3SeedHunterAudioRouter");
    if (settings.audio_mode) setWidget(router, "audio_mode", settings.audio_mode);

    const context = findNode((item) => item.type === "H3SeedHunterAVContext");
    if (settings.context_frames !== undefined) {
        setWidget(context, "context_length", Number(settings.context_frames));
    }

    const control = findNode((item) => item.type === "H3SeedHunterSinglePassControl");
    if (control) {
        if (settings.preview_megapixels !== undefined) {
            setWidget(control, "preview_megapixels", Number(settings.preview_megapixels));
        }
        if (settings.single_pass_megapixels !== undefined) {
            setWidget(control, "single_pass_megapixels", Number(settings.single_pass_megapixels));
        }
        const buttonName = settings.run_mode === "single"
            ? "TURN ON SINGLE PASS"
            : "RESTORE PREVIEW MODE";
        const button = widget(control, buttonName);
        if (button?.callback) button.callback();
        else {
            control.properties ||= {};
            control.properties.seedhunter_mode = settings.run_mode || "preview";
        }
    }
}

function valueOfNode(type, titlePart, widgetName) {
    const node = findNode((item) =>
        item.type === type && (!titlePart || (item.title || "").includes(titlePart))
    );
    return widget(node, widgetName)?.value ?? node?.widgets?.[0]?.value;
}

function applySnapshot(node, snapshot) {
    node.properties ||= {};
    node.properties.seedhunter_project = snapshot;
    setWidget(node, "action", "load project");
    updateClipDisplay(snapshot);
    updateContinuationSelector(node, snapshot);
    applyProjectSettings(snapshot);

    const status = widget(node, "PROJECT STATUS");
    if (status) status.value = snapshot.status;
    node.title = `PROJECT — ${snapshot.status}`;
    node.color = "#346b6d";
    node.bgcolor = "#203b3c";

    const clipNumber = findNode((item) =>
        (item.title || "").includes("NEXT CLIP NUMBER")
    );
    if (clipNumber) {
        const clipWidget = widget(clipNumber, "value") || clipNumber.widgets?.[0];
        if (clipWidget) {
            clipWidget.value = Number(snapshot.next_clip_index);
            clipWidget.callback?.(
                clipWidget.value, app.canvas, clipNumber, app.canvas?.graph_mouse, {}
            );
            clipWidget.value = Number(snapshot.next_clip_index);
            clipNumber.setDirtyCanvas?.(true, true);
        }
    }

    const source = findNode((item) =>
        item.type === "H3SeedHunterSourceVideo" || item.type === "H3SeedHunterSourceVideoFFmpeg"
    );
    if (source) {
        const extending = Boolean(snapshot.previous_clip_video);
        setWidget(source, "start_mode", extending ? "extend video" : "new clip");
        setWidget(source, "video", extending ? snapshot.previous_clip_video : "");
        setWidget(source, "use_source_audio", true);
        let sourceStatus = widget(source, "PROJECT SOURCE VIDEO");
        if (!sourceStatus) {
            sourceStatus = source.addWidget(
                "text", "PROJECT SOURCE VIDEO", "new clip", () => {}, { serialize: false }
            );
        }
        sourceStatus.value = extending ? snapshot.previous_clip_video : "new clip";
        const preview = ensureSourcePreview(source);
        if (preview) {
            if (extending) {
                const projectName = String(widget(node, "project_name")?.value || "");
                preview.src = `/seedhunter/project/source-video?project_name=${encodeURIComponent(projectName)}&revision=${encodeURIComponent(snapshot.revision)}`;
                preview.style.display = "block";
                preview.load();
            } else {
                preview.pause();
                preview.removeAttribute("src");
                preview.style.display = "none";
            }
        }
        source.size[0] = Math.max(Number(source.size?.[0] || 0), 650);
        if (extending) source.size[1] = Math.max(Number(source.size?.[1] || 0), 620);
        source.setDirtyCanvas?.(true, true);
    }

    const promptNode = findNode((item) =>
        item.type === "MiniMaxH3ReferenceToVideo" && (item.title || "").includes("ROLLING CLIP")
    );
    if (promptNode && typeof snapshot.prompt === "string" && snapshot.prompt) {
        setWidget(promptNode, "prompt", snapshot.prompt);
        promptNode.setDirtyCanvas?.(true, true);
    }

    const references = Array.isArray(snapshot.reference_images) ? snapshot.reference_images : [];
    for (let index = 0; index < 4; index += 1) {
        if (!references[index]) continue;
        const picture = findNode((item) =>
            item.type === "LoadImage" && (item.title || "").includes(`<Picture ${index + 1}>`)
        );
        setWidget(picture, "image", references[index]);
    }

    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
}

async function perform(node, action) {
    const projectName = String(widget(node, "project_name")?.value || "").trim();
    if (!projectName) throw new Error("Enter a project name first.");
    const snapshot = await requestProject(action, projectName);
    applySnapshot(node, snapshot);
    await refreshProjectSelector(node, snapshot.project_path?.split(/[\\/]/).pop() || projectName);
    notify(action === "create" ? `Created ${snapshot.status}` : `Loaded ${snapshot.status}`);
}

function singlePassIsActive() {
    const control = findNode((item) => item.type === "H3SeedHunterSinglePassControl");
    return control?.properties?.seedhunter_mode === "single";
}

function lockProjectContextPrefixes() {
    for (const node of app.graph?._nodes || []) {
        if (node.type !== "MiniMaxH3MotionContextSaveLatent") continue;
        const title = node.title || "";
        const prefix = title.includes("SAVE SINGLE PASS CONTEXT")
            ? SINGLE_PASS_CONTEXT_PREFIX
            : title.includes("ARCHIVE ACCEPTED FINAL CHECKPOINT")
                ? FINAL_PASS_CONTEXT_PREFIX
                : null;
        if (!prefix) continue;
        const item = widget(node, "filename_prefix") || node.widgets?.[0];
        if (!item) continue;
        item.value = prefix;
        item.type = "hidden";
        item.computeSize = () => [0, -4];
        node.properties ||= {};
        node.properties.seedhunter_locked_context_prefix = prefix;
        node.setDirtyCanvas?.(true, true);
    }
}

async function acceptRenderedClip(outputNode) {
    const projectNode = findNode((item) => item.type === TYPE);
    const project = projectNode?.properties?.seedhunter_project;
    if (!project?.project_token) throw new Error("Create or load a project first.");

    const singlePassOutput = (outputNode.title || "").includes("HYBRID PREVIEW 1");
    if (singlePassOutput && !singlePassIsActive()) {
        throw new Error("Preview 1 can only be accepted while Single Pass Mode is active.");
    }
    const contextSave = findNode((item) => item.type === "MiniMaxH3MotionContextSaveLatent" && (
        singlePassOutput
            ? (item.title || "").includes("SAVE SINGLE PASS CONTEXT")
            : (item.title || "").includes("ARCHIVE ACCEPTED FINAL CHECKPOINT")
    ));
    if (!contextSave) throw new Error("The matching context-save node was not found.");

    const output = await resolvedOutput(outputNode);
    const clipIndex = Number(project.next_clip_index);
    const seconds = Number(valueOfNode("PrimitiveFloat", "Number of seconds clip", "value"));
    const contextLength = Number(valueOfNode("H3SeedHunterAVContext", "PREVIEW", "context_length") || 39);
    const prompt = String(valueOfNode("MiniMaxH3ReferenceToVideo", "ROLLING CLIP", "prompt") || "");
    const audioMode = String(valueOfNode("H3SeedHunterAudioRouter", "AUDIO MODE", "audio_mode") || "");
    const fps = Number(widget(outputNode, "frame_rate")?.value || 24);
    const contextPrefix = singlePassOutput
        ? SINGLE_PASS_CONTEXT_PREFIX
        : FINAL_PASS_CONTEXT_PREFIX;
    const referenceImages = [];
    for (let index = 1; index <= 4; index += 1) {
        const picture = findNode((item) =>
            item.type === "LoadImage" && (item.title || "").includes(`<Picture ${index}>`)
        );
        referenceImages.push(String(widget(picture, "image")?.value || ""));
    }

    if (!Number.isInteger(clipIndex) || clipIndex < 1) throw new Error("Invalid next clip number.");
    if (!Number.isFinite(seconds) || seconds <= 0) throw new Error("Invalid clip duration.");
    if (!contextPrefix) throw new Error("Context checkpoint prefix is missing.");

    const response = await fetch("/seedhunter/project/accept", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            project_name: String(widget(projectNode, "project_name")?.value || ""),
            project_token: project.project_token,
            clip_index: clipIndex,
            video_path: output.path,
            context_prefix: contextPrefix,
            prompt,
            frame_count: validH3Frames(seconds),
            overlap_frames: clipIndex === 1 ? 0 : contextLength,
            audio_mode: audioMode,
            fps,
            reference_images: referenceImages,
            workflow_settings: collectProjectSettings(),
        }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not accept the clip.");
    applySnapshot(projectNode, result);
    notify(`Accepted clip ${clipIndex}; project now expects clip ${result.next_clip_index}.`);
}

async function saveCurrentProjectState(node) {
    const project = node.properties?.seedhunter_project;
    if (!project?.project_token) throw new Error("Create or load a project first.");
    const response = await fetch("/seedhunter/project/save-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            project_name: String(widget(node, "project_name")?.value || ""),
            project_token: project.project_token,
            settings: collectProjectSettings(),
        }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not save project state.");
    applySnapshot(node, result);
    notify(`Saved workflow state for ${result.status}`);
}

async function assembleCurrentProject(node) {
    const project = node.properties?.seedhunter_project;
    if (!project?.project_token) throw new Error("Create or load a project first.");
    notify("Assembling the active project timeline…");
    const response = await fetch("/seedhunter/project/assemble", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            project_name: String(widget(node, "project_name")?.value || ""),
            project_token: project.project_token,
        }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not assemble the project timeline.");
    applySnapshot(node, result);
    notify(`Assembled ${result.final_frame_count} frames (${result.final_duration.toFixed(3)}s): ${result.final_render}`);
}

function installAcceptButton(node) {
    if (node.type !== "VHS_VideoCombine" || widget(node, "ACCEPT CURRENT CLIP INTO PROJECT")) return;
    const title = node.title || "";
    if (!title.includes("FINAL SELECTED CLIP") && !title.includes("HYBRID PREVIEW 1")) return;
    node.addWidget("button", "ACCEPT CURRENT CLIP INTO PROJECT", null, async () => {
        try { await acceptRenderedClip(node); }
        catch (error) { alert(`SeedHunter Project: ${error.message}`); }
    });
}

function install(node) {
    if (node.type === "H3SeedHunterProjectClipIndex") {
        const project = findNode((item) => item.type === TYPE)?.properties?.seedhunter_project;
        if (project) updateClipDisplay(project);
        return;
    }
    if (node.type !== TYPE) return;
    lockProjectContextPrefixes();
    if (widget(node, "CREATE NEW PROJECT")) {
        refreshProjectSelector(node).catch((error) => console.warn("[SeedHunter]", error));
        return;
    }
    node.properties ||= {};
    refreshProjectSelector(node).catch((error) => console.warn("[SeedHunter]", error));
    node.addWidget("text", "PROJECT STATUS", "No project loaded", () => {}, { serialize: false });
    node.addWidget("button", "CREATE NEW PROJECT", null, async () => {
        try { await perform(node, "create"); }
        catch (error) { alert(`SeedHunter Project: ${error.message}`); }
    });
    node.addWidget("button", "LOAD / REFRESH PROJECT", null, async () => {
        try { await perform(node, "load"); }
        catch (error) { alert(`SeedHunter Project: ${error.message}`); }
    });
    node.addWidget("button", "SAVE CURRENT PROJECT STATE", null, async () => {
        try { await saveCurrentProjectState(node); }
        catch (error) { alert(`SeedHunter Project: ${error.message}`); }
    });
    node.addWidget("button", "ASSEMBLE ACTIVE TIMELINE", null, async () => {
        try { await assembleCurrentProject(node); }
        catch (error) { alert(`SeedHunter Project: ${error.message}`); }
    });
    node.addWidget("button", "REFRESH PROJECT LIST", null, async () => {
        try {
            const projects = await refreshProjectSelector(node);
            notify(`Found ${projects.length} project(s).`);
        } catch (error) { alert(`SeedHunter Project: ${error.message}`); }
    });
    node.size[0] = Math.max(Number(node.size?.[0] || 0), 620);
    node.size[1] = Math.max(Number(node.size?.[1] || 0), 370);

    const saved = node.properties.seedhunter_project;
    if (saved?.status) applySnapshot(node, saved);
}

app.registerExtension({
    name: "SeedHunter.ProjectControls",
    async nodeCreated(node) { install(node); installAcceptButton(node); },
    async loadedGraphNode(node) { install(node); installAcceptButton(node); },
    async afterConfigureGraph() {
        for (const node of app.graph?._nodes || []) {
            install(node);
            installAcceptButton(node);
        }
        lockProjectContextPrefixes();
    },
});
