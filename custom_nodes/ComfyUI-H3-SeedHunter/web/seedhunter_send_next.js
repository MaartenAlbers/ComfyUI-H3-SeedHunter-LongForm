import { app } from "/scripts/app.js";

console.info("[SeedHunter] Send-to-next extension loaded.");

const ROUTER_TYPE = "H3SeedHunterAudioRouter";

function widget(node, name) {
    return node?.widgets?.find((item) => item.name === name);
}

function latestOutput(node) {
    const preview = node?.widgets?.find((item) => item.name === "videopreview");
    const params = preview?.value?.params || preview?.options?.params;
    if (!params?.filename && !params?.fullpath) return null;
    return {
        path: params.fullpath || params.filename,
        filename: params.filename,
        subfolder: params.subfolder || "",
        type: params.type || "output",
    };
}

async function resolvedOutput(node) {
    const visible = latestOutput(node);
    if (visible) return visible;
    const filenamePrefix = widget(node, "filename_prefix")?.value;
    if (!filenamePrefix) throw new Error("No preview or filename prefix was found.");
    const response = await fetch("/seedhunter/latest_output", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename_prefix: filenamePrefix }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not find the latest saved output.");
    return result;
}

function findNode(type, titlePart) {
    return app.graph?._nodes?.find((node) =>
        node.type === type && (!titlePart || (node.title || "").includes(titlePart))
    );
}

function setWidget(node, name, value) {
    const item = widget(node, name);
    if (!item) throw new Error(`Widget '${name}' was not found on ${node?.title || node?.type}.`);
    item.value = value;
    item.callback?.(value, app.canvas, node, app.canvas?.graph_mouse, {});
}

function notify(message) {
    app.extensionManager?.toast?.add?.({ severity: "success", summary: "SeedHunter", detail: message, life: 4000 });
    console.info(`[SeedHunter] ${message}`);
}

function singlePassIsActive() {
    const control = app.graph?._nodes?.find((node) => node.type === "H3SeedHunterSinglePassControl");
    return control?.properties?.seedhunter_mode === "single";
}

async function sendToNextClip(outputNode) {
    const output = await resolvedOutput(outputNode);
    if (!output) throw new Error("Render and save this video first.");
    const source = app.graph?._nodes?.find((node) =>
        node.type === "H3SeedHunterSourceVideo" || node.type === "H3SeedHunterSourceVideoFFmpeg"
    );
    if (!source) throw new Error("START — new clip / seamless extension was not found.");
    setWidget(source, "start_mode", "extend video");
    setWidget(source, "video", output.path);
    setWidget(source, "use_source_audio", true);

    // clip_index on the checkpoint is linked, so its visible value lives on
    // the PrimitiveInt controller rather than on the checkpoint widget.
    const clipNumber = app.graph?._nodes?.find((node) =>
        node.type === "PrimitiveInt" && (node.title || "").includes("NEXT CLIP NUMBER")
    );
    if (!clipNumber) throw new Error("NEXT CLIP NUMBER was not found.");
    const valueWidget = widget(clipNumber, "value") || clipNumber.widgets?.[0];
    if (!valueWidget) throw new Error("The NEXT CLIP NUMBER value was not found.");
    const nextNumber = Math.max(1, Number(valueWidget.value || 1) + 1);
    valueWidget.value = nextNumber;
    valueWidget.callback?.(nextNumber, app.canvas, clipNumber, app.canvas?.graph_mouse, {});
    clipNumber.setDirtyCanvas?.(true, true);
    source.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
    notify("Selected render and its audio are ready as the source for the next clip.");
}

async function sendToAudioReference(outputNode) {
    const output = await resolvedOutput(outputNode);
    if (!output) throw new Error("Render and save the final selected clip first.");
    const reference = findNode("VHS_LoadAudioUpload", "REFERENCE 1") ||
        app.graph?._nodes?.find((node) => (node.title || "").includes("REFERENCE 1"));
    const router = findNode(ROUTER_TYPE);
    if (!reference || !router) throw new Error("REFERENCE 1 or AUDIO MODE was not found.");
    const audioWidget = widget(reference, "audio") || reference.widgets?.[0];
    if (!audioWidget) throw new Error("The REFERENCE 1 file field was not found.");

    const response = await fetch("/seedhunter/copy_output_to_input", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            filename: output.filename,
            subfolder: output.subfolder,
            fullpath: output.path,
        }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not prepare the audio reference.");
    const inputFilename = result.filename;

    if (Array.isArray(audioWidget.options?.values) && !audioWidget.options.values.includes(inputFilename)) {
        audioWidget.options.values.push(inputFilename);
    }
    audioWidget.value = inputFilename;
    audioWidget.callback?.(inputFilename, app.canvas, reference, app.canvas?.graph_mouse, {});
    setWidget(router, "audio_mode", "audio reference");
    reference.mode = 0;
    reference.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
    notify("Final clip audio is loaded as REFERENCE 1.");
}

function installButtons(node) {
    if (node.type !== "VHS_VideoCombine") return;
    const title = node.title || "";
    const isSinglePassOutput = Number(node.id) === 2296 || title.includes("HYBRID PREVIEW 1");
    if (isSinglePassOutput && !widget(node, "USE AS SOURCE FOR NEXT CLIP")) {
        node.addWidget("button", "USE AS SOURCE FOR NEXT CLIP", null, async () => {
            try {
                if (!singlePassIsActive()) throw new Error("Turn on Single Pass Mode before using Preview 1 as the next clip source.");
                await sendToNextClip(node);
            } catch (error) { alert(`SeedHunter: ${error.message}`); }
        });
        console.info("[SeedHunter] Installed next-clip button on the Single Pass output.");
    }
    if ((Number(node.id) === 2675 || title.includes("FULL SEAMLESS VIDEO")) && !widget(node, "USE AS SOURCE FOR NEXT CLIP")) {
        node.addWidget("button", "USE AS SOURCE FOR NEXT CLIP", null, async () => {
            try { await sendToNextClip(node); } catch (error) { alert(`SeedHunter: ${error.message}`); }
        });
        console.info("[SeedHunter] Installed next-clip button.");
    }
    const isFinalSelectedClip = Number(node.id) === 2640 || title.includes("FINAL SELECTED CLIP");
    if (isFinalSelectedClip && !widget(node, "USE AS SOURCE FOR NEXT CLIP")) {
        node.addWidget("button", "USE AS SOURCE FOR NEXT CLIP", null, async () => {
            try { await sendToNextClip(node); } catch (error) { alert(`SeedHunter: ${error.message}`); }
        });
        console.info("[SeedHunter] Installed next-clip button on final selected clip.");
    }
    if (isFinalSelectedClip && !widget(node, "USE AS AUDIO REFERENCE")) {
        node.addWidget("button", "USE AS AUDIO REFERENCE", null, async () => {
            try { await sendToAudioReference(node); } catch (error) { alert(`SeedHunter: ${error.message}`); }
        });
        console.info("[SeedHunter] Installed audio-reference button.");
    }
}

app.registerExtension({
    name: "SeedHunter.SendToNextClip",
    async nodeCreated(node) {
        installButtons(node);
    },
    async loadedGraphNode(node) {
        installButtons(node);
    },
    async afterConfigureGraph() {
        for (const node of app.graph?._nodes || []) installButtons(node);
    },
});
