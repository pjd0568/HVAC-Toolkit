# SPEC — In-App Help / User Guide

Status: built 12 Jul 2026. Clean-room, written from this app's own tools and the
public standards already cited in each module's spec. Nothing carried from the
frozen prototype.

## Purpose

A single, self-contained Help section that documents every current module: what
each tool is for, when to reach for it, every input it takes, a step-by-step "how
to use it", and how to read the results. Reachable from a **Help button in the
topbar of every page** (context-aware — it jumps to the section for the tool the
user is currently on).

## Scope (modules covered)

Getting Started (app-wide: units toggle, memory slots, PDF/PNG export, shareable
URLs), Weather & Design Conditions, Psychrometrics (Single Point, Mixed Air,
Cooling Coil, AHU Design), Duct Sizing (+ Index Leg), Unit Converter, Design
Guides, Projects, and Pipe Sizing (including Stage 2 system pressure-drop builder).

## Design

- One route, `GET /help`, one Blueprint (`blueprints/help.py`), one template
  (`templates/help.html`). No persistence, no forms that mutate state — same
  static-content pattern as the Design Guides blueprint.
- **Left in-page sidebar index**: a grouped, clickable list of every section,
  sticky so it stays visible while the content scrolls. Anchored (`#section-id`)
  so the topbar Help button and deep links can jump straight to a tool.
- **Search box** at the top of the sidebar: pure client-side JS, no round-trip.
  Typing filters both the sidebar list and the visible content sections by
  matching against each section's heading and body text; a "no matches" note
  shows when nothing matches; clearing the box restores everything.
- **Context-aware Help button**: `base.html` maps the page's `active` variable to
  the matching help anchor, so the button links to `/help#<anchor>` for the
  current tool (falls back to the top of Help on pages with no specific section).
- Content lives in the template as structured HTML (headings + definition lists +
  ordered steps) so the client-side search can read it from the DOM. The
  blueprint passes only the sidebar nav model (group → sections).

## Non-goals (for now)

Per-field inline tooltips on the tool pages themselves, a server-side search
index, and versioned/what's-new notes. The single Help page is deliberately the
one place the guidance lives, to avoid it drifting from the tools the way
duplicated copy would.
