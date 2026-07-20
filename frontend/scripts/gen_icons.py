# -*- coding: utf-8 -*-
"""Generate the unified EduAgent icon library.

Design spec: 24-grid, stroke=currentColor 1.8, round caps/joins, fill=none,
size prop (default 16), aria-hidden. Geometry is Feather/Lucide-derived.

Run:  python frontend/scripts/gen_icons.py
"""
import io
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "components", "icons")

TEMPLATE = """<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
{body}
  </svg>
</template>

<script setup>
defineProps({{
  size: {{ type: [Number, String], default: 16 }},
}});
</script>
"""

FILLED_TEMPLATE = """<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    :fill="filled ? 'currentColor' : 'none'"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
{body}
  </svg>
</template>

<script setup>
defineProps({{
  size: {{ type: [Number, String], default: 16 }},
  filled: {{ type: Boolean, default: false }},
}});
</script>
"""

ICONS = {
    # -- navigation / chrome --
    "IconClose": ['<path d="M18 6 6 18" />', '<path d="m6 6 12 12" />'],
    "IconChevronDown": ['<path d="m6 9 6 6 6-6" />'],
    "IconChevronUp": ['<path d="m18 15-6-6-6 6" />'],
    "IconChevronLeft": ['<path d="m15 18-6-6 6-6" />'],
    "IconChevronRight": ['<path d="m9 18 6-6-6-6" />'],
    "IconArrowLeft": ['<path d="M19 12H5" />', '<path d="m12 19-7-7 7-7" />'],
    "IconArrowRight": ['<path d="M5 12h14" />', '<path d="m12 5 7 7-7 7" />'],
    "IconArrowUp": ['<path d="M12 19V5" />', '<path d="m5 12 7-7 7 7" />'],
    "IconArrowDown": ['<path d="M12 5v14" />', '<path d="m19 12-7 7-7-7" />'],
    "IconMenu": ['<path d="M4 6h16" />', '<path d="M4 12h16" />', '<path d="M4 18h16" />'],
    "IconPlus": ['<path d="M12 5v14" />', '<path d="M5 12h14" />'],
    "IconSearch": ['<circle cx="11" cy="11" r="7" />', '<path d="m21 21-4.3-4.3" />'],
    "IconRefresh": [
        '<path d="M20 11a8.1 8.1 0 0 0-14-4.9L4 8" />',
        '<path d="M4 4v4h4" />',
        '<path d="M4 13a8.1 8.1 0 0 0 14 4.9L20 16" />',
        '<path d="M20 20v-4h-4" />',
    ],
    "IconPlay": ['<path d="M8 5.5v13L19 12z" />'],
    "IconTrash": [
        '<path d="M3 6h18" />',
        '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />',
        '<path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />',
        '<path d="M10 11v6" />',
        '<path d="M14 11v6" />',
    ],
    "IconAlert": ['<circle cx="12" cy="12" r="9" />', '<path d="M12 8v4" />', '<path d="M12 16h.01" />'],
    "IconWarning": [
        '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />',
        '<path d="M12 9v4" />',
        '<path d="M12 17h.01" />',
    ],
    "IconUser": ['<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />', '<circle cx="12" cy="7" r="4" />'],
    "IconDownload": ['<path d="M12 3v12" />', '<path d="m7 10 5 5 5-5" />', '<path d="M5 21h14" />'],
    "IconBulb": [
        '<path d="M9 18h6" />',
        '<path d="M10 22h4" />',
        '<path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14" />',
    ],
    "IconSpark": [
        '<path d="M11.5 3.6a.53.53 0 0 1 1 0l1.6 4.9a2 2 0 0 0 1.4 1.4l4.9 1.6a.53.53 0 0 1 0 1l-4.9 1.6a2 2 0 0 0-1.4 1.4l-1.6 4.9a.53.53 0 0 1-1 0l-1.6-4.9a2 2 0 0 0-1.4-1.4l-4.9-1.6a.53.53 0 0 1 0-1l4.9-1.6a2 2 0 0 0 1.4-1.4z" />',
        '<path d="M19 3v4" />',
        '<path d="M21 5h-4" />',
    ],
    # -- learning card types --
    "IconMap": [
        '<path d="M14.1 5.6a2 2 0 0 0 1.8 0l3.7-1.9A1 1 0 0 1 21 4.6v12.8a1 1 0 0 1-.6.9l-4.5 2.3a2 2 0 0 1-1.8 0l-4.2-2.1a2 2 0 0 0-1.8 0l-3.7 1.9A1 1 0 0 1 3 19.4V6.6a1 1 0 0 1 .6-.9l4.5-2.3a2 2 0 0 1 1.8 0z" />',
        '<path d="M15 5.8V21" />',
        '<path d="M9 3.2v15" />',
    ],
    "IconCode": ['<path d="m16 18 6-6-6-6" />', '<path d="m8 6-6 6 6 6" />'],
    "IconPencil": [
        '<path d="M17.2 2.8a2.68 2.68 0 0 1 3.8 3.8L7.3 20.3a2 2 0 0 1-.83.5l-4 1.2a.5.5 0 0 1-.62-.62l1.2-4a2 2 0 0 1 .5-.83z" />',
        '<path d="m14.5 5.5 4 4" />',
    ],
    "IconVideo": ['<rect x="3" y="5" width="18" height="14" rx="2.5" />', '<path d="m10.2 9.3 4.6 2.7-4.6 2.7z" />'],
    "IconClipboard": [
        '<rect x="8" y="2" width="8" height="4" rx="1" />',
        '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />',
        '<path d="m9 13.5 2 2 4-4" />',
    ],
    # -- course subjects --
    "IconGlobe": [
        '<circle cx="12" cy="12" r="9" />',
        '<path d="M3 12h18" />',
        '<path d="M12 3a14 14 0 0 1 3.6 9 14 14 0 0 1-3.6 9 14 14 0 0 1-3.6-9A14 14 0 0 1 12 3z" />',
    ],
    "IconCpu": [
        '<rect x="5" y="5" width="14" height="14" rx="2" />',
        '<rect x="9.5" y="9.5" width="5" height="5" rx="0.75" />',
        '<path d="M9 2v3" />',
        '<path d="M15 2v3" />',
        '<path d="M9 19v3" />',
        '<path d="M15 19v3" />',
        '<path d="M2 9h3" />',
        '<path d="M2 15h3" />',
        '<path d="M19 9h3" />',
        '<path d="M19 15h3" />',
    ],
    # -- redraws of previously rough icons --
    "IconMinimize": ['<path d="M5 12h14" />'],
    "IconPin": [
        '<path d="M12 17v5" />',
        '<path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1z" />',
    ],
    "IconSettings": [
        '<circle cx="12" cy="12" r="3" />',
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />',
    ],
    # -- restyled keepers (geometry unchanged, stroke normalized to 1.8) --
    "IconChat": ['<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />'],
    "IconCheck": ['<polyline points="20 6 9 17 4 12" />'],
    "IconDoc": [
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />',
        '<polyline points="14 2 14 8 20 8" />',
        '<line x1="16" y1="13" x2="8" y2="13" />',
        '<line x1="16" y1="17" x2="8" y2="17" />',
        '<polyline points="10 9 9 9 8 9" />',
    ],
    "IconExpand": [
        '<polyline points="15 3 21 3 21 9" />',
        '<polyline points="9 21 3 21 3 15" />',
        '<line x1="21" y1="3" x2="14" y2="10" />',
        '<line x1="3" y1="21" x2="10" y2="14" />',
    ],
    "IconLock": [
        '<rect x="3" y="11" width="18" height="11" rx="2" ry="2" />',
        '<path d="M7 11V7a5 5 0 0 1 10 0v4" />',
    ],
    "IconPresentation": [
        '<path d="M3 4h18" />',
        '<path d="M12 4v3" />',
        '<rect x="5" y="7" width="14" height="11" rx="1.5" />',
        '<path d="M9 21v-3" />',
        '<path d="M15 21v-3" />',
        '<path d="M9 11h6" />',
        '<path d="M9 14h4" />',
    ],
    "IconQuiz": [
        '<circle cx="12" cy="12" r="10" />',
        '<path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />',
        '<line x1="12" y1="17" x2="12.01" y2="17" />',
    ],
    "IconRadar": [
        '<path d="M12 3 4 7.5v9L12 21l8-4.5v-9z" />',
        '<path d="M12 7.5 8 9.8v4.4l4 2.3 4-2.3V9.8z" />',
        '<path d="M12 3v4.5" />',
        '<path d="M4 7.5 8 9.8" />',
        '<path d="M20 7.5 16 9.8" />',
    ],
    "IconTree": [
        '<path d="M12 5v14" />',
        '<path d="M7 10h10" />',
        '<path d="M7 19h10" />',
        '<circle cx="12" cy="5" r="2.5" />',
        '<circle cx="7" cy="10" r="2.5" />',
        '<circle cx="17" cy="10" r="2.5" />',
        '<circle cx="7" cy="19" r="2.5" />',
        '<circle cx="17" cy="19" r="2.5" />',
    ],
}

FILLED_ICONS = {
    "IconBookmark": ['<path d="M6 3.75A1.75 1.75 0 0 1 7.75 2h8.5A1.75 1.75 0 0 1 18 3.75V20l-6-3.5L6 20V3.75Z" />'],
    "IconStar": ['<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26" />'],
}


def main():
    written = []
    for name, paths in ICONS.items():
        body = "\n".join("    " + p for p in paths)
        content = TEMPLATE.format(body=body)
        with io.open(os.path.join(ROOT, name + ".vue"), "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        written.append(name)

    for name, paths in FILLED_ICONS.items():
        body = "\n".join("    " + p for p in paths)
        content = FILLED_TEMPLATE.format(body=body)
        with io.open(os.path.join(ROOT, name + ".vue"), "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        written.append(name)

    print("wrote %d icons" % len(written))
    for w in sorted(written):
        print(" ", w)


if __name__ == "__main__":
    main()
