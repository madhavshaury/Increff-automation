/**
 * post-to-teams.js
 *
 * Posts the audit report to a central Microsoft Teams channel
 * using Adaptive Cards via Incoming Webhook / Workflows.
 *
 * Environment variables:
 *   TEAMS_WEBHOOK_URL  — Teams incoming webhook URL
 *   AUDIT_TITLE        — Suggested PR title
 *   AUDIT_REPORT       — Full audit report body (markdown)
 *   REPO_NAME          — Repository name
 *   PR_NUMBER          — PR number
 *   PR_AUTHOR          — PR author login
 *   PR_URL             — PR HTML URL
 */

async function postToTeams() {
  const repoName = process.env.REPO_NAME;
  const prNumber = process.env.PR_NUMBER;
  const prAuthor = process.env.PR_AUTHOR;
  const prUrl = process.env.PR_URL;
  const auditTitle = process.env.AUDIT_TITLE;
  const auditReport = process.env.AUDIT_REPORT;

  // Adaptive Card payload (works with both legacy connectors and new Workflows)
  const card = {
    type: "message",
    attachments: [
      {
        contentType: "application/vnd.microsoft.card.adaptive",
        contentUrl: null,
        content: {
          $schema: "http://adaptivecards.io/schemas/adaptive-card.json",
          type: "AdaptiveCard",
          version: "1.4",
          body: [
            {
              type: "ColumnSet",
              columns: [
                {
                  type: "Column",
                  width: "auto",
                  items: [
                    {
                      type: "TextBlock",
                      text: "🔍",
                      size: "Large",
                    },
                  ],
                },
                {
                  type: "Column",
                  width: "stretch",
                  items: [
                    {
                      type: "TextBlock",
                      text: `System Audit — ${repoName}`,
                      weight: "Bolder",
                      size: "Large",
                      color: "Accent",
                    },
                    {
                      type: "TextBlock",
                      text: `PR #${prNumber} merged by @${prAuthor}`,
                      spacing: "None",
                      isSubtle: true,
                    },
                  ],
                },
              ],
            },
            {
              type: "FactSet",
              facts: [
                { title: "Repository", value: repoName },
                { title: "PR Number", value: `#${prNumber}` },
                { title: "Author", value: `@${prAuthor}` },
                { title: "Suggested Title", value: auditTitle },
              ],
              separator: true,
            },
            {
              type: "TextBlock",
              text: auditReport,
              wrap: true,
              spacing: "Medium",
              separator: true,
            },
          ],
          actions: [
            {
              type: "Action.OpenUrl",
              title: "🔗 View Pull Request",
              url: prUrl,
              style: "positive",
            },
          ],
          msteams: {
            width: "Full",
          },
        },
      },
    ],
  };

  const res = await fetch(process.env.TEAMS_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(card),
  });

  if (!res.ok) {
    const errBody = await res.text();
    throw new Error(`Teams webhook ${res.status}: ${errBody}`);
  }

  console.log("✅ Audit posted to Microsoft Teams");
}

postToTeams().catch((err) => {
  console.error("❌ Teams posting failed:", err.message);
  // Don't exit(1) — Teams failure shouldn't fail the whole workflow
  process.exit(0);
});
