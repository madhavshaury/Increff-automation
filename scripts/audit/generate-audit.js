/**
 * generate-audit.js
 *
 * Fetches the PR diff via GitHub API, sends it to NVIDIA NIM
 * (qwen/qwen3.5-122b-a10b) for analysis, and outputs a structured
 * audit report in conventional-commit format.
 *
 * Environment variables (set by the GitHub Actions workflow):
 *   NVIDIA_API_KEY   — NVIDIA NIM API bearer token
 *   GITHUB_TOKEN     — auto-provided by GitHub Actions
 *   REPO_FULL_NAME   — e.g. "madhavshaury/Increff-automation"
 *   PR_NUMBER        — pull request number
 *   PR_TITLE         — original PR title
 *   PR_AUTHOR        — PR author login
 *   PR_URL           — HTML URL of the PR
 *   GITHUB_OUTPUT    — path to the output file (set by Actions)
 */

import { appendFileSync } from "fs";

// ─── Constants ────────────────────────────────────────────────────────
const NVIDIA_API_URL =
  "https://integrate.api.nvidia.com/v1/chat/completions";
const MAX_DIFF_CHARS = 60_000; // keep under model context limit

// Fallback model chain — if the primary is degraded, try the next
const MODELS = [
  { id: "qwen/qwen3.5-122b-a10b", thinking: true },
  { id: "meta/llama-3.3-70b-instruct", thinking: false },
  { id: "qwen/qwq-32b", thinking: true },
];

// ─── Fetch PR diff ───────────────────────────────────────────────────
async function fetchPRDiff() {
  const url = `https://api.github.com/repos/${process.env.REPO_FULL_NAME}/pulls/${process.env.PR_NUMBER}`;

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github.v3.diff",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });

  if (!res.ok) {
    throw new Error(`GitHub API ${res.status}: ${await res.text()}`);
  }

  let diff = await res.text();

  if (diff.length > MAX_DIFF_CHARS) {
    console.warn(
      `⚠️  Diff too large (${diff.length} chars), truncating to ${MAX_DIFF_CHARS}`
    );
    diff =
      diff.substring(0, MAX_DIFF_CHARS) +
      "\n\n... [diff truncated — remaining changes omitted for brevity]";
  }

  return diff;
}

// ─── Fetch PR file list (fallback for huge diffs) ────────────────────
async function fetchPRFiles() {
  const url = `https://api.github.com/repos/${process.env.REPO_FULL_NAME}/pulls/${process.env.PR_NUMBER}/files`;

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github.v3+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });

  if (!res.ok) return [];

  const files = await res.json();
  return files.map((f) => ({
    filename: f.filename,
    status: f.status,
    additions: f.additions,
    deletions: f.deletions,
  }));
}

// ─── Build the prompt ────────────────────────────────────────────────
function buildPrompt(diff, fileList) {
  const filesSummary = fileList
    .map(
      (f) =>
        `  ${f.status.toUpperCase()} ${f.filename} (+${f.additions} -${f.deletions})`
    )
    .join("\n");

  return `You are a senior software engineer performing a system audit on a merged pull request.

Analyze the git diff below and produce a structured audit report.

**Output format — follow EXACTLY:**

TITLE: <A concise conventional commit title, e.g. "fix(inventory): resolve CSV date parsing for edge cases">

BODY:
## Overview
<1–2 sentences summarising what was fixed, added, or changed.>

## Key Changes
<A bulleted list of the most important technical changes. Be specific — mention file names, function names, config keys, etc.>

## Impact
<What this change means for the system, the users, or downstream services. Mention any breaking changes.>

## Verification Results
<What tests or verifications should be performed, and what the expected outcome is.>

---

**PR Metadata:**
- Repository: ${process.env.REPO_FULL_NAME}
- PR #${process.env.PR_NUMBER} by @${process.env.PR_AUTHOR}
- Original PR Title: "${process.env.PR_TITLE}"

**Files Changed:**
${filesSummary}

**Git Diff:**
\`\`\`diff
${diff}
\`\`\``;
}

