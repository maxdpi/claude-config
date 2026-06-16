/**
 * Leon Writing Style — Workflow-tool port (M-006, CI-M-006-014).
 *
 * Replaces the 9-step --step-number workflow with native sequential phases.
 * Linear/single-agent — no fan-out, no teammates.
 *
 * Domain logic from skills/scripts/skills/leon_writing_style/writing_style.py:
 *
 * Phases:
 *   UNDERSTANDING (Steps 1-2):
 *     1. content_classification — classify content type + voice
 *     2. purpose_audience       — define purpose, audience, hook draft
 *
 *   DRAFTING (Step 3):
 *     3. draft                  — write with style rules
 *
 *   VERIFICATION (Steps 4-7):
 *     4. ai_tells_detection     — find AI-generated patterns
 *     5. positive_markers       — verify Leon's positive style markers
 *     6. structural_metrics     — check paragraph/sentence structure
 *     7. voice_consistency      — verify voice consistency across sections
 *
 *   REFINEMENT (Steps 8-9):
 *     8. refinement             — apply targeted fixes
 *     9. final_review           — last pass, output styled content
 *
 * Research grounding (preserved from Python source):
 *   - Plan-and-Solve (Wang et al., 2023)
 *   - Step-Back Prompting (Zheng et al., 2023)
 *   - RE2 Re-Reading (Xu et al., 2023)
 *   - Chain-of-Verification (Dhuliawala et al., 2023)
 *   - Factor+Revise (Dhuliawala et al., 2023)
 *   - Self-Refine (Madaan et al., 2023)
 *   - Metacognitive Prompting (Wang & Zhao, 2024)
 */

export const meta = {
  name: "leon-writing-style",
  description: "9-step style compliance workflow — understanding, drafting, verification, refinement",
  phases: [
    "content_classification",
    "purpose_audience",
    "draft",
    "ai_tells_detection",
    "positive_markers",
    "structural_metrics",
    "voice_consistency",
    "refinement",
    "final_review",
  ],
};

const HISTORY_TEMPLATE = `
CONTEXT ACCUMULATION: Your --thoughts MUST include:

  ## Classification (from Step 1)
  | Section | Content Type | Voice |

  ## Purpose (from Step 2)
  Core message: [one sentence]
  Reference register: [philosophical / pop culture / technical / none]

  ## Violations (from Steps 4-6)
  | Location | Pattern | Quoted Text | Confidence |

  ## Positive Markers (from Step 5)
  | Category | Count | Examples |
  Verdict: PASS/FAIL (found N, required M)

  ## Structural Metrics (from Step 4)
  Paragraph range: X-Y sentences
  Sentence length mix: X% short, Y% medium, Z% long
  Opener type: grounded / meta-commentary

  ## Refinements (from Step 8+)
  | Original | Revised |
`;

