/**
 * post-to-slack.js
 *
 * Posts the audit report to a per-repo Slack channel using Block Kit.
 *
 * Environment variables:
 *   SLACK_BOT_TOKEN  — Bot User OAuth Token (xoxb-...)
 *   SLACK_CHANNEL    — Target channel (e.g. #increff-audits)
 *   AUDIT_TITLE      — Suggested PR title
 *   AUDIT_REPORT     — Full audit report body (markdown)
 *   REPO_NAME        — Repository name (e.g. Increff-automation)
 *   PR_NUMBER        — PR number
 *   PR_AUTHOR        — PR author login
 *   PR_URL           — PR HTML URL
 */

import { WebClient } from "@slack/web-api";

async function postToSlack() {
  const slack = new WebClient(process.env.SLACK_BOT_TOKEN);

  const repoName = process.env.REPO_NAME;
  const prNumber = process.env.PR_NUMBER;
  const prAuthor = process.env.PR_AUTHOR;
  const prUrl = process.env.PR_URL;
  const auditTitle = process.env.AUDIT_TITLE;
  const auditReport = process.env.AUDIT_REPORT;
  const channel = process.env.SLACK_CHANNEL;

  // Truncate report if it exceeds Slack's 3000 char block limit
  const maxReportLength = 2900;
  const reportText =
    auditReport.length > maxReportLength
      ? auditReport.substring(0, maxReportLength) + "\n\n_... report truncated — see PR for full details_"
      : auditReport;

  const blocks = [
    {
      type: "header",
      text: {
        type: "plain_text",
        text: `🔍 System Audit — ${repoName}`,
        emoji: true,
      },
    },
    { type: "divider" },
    {
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: `📌 *PR #${prNumber}* merged by *@${prAuthor}*`,
        },
      ],
    },
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: `*📋 Suggested PR Title:*\n\`\`\`${auditTitle}\`\`\``,
      },
    },
    { type: "divider" },
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: reportText,
      },
    },
    { type: "divider" },
    {
      type: "actions",
      elements: [
        {
          type: "button",
          text: {
            type: "plain_text",
            text: "🔗 View Pull Request",
            emoji: true,
          },
          url: prUrl,
          style: "primary",
        },
      ],
    },
  ];

  const fallbackText = `System Audit — ${repoName} PR #${prNumber} by @${prAuthor}: ${auditTitle}`;

  await slack.chat.postMessage({
    channel,
    text: fallbackText,
    blocks,
    unfurl_links: false,
    unfurl_media: false,
  });

  console.log(`✅ Audit posted to Slack channel: ${channel}`);
}

postToSlack().catch((err) => {
  console.error("❌ Slack posting failed:", err.message);
  // Don't exit(1) — Slack failure shouldn't fail the whole workflow
  process.exit(0);
});
