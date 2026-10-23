---
name: routine
description: "Use when the user asks for a routine: something Hermes should do on a schedule (every weekday at 9, every hour, on the 1st). Covers setting it up as a cron job that reads well in Talaria's Routines list and reports where the user will see it."
version: 1.0.0
author: Sageware Solutions Inc.
metadata:
  hermes:
    tags: [talaria, routine, cron, schedule, automation]
---

# Talaria routines

A routine is a cron job. Talaria, the user's iPhone app for Hermes, lists each one under Routines, along with its
schedule, its last and next run, and a session for every run. Set it up with your cron tool.

## Before creating it

- **Pin down the schedule.** If the request is vague ("regularly", "often"), ask once, offering a sensible default
  ("weekdays at 9:00?"). Use the user's timezone.
- **Pin down what a good run produces.** That could be a summary, an alert only when something's wrong, or an
  updated file.
- **Check it doesn't already exist.** List the existing jobs, and update a matching one rather than adding another.

## Setting it up

- **Name.** Talaria shows the job's name as the routine's title, and every run's session is titled
  "<name> · <date time>". Use two to five words in sentence case: "Collect reimbursement requests", "Check
  server health".
- **Prompt.** Write it to stand on its own. Each run starts fresh with no memory of this chat, so include the
  paths, accounts, thresholds and the shape of the output it needs.
- **Delivery.**
  - Results should land where the user will see them. Use this chat's origin unless they name another place.
  - For routines that only matter when something's off, have the run say so plainly in its first line, and keep
    quiet otherwise.
- **Apps.** When the routine keeps a Talaria app current (`~/.hermes/talaria/apps/<name>/`), have it
  rewrite that app's JSON data files, not its page, so the app stays live without being rebuilt.

## After creating it

Confirm in a sentence or two: the routine's name, when it runs next in plain words ("next run: tomorrow 9:00"),
and where its results go. If it's easy to try now, offer to run it once.
