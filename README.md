# claude-skills

Claude Code skills, each packaged as a plugin in this marketplace.

## Install

In Claude Code:

```
/plugin marketplace add snowch/claude-skills
/plugin install demo-video@snowch-skills
```

## Plugins

| Plugin | Skill | What it does |
|---|---|---|
| [demo-video](plugins/demo-video) | `record-demo` | Records a narrated product demo of a web app as one clean 4K take, scripted with Playwright and voiced by a local TTS model (Kokoro). Delivers a silent master for an editor, a narrated reference copy with captions, and a timecoded shot list. Needs macOS on Apple Silicon, `uv`, `ffmpeg` and Chrome. |

Once installed, ask Claude something like "record a narrated demo of the app at http://localhost:3000 for marketing".

## Adding a skill

1. Add `plugins/<plugin>/.claude-plugin/plugin.json` and `plugins/<plugin>/skills/<skill>/SKILL.md`.
2. List the plugin in `.claude-plugin/marketplace.json`.

Keep skills generic. This repo is public, so it holds no hostnames, IPs, credentials or customer names.
