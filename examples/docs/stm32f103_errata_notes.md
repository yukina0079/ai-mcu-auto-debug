# STM32F103 Errata Notes

This local note stands in for imported errata excerpts during tests.

- Always check the actual errata document for the exact part number and revision.
- If behavior differs from register documentation, mark the debug conclusion as uncertain until confirmed.
- GPIOC.CRH behavior differs from register documentation on affected revision; use workaround before writing MODE13/CNF13.
