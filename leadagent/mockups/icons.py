"""Inline SVG icon set (24x24, stroke based). Simple, original shapes -
no external icon font or CDN, so a mockup is one self-contained page."""

ICONS: dict[str, str] = {
    # generic
    "phone": '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
    "pin": '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "mail": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "star": '<path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z"/>',
    "shield": '<path d="M12 2 4 5v6c0 5 3.4 9.3 8 11 4.6-1.7 8-6 8-11V5z"/><path d="m9 12 2 2 4-4"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c.8-4 4-6 8-6s7.2 2 8 6"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.5 3.3-5.5 6.5-5.5s5.9 2 6.5 5.5"/><circle cx="17.5" cy="9" r="2.5"/><path d="M17 14.6c2.2.3 4 1.8 4.5 4.4"/>',
    "lock": '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "alert": '<path d="M12 3 2 20h20z"/><path d="M12 10v5M12 17.5v.5"/>',
    "doc": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h6"/>',
    "home": '<path d="M3 11 12 3l9 8"/><path d="M5 10v11h14V10M10 21v-6h4v6"/>',
    "briefcase": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M16 8l3 3"/>',
    "heart": '<path d="M12 21s-8-5.2-8-11a4.5 4.5 0 0 1 8-2.7A4.5 4.5 0 0 1 20 10c0 5.8-8 11-8 11z"/>',
    "route": '<circle cx="6" cy="19" r="2"/><circle cx="18" cy="5" r="2"/><path d="M8 19h8a3 3 0 0 0 0-6H8a3 3 0 0 1 0-6h8"/>',
    # driving
    "car": '<path d="M5 17H3v-5l2-5h14l2 5v5h-2"/><path d="M3 12h18"/><circle cx="7.5" cy="17" r="2"/><circle cx="16.5" cy="17" r="2"/>',
    "wheel": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2"/><path d="M12 14v7M10 12H3M14 12h7"/>',
    "road": '<path d="M8 3 4 21M16 3l4 18M12 4v3M12 11v3M12 18v3"/>',
    "parking": '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M9 17V8h4a3 3 0 0 1 0 6H9"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.5-4M4 5v4h4M4 13a8 8 0 0 0 14.5 4M20 19v-4h-4"/>',
    "book": '<path d="M4 4h7a3 3 0 0 1 3 3v14a2 2 0 0 0-2-2H4zM20 4h-7a3 3 0 0 0-3 3v14a2 2 0 0 1 2-2h8z"/>',
    # auto repair
    "wrench": '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/>',
    "brake": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2"/>',
    "oil": '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>',
    "battery": '<rect x="2" y="7" width="18" height="10" rx="2"/><path d="M22 11v2M6 12h4M8 10v4"/>',
    "tire": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
    "engine": '<path d="M4 9h3l2-2h6l2 2h3v7h-3l-2 2H9l-2-2H4z"/><path d="M2 12v2M22 12v2"/>',
    "snow": '<path d="M12 2v20M4 6l16 12M20 6 4 18"/>',
    "bolt": '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    "gauge": '<path d="M4 16a8 8 0 1 1 16 0"/><path d="m12 16 4-5"/><circle cx="12" cy="16" r="1"/>',
    "spring": '<path d="M6 4h12M6 8h12M6 12h12M6 16h12M12 2v2M12 16v5"/>',
    # dental
    "tooth": '<path d="M7 3c-2 0-4 2-4 5 0 2 1 3 1.5 5S5.5 21 7.5 21c1.7 0 1.5-4 4.5-4s2.8 4 4.5 4c2 0 2-4.5 3-8 .5-2 1.5-3 1.5-5 0-3-2-5-4-5-2 0-3 1-5 1S9 3 7 3z"/>',
    "sparkle": '<path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>',
    "smile": '<circle cx="12" cy="12" r="9"/><path d="M8 14a5 5 0 0 0 8 0M9 9h.01M15 9h.01"/>',
    "implant": '<path d="M9 3h6M10 6h4M10 9h4M10.5 12h3M11 15h2M12 18v3"/>',
    "aligner": '<path d="M4 14c0-5 3-8 8-8s8 3 8 8c-2 1-4 1-5-1-1 2-5 2-6 0-1 2-3 2-5 1z"/>',
    "roots": '<path d="M6 3h12v6c0 3-1 5-2 12-1 0-2-5-4-5s-3 5-4 5c-1-7-2-9-2-12z"/>',
    # gym
    "dumbbell": '<path d="M6 7v10M3 9v6M18 7v10M21 9v6M6 12h12"/>',
    "timer": '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2M9 2h6"/>',
    "flame": '<path d="M12 3s5 4 5 9a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3 1-5 1-8z"/>',
    "pulse": '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
    "yoga": '<path d="M12 21V11M12 11c0-4 3-7 8-7 0 5-3 8-8 8M12 14c0-3-2-5-6-5 0 4 2 6 6 6"/>',
    # law
    "scales": '<path d="M12 3v18M6 21h12M4 7h16M6 7l-3 7a3.5 3.5 0 0 0 6 0zM18 7l-3 7a3.5 3.5 0 0 0 6 0z"/>',
    "column": '<path d="M3 21h18M5 21V10M10 21V10M14 21V10M19 21V10M2 10l10-6 10 6z"/>',
    "family": '<circle cx="8" cy="7" r="3"/><circle cx="17" cy="9" r="2.3"/><path d="M2.5 20c.5-3.8 2.7-6 5.5-6s5 2.2 5.5 6M14.5 19.5c.3-2.4 1.5-4 3-4.4"/>',
    "pen": '<path d="M4 20l1-4L17 4l3 3L8 19zM14 7l3 3"/>',
    # accounting
    "calculator": '<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M8 6h8M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01M8 18h.01M12 18h.01M16 18h.01"/>',
    "chart": '<path d="M3 3v18h18M7 15l4-4 3 3 5-6"/>',
    "receipt": '<path d="M5 2h14v20l-3-2-2 2-2-2-2 2-2-2-3 2zM9 7h6M9 11h6M9 15h4"/>',
    "folder": '<path d="M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "rocket": '<path d="M12 2c4 2 6 6 6 10l-3 3H9l-3-3c0-4 2-8 6-10zM9 15l-2 5 5-2M15 15l2 5-5-2M12 9h.01"/>',
    "wallet": '<path d="M3 7a2 2 0 0 1 2-2h13v4"/><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M16 13.5h2"/>',
}


def svg(name: str, cls: str = "ic") -> str:
    inner = ICONS.get(name) or ICONS["check"]
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{inner}</svg>')
