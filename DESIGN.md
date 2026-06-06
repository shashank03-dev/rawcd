# Design

## System

RawCD uses a typographic restoration-lab interface. The physical scene is an archival proofing table under calibrated white light: printed clip ledgers, colored correction marks, and a moss-green scanner signal.

## Color

Use OKLCH color variables only.

- Background: pure white, `oklch(1 0 0)`.
- Surface: cool off-white, `oklch(0.972 0.004 140)`.
- Ink: near-black green-tinted ink, `oklch(0.18 0.018 155)`.
- Muted: readable secondary ink, `oklch(0.43 0.020 155)`.
- Primary: moss signal, `oklch(0.48 0.115 140)`.
- Accent: correction vermilion, `oklch(0.58 0.180 33)`.
- Info: blue ledger mark, `oklch(0.50 0.115 235)`.
- Warning: amber repair note, `oklch(0.64 0.145 78)`.
- Error: oxide red, `oklch(0.50 0.170 28)`.

## Typography

Use a compact product type scale. Product controls use a familiar sans stack; headings use Georgia for editorial contrast only where it aids hierarchy. Labels remain sans-serif and never become decorative.

## Components

Panels are tool surfaces, not marketing cards. Use clear borders, ruled sections, stable button sizes, visible focus rings, and compact notes. Avoid numbered section markers except where the content is truly sequential.

## Motion

Motion is reserved for hover, focus, and progress state. Keep transitions under 180 ms and disable nonessential movement for reduced-motion users.
