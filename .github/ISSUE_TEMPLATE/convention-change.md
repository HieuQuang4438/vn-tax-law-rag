---
name: Convention change
about: A change to the rules themselves. Filed by a human, per CONVENTIONS.md §7.
title: "<section>: <what changes>"
labels: convention
---

## Spec

`CONVENTIONS.md#<section>` — the section being changed. Not a place to write the change.

## Why

<What went wrong, or what the rules cannot currently express. This is the one issue kind
that carries its reasoning in the body: the file being changed is the file that owns the
reason, so there is nowhere else to point. Every other kind points at a document.>

## Work

<Which sections change, and what each becomes. One or two sentences per section.>

## Done when

<Checks, each one runnable. A check that cannot be run is a wish.>

## Now false

<Sentences elsewhere that this change makes wrong, file by file:
`templates/README.md`: "<the sentence>" — now says four, not three.
A rule change invalidates prose silently; this is the list that makes it loud.
Write "nothing" only after looking.>

## Depends on

<#issue numbers, ADR ids, or "nothing">

## Out of scope

<The nearby rule this is not touching, and where it goes instead.>

<!--
This template is the only one whose sections are headings rather than bold labels: its
bodies are long enough that linkable anchors earn the extra lines. The other three stay
one line per field on purpose.

Spec, Work, Done when, Depends on and Out of scope keep those exact names here, because
the audit step in §7 reads them by name before `Closes #N` is written anywhere.
Why and Now false are additions, and the audit does not cover them.

Carries a design choice? docs/checklists/issue-proposal.md before any code.
-->
