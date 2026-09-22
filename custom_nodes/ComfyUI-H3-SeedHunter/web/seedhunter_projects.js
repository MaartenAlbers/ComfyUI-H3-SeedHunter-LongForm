import { app } from "/scripts/app.js";

const TYPE = "H3SeedHunterProject";

function widget(node, name) {
    return node?.widgets?.find((item) => item.name === name);
}

function setWidget(node, name, value) {
    const item = widget(node, name);
    if (!item) return;
    item.value = value;
    item.callback?.(value, app.canvas, node, app.canvas?.graph_mouse, {});
}

function findNode(predicate) {
    return (app.graph?._nodes || []).find(predicate);
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

function applySnapshot(node, snapshot) {
    node.properties ||= {};
    node.properties.seedhunter_project = snapshot;
    setWidget(node, "action", "load project");

    const status = widget(node, "PROJECT STATUS");
    if (status) status.value = snapshot.status;
    node.title = `PROJECT — ${snapshot.status}`;
    node.color = "#346b6d";
    node.bgcolor = "#203b3c";

    const clipNumber = findNode((item) =>
        item.type === "PrimitiveInt" && (item.title || "").includes("NEXT CLIP NUMBER")
    );
    setWidget(clipNumber, "value", Number(snapshot.next_clip_index));

    const source = findNode((item) =>
        item.type === "H3SeedHunterSourceVideo" || item.type === "H3SeedHunterSourceVideoFFmpeg"
    );
    if (source) {
        const extending = Boolean(snapshot.previous_clip_video);
        setWidget(source, "start_mode", extending ? "extend video" : "new clip");
        setWidget(source, "video", extending ? snapshot.previous_clip_video : "");
        setWidget(source, "use_source_audio", true);
    }

    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
}

async function perform(node, action) {
    const projectName = String(widget(node, "project_name")?.value || "").trim();
    if (!projectName) throw new Error("Enter a project name first.");
    const snapshot = await requestProject(action, projectName);
    applySnapshot(node, snapshot);
    notify(action === "create" ? `Created ${snapshot.status}` : `Loaded ${snapshot.status}`);
}

function install(node) {
    if (node.type !== TYPE || widget(node, "CREATE NEW PROJECT")) return;
    node.properties ||= {};
    node.addWidget("text", "PROJECT STATUS", "No project loaded", () => {}, { serialize: false });
    node.addWidget("button", "CREATE NEW PROJECT", null, async () => {
        try { await perform(node, "create"); }
        catch (error) { alert(`SeedHunter Project: ${error.message}`); }
    });
    node.addWidget("button", "LOAD / REFRESH PROJECT", null, async () => {
        try { await perform(node, "load"); }
        catch (error) { alert(`SeedHunter Project: ${error.message}`); }
    });
    node.size[0] = Math.max(Number(node.size?.[0] || 0), 620);
    node.size[1] = Math.max(Number(node.size?.[1] || 0), 220);

    const saved = node.properties.seedhunter_project;
    if (saved?.status) applySnapshot(node, saved);
}

app.registerExtension({
    name: "SeedHunter.ProjectControls",
    async nodeCreated(node) { install(node); },
    async loadedGraphNode(node) { install(node); },
    async afterConfigureGraph() {
        for (const node of app.graph?._nodes || []) install(node);
    },
});
