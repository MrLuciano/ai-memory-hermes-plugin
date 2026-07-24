# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md


## Claude Code Specifics
- Always enter `plan` mode (`/plan`) before modifying files under `plugins/`, 'tests/' and 'scripts/'.
- When investigating errors, use the custom `/debug` skill before attempting structural changes.
- If you notice repetitive logic patterns, suggest a localized subagent wrapper.
- Do not run terminal migrations unless you explicitly ask for execution permission first.
