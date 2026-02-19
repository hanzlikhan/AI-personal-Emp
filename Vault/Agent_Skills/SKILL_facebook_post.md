---
title: Facebook Post Skill
description: Instructions for creating engaging Facebook content
status: active
---

# Facebook Post Skill

When the agent receives a task with `type: facebook_post`, it activates this skill.

## 1. Strategy Phase
Before writing, the agent creates a **Plan** (`/Plans/[timestamp]_facebook_strategy.md`).
- **Goal**: Identify key message, target audience, and timing.
- **Example Step**: "Analyze recent trends in AI to find a relevant hook."

## 2. Drafting Phase
The agent drafts the content.
- **Tone**: Casual, engaging, community-focused. 
- **Formatting**: Use Line breaks for readability. Use Emojis 🚀.
- **Hashtags**: Include 3-5 relevant hashtags at the bottom (e.g., #SilverTierAI).

## 3. Execution Phase
After User Approval:
1.  Agent calls MCP: `post-facebook`.
2.  MCP opens Facebook.
3.  Logs in (if needed).
4.  Types the post and publishes (or saves as draft in Safe Mode).
