# Design consistency

GiroWatch dropdowns must use the same design as GiroTrack. This is a user requirement.

- Use the shared dropdown styles and `--dropdown-*` tokens in `web/theme.css` for all select menus, Actions menus, profile context menus, and dropdown panels, including dynamically created controls.
- GiroTrack is the reference: `C:/AbacusAI/GiroTrack/app/globals.css` (`.payer-picker-menu`, `.cal-payer-filter-menu`, `.cal-payer-option`). Match its font, border, corner radius, spacing, shadows, and hover/selected states.
- Keep menus right-aligned to their trigger so wider menus expand to the left; clamp them within the viewport.
- Selection dropdowns must include a search field above the options, matching GiroTrack. Filter without changing the value until an option is chosen; support empty results, keyboard selection, and Escape.
- Preserve keyboard navigation, focus, dismissal, disabled states, status colours, dark mode, and the user's UI scale.
- Do not introduce separate dropdown styling for new screens. If the reference design changes, update the shared tokens and all affected menu types together.
