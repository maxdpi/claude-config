---
name: leon-writing-style
description: Invoke IMMEDIATELY via the Workflow tool when user requests style-matched content generation. Do NOT explore first - the workflow orchestrates the writing phases.
---

# Leon Writing Style

Style-matched content generation skill. Produces content that matches Leon's writing voice and style markers.

When this skill activates, IMMEDIATELY invoke the Workflow tool. The workflow IS the entry point.

## Invocation

Invoke the Workflow tool with the script at `skills/leon-writing-style/workflow.mjs`. Pass the user's content request (topic, format, audience) as `args`.

The workflow drives nine phases natively (content_classification → purpose_audience → draft → ai_tells_detection → positive_markers → structural_metrics → voice_consistency → refinement → final_review).

Do NOT explore or draft first. Invoke the workflow and follow its phases.