export async function run() {
  // ── Phase 1: Content Classification (UNDERSTANDING) ───────────────────────
  phase("content_classification");

  const classificationResult = await agent(
    `LEON WRITING STYLE — Content Classification [UNDERSTANDING Phase]

Before writing, classify your content. Voice rules depend on this.

<content_types>
NARRATIVE - Tell a story, share experience, explain motivation
  Voice: First-person ('I found', 'I chose', 'my advice')
  Use for: Introductions, rationale, design decisions, opinions

INSTRUCTIONAL - Teach how to do something
  Voice: Imperative ('Run the command', 'Configure the setting')
  Use for: Usage guides, tutorials, step-by-step procedures

REFERENCE - Document facts, APIs, specifications
  Voice: Third-person declarative ('The function accepts...')
  Use for: API docs, parameter tables, specifications

HYBRID - Mixed content (most technical writing)
  Voice: Shifts by section purpose
  Use for: READMEs, blog posts, technical articles
</content_types>

<classification_output>
Map your content to types:

  | Section/Topic | Content Type | Voice |
  |---------------|--------------|-------|
  | Introduction  | narrative    | first-person |
  | Usage         | instructional| imperative |
  | ...           | ...          | ... |

This table guides voice selection in later steps.
</classification_output>`,
    { label: "content-classification", phase: "content_classification" },
  );

  // ── Phase 2: Purpose & Audience ───────────────────────────────────────────
  phase("purpose_audience");

  const purposeResult = await agent(
    `LEON WRITING STYLE — Purpose & Audience [UNDERSTANDING Phase]

Classification from Step 1:
${classificationResult}

<audience_analysis>
WHO is the reader?
  - Technical level: expert / intermediate / beginner
  - What do they already know?
  - What confusion might they bring?
</audience_analysis>

<purpose_analysis>
WHY does this content exist?
  - What should change after reading? (knowledge, action, belief)
  - What is the SINGLE most important message?
  - What action should the reader take?

Leon's writing always has a clear throughline.
If you cannot state the core message in one sentence, clarify before drafting.
</purpose_analysis>

<hook_draft>
Draft your opening hook now:
  - State the problem and why it matters
  - Use first-person if narrative ('I was writing an application that...')
  - Be specific, not abstract (name projects, technologies, constraints)
</hook_draft>

<reference_register>
OPTIONAL: Will this document use quotes, anecdotes, or cultural references?

  If YES, choose ONE register and commit:
    - Philosophical (Seneca, military history, wisdom traditions)
    - Pop culture (TV, films, memes, irreverent commentary)
    - Technical (papers, specifications, industry sources)

  If NO, proceed without references. This is a valid choice.
  CRITICAL: Do not mix registers. Pick one or none.
</reference_register>

${HISTORY_TEMPLATE}`,
    { label: "purpose-audience", phase: "purpose_audience" },
  );

  // ── Phase 3: Draft with Style Rules (DRAFTING) ────────────────────────────
  phase("draft");

  const draftResult = await agent(
    `LEON WRITING STYLE — Draft with Style Rules [DRAFTING Phase]

Understanding:
${classificationResult}

Purpose/Audience:
${purposeResult}

<step_back_principles>
Before writing, answer these questions:
  1. What makes Leon's voice distinctive from generic technical writing?
     (First-person authority, specific examples, definitive conclusions)
  2. What is the ONE thing that would make this sound AI-generated?
     (Tricolons, dead metaphors, hollow emphasis, balanced structure)
</step_back_principles>

<core_voice>
CONFIDENT AUTHORITY:
  State conclusions first, then support.
  NOT: 'This might be problematic'
  YES: 'This is the wrong approach.'

FIRST-PERSON FOR NARRATIVE:
  'I found', 'my advice', 'I would recommend'
  Exception: Instructions use imperative, reference uses third-person

SARDONIC WHEN WARRANTED:
  'of course!', 'Sigh.', 'I almost cannot believe I'm reading this.'
  Express genuine frustration at poor engineering decisions.

PRAGMATIC, NOT THEORETICAL:
  Ground in real code, real projects, real consequences.
  Name specific projects, people, technologies.
</core_voice>

<structure_pattern>
1. HOOK - state the problem and why it matters
2. CONTEXT - background needed to understand
3. TECHNICAL DEEP DIVE - code examples, step-by-step
4. ANALYSIS - options and trade-offs
5. RECOMMENDATION - definitive advice
6. IMPLICATIONS (optional) - broader meaning
</structure_pattern>

<transitions>
Use: 'So, ...', 'However, ...', 'Now, ...', 'As such, ...'
Signature: 'The astute reader will notice...', 'Once again, ...'
Avoid: 'Moving on to...', 'In conclusion...', 'Let's explore...'
</transitions>

Write your draft now. Verification follows in the next steps.

${HISTORY_TEMPLATE}`,
    { label: "draft", phase: "draft" },
  );

  // ── Phase 4: AI Tells Detection (VERIFICATION) ────────────────────────────
  phase("ai_tells_detection");

  const aiTellsResult = await agent(
    `LEON WRITING STYLE — AI Tells Detection [VERIFICATION Phase]

Draft:
${draftResult}

<re_read>
Read the draft again, slowly, sentence by sentence.
Then check for AI-generated patterns.
</re_read>

VERIFICATION METHOD: Extract first, then judge.
For each pattern: (1) extract candidates, (2) assess each.

<pattern_1_tricolons>
TRICOLONS / RHYTHMIC PARALLELISM
  EXTRACT: List all sentences with 3+ comma-separated elements or parallel phrase structures.
  JUDGE each: Does it have manufactured symmetry?
    WRONG: 'Clear context, focused execution, reliable results.'
    RIGHT: 'The same agents run at every stage. Standards don't change.'
  Record: | Quote | Confidence (HIGH/MED/LOW) |
</pattern_1_tricolons>

<pattern_2_contrarian>
CONTRARIAN OPENERS / RHETORICAL REFRAMING
  EXTRACT: List sentences with 'X isn't Y — it's Z' or similar contrastive structure.
  JUDGE each: Is it a rhetorical reframe that adds no information?
</pattern_2_contrarian>

<pattern_3_dead_metaphors>
DEAD METAPHORS / CLICHÉS
  EXTRACT: List metaphors, analogies, and clichés.
  JUDGE each: Is it a novel observation or a worn-out phrase?
    WRONG: 'a double-edged sword', 'at the end of the day', 'game-changer'
</pattern_3_dead_metaphors>

<pattern_4_hollow_emphasis>
HOLLOW EMPHASIS
  EXTRACT: List intensifiers and emphasis words.
  WRONG: 'crucial', 'vital', 'important', 'key', 'critical', 'fundamental'
  Judge: Does the emphasis word do work, or is it filler?
</pattern_4_hollow_emphasis>

Output table of violations:
| Location | Pattern | Quoted Text | Confidence |
|----------|---------|-------------|------------|

${HISTORY_TEMPLATE}`,
    { label: "ai-tells-detection", phase: "ai_tells_detection" },
  );

  // ── Phase 5: Positive Markers (VERIFICATION) ──────────────────────────────
  phase("positive_markers");

  const markersResult = await agent(
    `LEON WRITING STYLE — Positive Markers Check [VERIFICATION Phase]

Draft:
${draftResult}

AI Tells found:
${aiTellsResult}

COUNT positive style markers. These signal Leon's authentic voice.

<positive_marker_categories>
SPECIFICITY MARKERS (target: 3+):
  - Named technologies, projects, companies
  - Specific version numbers, dates, measurements
  - Concrete examples with actual code or commands
  Count: ___

FIRST-PERSON AUTHORITY (target: 2+ in narrative sections):
  - 'I found', 'I chose', 'my experience', 'I would'
  Count: ___

DIRECT RECOMMENDATION (target: 1+):
  - 'Use X', 'Avoid Y', 'Do this', 'Don't do that'
  Count: ___

SARDONIC/OPINIONATED MOMENTS (target: 1+ if appropriate):
  - 'of course!', 'Sigh.', expressed frustration at poor decisions
  Count: ___

EVIDENCE-FIRST STRUCTURE (target: all major claims):
  - Claim stated, then supported (not hedged before stated)
  Count: ___
</positive_marker_categories>

Verdict: PASS/FAIL (found N, required M minimum across categories)

${HISTORY_TEMPLATE}`,
    { label: "positive-markers", phase: "positive_markers" },
  );

  // ── Phase 6: Structural Metrics (VERIFICATION) ────────────────────────────
  phase("structural_metrics");

  const structuralResult = await agent(
    `LEON WRITING STYLE — Structural Metrics [VERIFICATION Phase]

Draft:
${draftResult}

CHECK structural patterns:

<paragraph_structure>
TARGET: 2-5 sentences per paragraph
  EXTRACT: Count sentences in each paragraph
  VIOLATIONS: Paragraphs with 1 sentence (too short) or 6+ sentences (too long)
  Record: Paragraph range: X-Y sentences
</paragraph_structure>

<sentence_length_mix>
TARGET: Mix of short (1-8 words), medium (9-20 words), long (21+ words)
  EXTRACT: Length of each sentence
  VIOLATIONS: 3+ consecutive sentences of same length class
  Record: X% short, Y% medium, Z% long
</sentence_length_mix>

<opener_analysis>
FIRST SENTENCE of each paragraph:
  GROUNDED opener: Specific fact, named entity, concrete situation -> GOOD
  META-COMMENTARY opener: 'In this section...', 'Now we will...', 'Let's look at...' -> BAD
  Record: opener type for each paragraph
</opener_analysis>

Output structural analysis with specific violations.

${HISTORY_TEMPLATE}`,
    { label: "structural-metrics", phase: "structural_metrics" },
  );

  // ── Phase 7: Voice Consistency (VERIFICATION) ─────────────────────────────
  phase("voice_consistency");

  const voiceResult = await agent(
    `LEON WRITING STYLE — Voice Consistency [VERIFICATION Phase]

Draft:
${draftResult}

Classification:
${classificationResult}

CHECK voice consistency against the content type classification from Step 1:

For each section, verify:
  | Section | Expected Voice | Actual Voice | Consistent? |
  |---------|---------------|--------------|-------------|
  | ...     | ...           | ...          | YES/NO      |

VOICE VIOLATIONS:
  - NARRATIVE section using third-person passive -> should be first-person
  - INSTRUCTIONAL section using first-person opinion -> should be imperative
  - REFERENCE section using second-person -> should be declarative

FLAG any inconsistencies with location and correction needed.

Also check REGISTER CONSISTENCY:
  - Mixed registers? (philosophical + pop culture = violation)
  - Register matches claimed register from Step 2?

${HISTORY_TEMPLATE}`,
    { label: "voice-consistency", phase: "voice_consistency" },
  );

  // ── Phase 8: Refinement ───────────────────────────────────────────────────
  phase("refinement");

  const refinementResult = await agent(
    `LEON WRITING STYLE — Refinement [REFINEMENT Phase]

Draft:
${draftResult}

Violations found:

AI Tells:
${aiTellsResult}

Positive Markers:
${markersResult}

Structural Issues:
${structuralResult}

Voice Issues:
${voiceResult}

Apply targeted fixes:

For EACH violation:
1. Quote the original text
2. Explain why it violates Leon's style
3. Write the corrected version

PRIORITY ORDER:
  1. AI tells (highest priority — these undermine authenticity)
  2. Voice inconsistencies
  3. Structural issues
  4. Missing positive markers (add specificity, direct recommendations)

DO NOT rewrite sections without violations.
DO NOT change meaning.
DO change: remove hollow emphasis, break tricolons, add specificity, fix voice.

Track: | Original | Revised | Reason |

${HISTORY_TEMPLATE}`,
    { label: "refinement", phase: "refinement" },
  );

  // ── Phase 9: Final Review ─────────────────────────────────────────────────
  phase("final_review");

  const styled_content = await agent(
    `LEON WRITING STYLE — Final Review [REFINEMENT Phase]

Apply all refinements and produce the FINAL styled content.

Refinements:
${refinementResult}

FINAL PASS — read the complete refined content once more:
  1. Does it sound like Leon? (confident, specific, first-person where narrative)
  2. Are all AI tells removed?
  3. Is the structure clean (hook -> context -> deep dive -> recommendation)?
  4. Does it serve the reader's purpose identified in Step 2?

METACOGNITIVE ASSESSMENT:
  Confidence: HIGH / MEDIUM / LOW
  If LOW: describe remaining concerns

Output the FINAL STYLED CONTENT — the complete, publication-ready version.`,
    { label: "final-review", phase: "final_review" },
  );

  return { styled_content };
}