// ─── Analyze with NVIDIA NIM (with fallback models) ──────────────────
async function analyzeWithNVIDIA(diff, fileList) {
  const prompt = buildPrompt(diff, fileList);

  for (const model of MODELS) {
    console.log(`🤖 Trying model: ${model.id}...`);

    const payload = {
      model: model.id,
      messages: [{ role: "user", content: prompt }],
      max_tokens: 16384,
      temperature: 0.6,
      top_p: 0.95,
      stream: false,
    };

    // Only add thinking for models that support it
    if (model.thinking) {
      payload.chat_template_kwargs = { enable_thinking: true };
    }

    try {
      const res = await fetch(NVIDIA_API_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${process.env.NVIDIA_API_KEY}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errBody = await res.text();
        console.warn(`⚠️  Model ${model.id} failed (${res.status}): ${errBody}`);
        continue; // Try next model
      }

      const data = await res.json();
      console.log(`✅ Model ${model.id} responded successfully`);
      return data.choices[0].message.content;
    } catch (err) {
      console.warn(`⚠️  Model ${model.id} error: ${err.message}`);
      continue; // Try next model
    }
  }

  throw new Error("All NVIDIA NIM models failed. Please check API status at build.nvidia.com");
}

// ─── Parse the model output ─────────────────────────────────────────
function parseAuditResponse(raw) {
  // Strip <think>...</think> blocks produced by qwen thinking mode
  let content = raw.replace(/<think>[\s\S]*?<\/think>/g, "").trim();

  // Extract TITLE
  const titleMatch = content.match(/TITLE:\s*(.+)/);
  const title = titleMatch
    ? titleMatch[1].trim().replace(/^["']|["']$/g, "")
    : process.env.PR_TITLE;

  // Extract BODY (everything after the first "BODY:" marker)
  const bodyMatch = content.match(/BODY:\s*([\s\S]+)/);
  const body = bodyMatch ? bodyMatch[1].trim() : content;

  return { title, body };
}

// ─── Write GitHub Actions outputs ────────────────────────────────────
function setOutput(key, value) {
  const outputFile = process.env.GITHUB_OUTPUT;
  if (!outputFile) {
    console.log(`[OUTPUT] ${key} = ${value.substring(0, 200)}...`);
    return;
  }

  if (value.includes("\n")) {
    // Multi-line value: use heredoc delimiter
    appendFileSync(outputFile, `${key}<<EOF_AUDIT_DELIM\n${value}\nEOF_AUDIT_DELIM\n`);
  } else {
    appendFileSync(outputFile, `${key}=${value}\n`);
  }
}

// ─── Main ────────────────────────────────────────────────────────────
async function main() {
  console.log(
    `🔍 System Audit — ${process.env.REPO_FULL_NAME} PR #${process.env.PR_NUMBER}`
  );
  console.log(`   Author: @${process.env.PR_AUTHOR}`);
  console.log(`   Title:  ${process.env.PR_TITLE}`);
  console.log("─".repeat(60));

  // 1. Fetch diff and file list
  const [diff, fileList] = await Promise.all([
    fetchPRDiff(),
    fetchPRFiles(),
  ]);
  console.log(
    `📄 Diff: ${diff.length} chars | Files changed: ${fileList.length}`
  );

  // 2. Analyze with NVIDIA NIM
  const rawResponse = await analyzeWithNVIDIA(diff, fileList);
  console.log("✅ NVIDIA NIM analysis complete");

  // 3. Parse response
  const { title, body } = parseAuditResponse(rawResponse);

  // 4. Set outputs for downstream steps
  setOutput("title", title);
  setOutput("report", body);

  // 5. Print for logs
  console.log("─".repeat(60));
  console.log(`📌 Suggested PR Title:\n   ${title}\n`);
  console.log(`📝 Audit Report:\n${body}`);
  console.log("─".repeat(60));
  console.log("✅ Audit generation complete");
}

main().catch((err) => {
  console.error("❌ Audit generation failed:", err.message);
  process.exit(1);
});
